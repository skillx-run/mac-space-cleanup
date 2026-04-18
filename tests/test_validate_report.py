"""Tests for scripts/validate_report.py."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

import validate_report  # noqa: E402
from _helpers import run_script  # noqa: E402


_MIN_I18N_DICT = (
    '<script type="application/json" id="i18n-dict">'
    '{"en":{},"zh":{}}'
    '</script>'
)


def _well_formed_html(extra: str = "", i18n_dict: str | None = None) -> str:
    """A minimal report.html that fills every region and carries a
    validator-clean i18n dict. Override ``i18n_dict`` to test dict
    violations; omit to get the default symmetric empty-subtree form."""
    parts = [
        f"<!-- region:{r}:start --><p>filled {r}</p><!-- region:{r}:end -->"
        for r in validate_report.REGIONS
    ]
    dict_block = _MIN_I18N_DICT if i18n_dict is None else i18n_dict
    return (
        f"<html><body>{dict_block}{''.join(parts)}{extra}</body></html>"
    )


def _run(report: Path) -> tuple[int, dict, str]:
    return run_script(validate_report, ["--report", str(report)], None)


class TestValidateReport(unittest.TestCase):
    def setUp(self):
        # All but one test want runtime forbidden list empty (so we don't
        # depend on whoever is running the suite). The one test that needs
        # runtime values overrides this in its own body.
        patcher = mock.patch.object(validate_report, "_runtime_forbidden",
                                    return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)

    # ---------- happy paths ----------

    def test_well_formed_passes(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(_well_formed_html())
            code, out, _ = _run(report)
        self.assertEqual(code, 0)
        self.assertTrue(out["ok"])
        self.assertEqual(out["violations"], [])

    def test_all_good_nextstep_does_not_false_positive(self):
        """When pending_in_trash_bytes==0 the agent replaces the nextstep
        placeholder with `<p class="all-good">All freed bytes are
        immediately reclaimed — no follow-up needed.</p>`. That literal
        must not trigger placeholder_left or empty_region."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html().replace(
                "<!-- region:nextstep:start --><p>filled nextstep</p><!-- region:nextstep:end -->",
                (
                    "<!-- region:nextstep:start -->"
                    '<p class="all-good">All freed bytes are immediately reclaimed'
                    " \u2014 no follow-up needed.</p>"
                    "<!-- region:nextstep:end -->"
                ),
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 0, msg=out)
        self.assertTrue(out["ok"])

    # ---------- structural violations ----------

    def test_missing_region_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html().replace(
                "<!-- region:share:start --><p>filled share</p><!-- region:share:end -->",
                "",
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("missing_region", kinds)
        regions = [v.get("region") for v in out["violations"]
                   if v["kind"] == "missing_region"]
        self.assertIn("share", regions)

    def test_empty_region_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html().replace(
                "<!-- region:hero:start --><p>filled hero</p><!-- region:hero:end -->",
                "<!-- region:hero:start -->   <!-- region:hero:end -->",
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        empties = [v for v in out["violations"] if v["kind"] == "empty_region"]
        self.assertEqual(len(empties), 1)
        self.assertEqual(empties[0]["region"], "hero")

    # ---------- placeholder ----------

    def test_placeholder_marker_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra='<div data-placeholder="hero">Agent fills this block</div>',
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("placeholder_left", kinds)

    def test_placeholder_impact_flagged(self):
        """A surviving impact placeholder is caught — impact is a new
        region introduced in this redesign."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra='<div data-placeholder="impact">TODO</div>',
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        leaks = [v for v in out["violations"] if v["kind"] == "placeholder_left"]
        self.assertTrue(any('data-placeholder="impact"' in v["detail"]
                            for v in leaks))

    # ---------- redaction ----------

    def test_leaked_path_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(extra="<p>/Users/alice/Projects/secret</p>")
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        leaks = [v for v in out["violations"] if v["kind"] == "leaked_fragment"]
        self.assertTrue(any("/Users/" in v["detail"] for v in leaks))

    def test_leaked_credential_hint_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(extra="<code>id_rsa</code>")
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        leaks = [v for v in out["violations"] if v["kind"] == "leaked_fragment"]
        self.assertTrue(any("id_rsa" in v["detail"] for v in leaks))

    def test_runtime_username_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(extra="<p>user is alice today</p>")
            report.write_text(html)
            with mock.patch.object(validate_report, "_runtime_forbidden",
                                   return_value=["alice", "/Users/alice"]):
                code, out, _ = _run(report)
        self.assertEqual(code, 1)
        leaks = [v for v in out["violations"] if v["kind"] == "leaked_fragment"]
        self.assertTrue(any("alice" in v["detail"] for v in leaks))

    # ---------- input handling ----------

    def test_missing_file_returns_violation(self):
        code, out, _ = _run(Path("/tmp/definitely-not-here-xyz123.html"))
        self.assertEqual(code, 1)
        self.assertFalse(out["ok"])
        self.assertEqual(out["violations"][0]["kind"], "missing_file")

    # ---------- dry-run marking ----------

    def test_dry_run_flag_requires_banner_and_prefix(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(_well_formed_html(extra="<p>12.5 GB freed</p>"))
            code, out, _ = run_script(
                validate_report,
                ["--report", str(report), "--dry-run"],
                None,
            )
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertEqual(kinds.count("dry_run_unmarked"), 2)  # banner + prefix
        details = " ".join(v["detail"] for v in out["violations"])
        self.assertIn("dry-banner", details)
        self.assertIn("would be", details)

    def test_dry_run_flag_passes_with_banner_and_prefix(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra=(
                    '<div class="dry-banner">DRY-RUN — no files touched</div>'
                    '<p>would be 12.5 GB freed</p>'
                ),
            )
            report.write_text(html)
            code, out, _ = run_script(
                validate_report,
                ["--report", str(report), "--dry-run"],
                None,
            )
        self.assertEqual(code, 0)
        self.assertTrue(out["ok"])

    def test_dry_run_flag_accepts_simulated_marker(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra=(
                    '<header><div class="dry-banner">DRY-RUN</div></header>'
                    '<p>12.5 GB (simulated)</p>'
                ),
            )
            report.write_text(html)
            code, out, _ = run_script(
                validate_report,
                ["--report", str(report), "--dry-run"],
                None,
            )
        self.assertEqual(code, 0)

    def test_real_run_does_not_require_dry_run_markers(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(_well_formed_html(extra="<p>12.5 GB freed</p>"))
            code, out, _ = _run(report)
        self.assertEqual(code, 0)
        self.assertTrue(out["ok"])

    # ---------- i18n: dry-run markers (bilingual) ----------

    def test_dry_run_flag_accepts_chinese_marker(self):
        """A Chinese dry-run report marks numbers with '预计' / '模拟'
        instead of 'would be'. Validator must accept either vocabulary."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra=(
                    '<div class="dry-banner">预演模式 — 未改动任何文件</div>'
                    '<p>预计 12.5 GB 可释放</p>'
                ),
            )
            report.write_text(html)
            code, out, _ = run_script(
                validate_report,
                ["--report", str(report), "--dry-run"],
                None,
            )
        self.assertEqual(code, 0, msg=out)
        self.assertTrue(out["ok"])

    def test_dry_run_flag_missing_all_language_markers_fails(self):
        """Dry-run banner present but no numeric marker in either
        language → fails with dry_run_unmarked."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra=(
                    '<div class="dry-banner">DRY-RUN</div>'
                    '<p>12.5 GB</p>'
                ),
            )
            report.write_text(html)
            code, out, _ = run_script(
                validate_report,
                ["--report", str(report), "--dry-run"],
                None,
            )
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("dry_run_unmarked", kinds)

    # ---------- i18n: dict structure ----------

    def test_i18n_dict_missing_fails(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(_well_formed_html(i18n_dict=""))
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("i18n_dict_malformed", kinds)
        details = " ".join(v["detail"] for v in out["violations"])
        self.assertIn("missing", details)

    def test_i18n_dict_invalid_json_fails(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                i18n_dict='<script id="i18n-dict">{not valid json}</script>',
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("i18n_dict_malformed", kinds)
        details = " ".join(v["detail"] for v in out["violations"])
        self.assertIn("JSON parse error", details)

    def test_i18n_dict_missing_zh_subtree_fails(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                i18n_dict='<script id="i18n-dict">{"en":{}}</script>',
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("i18n_dict_malformed", kinds)

    def test_i18n_dict_key_mismatch_fails(self):
        """en has a key that zh is missing — asymmetric subtrees must
        flag or a zh user sees untranslated fallback silently."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                i18n_dict=(
                    '<script id="i18n-dict">'
                    '{"en":{"section.foo":"Foo","brand.by":"by"},'
                    '"zh":{"brand.by":"作者"}}'
                    '</script>'
                ),
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("i18n_dict_malformed", kinds)
        details = " ".join(v["detail"] for v in out["violations"])
        self.assertIn("section.foo", details)

    def test_i18n_dict_symmetric_populated_passes(self):
        """A non-trivial symmetric dict (both subtrees with the same
        key set) passes — confirms the check is about key-set equality,
        not emptiness."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                i18n_dict=(
                    '<script id="i18n-dict">'
                    '{"en":{"brand.by":"by","hero.unit":"freed"},'
                    '"zh":{"brand.by":"作者","hero.unit":"已释放"}}'
                    '</script>'
                ),
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 0, msg=out)
        self.assertTrue(out["ok"])

    # ---------- i18n: bilingual span pairing ----------

    def test_locale_pair_balance_ok(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra=(
                    '<p><span data-locale-show="en">Clean run</span>'
                    '<span data-locale-show="zh">清理完成</span></p>'
                    '<p><span data-locale-show="en">Nice</span>'
                    '<span data-locale-show="zh">不错</span></p>'
                ),
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 0, msg=out)

    def test_locale_pair_missing_zh_twin_fails(self):
        """An en span without its zh sibling is the classic regression —
        zh users would see an empty block. Count mismatch catches it."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra=(
                    '<p><span data-locale-show="en">Clean run</span>'
                    '<span data-locale-show="zh">清理完成</span></p>'
                    '<p><span data-locale-show="en">Orphan caption</span></p>'
                ),
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("locale_unpaired", kinds)
        details = " ".join(v["detail"] for v in out["violations"])
        self.assertIn("en=2", details)
        self.assertIn("zh=1", details)


if __name__ == "__main__":
    unittest.main()
