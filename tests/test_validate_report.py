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


# The rendered template ships the dict container empty; English runs
# leave it like this (baseline text inside data-i18n spans renders
# directly), non-English runs replace the body with a populated object.
_MIN_I18N_DICT = (
    '<script type="application/json" id="i18n-dict">{}</script>'
)


def _well_formed_html(
    extra: str = "",
    i18n_dict: str | None = None,
    data_i18n_attrs: str = "",
) -> str:
    """A minimal report.html that fills every region and carries a
    validator-clean empty i18n dict.

    Override ``i18n_dict`` to test dict violations (pass a full `<script
    id="i18n-dict">…</script>` block, or an empty string to omit the
    container entirely). Pass ``data_i18n_attrs`` to include a snippet
    of extra markup that carries data-i18n attributes — useful for
    tests that exercise the dict-keys-⊆-template-keys rule.
    """
    parts = [
        f"<!-- region:{r}:start --><p>filled {r}</p><!-- region:{r}:end -->"
        for r in validate_report.REGIONS
    ]
    dict_block = _MIN_I18N_DICT if i18n_dict is None else i18n_dict
    return (
        f"<html><body>{dict_block}{data_i18n_attrs}{''.join(parts)}{extra}</body></html>"
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
        self.assertEqual(code, 0, msg=out)
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

    # ---------- dry-run marking: structural checks ----------

    def test_real_run_does_not_require_dry_run_markers(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(_well_formed_html(extra="<p>12.5 GB freed</p>"))
            code, out, _ = _run(report)
        self.assertEqual(code, 0, msg=out)
        self.assertTrue(out["ok"])

    def test_dry_run_without_banner_and_prefix_fails(self):
        """A dry-run without either structural signal raises both
        dry_run_unmarked variants."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(_well_formed_html(extra="<p>12.5 GB</p>"))
            code, out, _ = run_script(
                validate_report,
                ["--report", str(report), "--dry-run"],
                None,
            )
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertEqual(kinds.count("dry_run_unmarked"), 2)
        details = " ".join(v["detail"] for v in out["violations"])
        self.assertIn("dry-banner", details)
        self.assertIn("dryrun-prefix", details)

    def test_dry_run_requires_banner_data_dryrun_attribute(self):
        """A .dry-banner that is missing data-dryrun=\"true\" must fail —
        the attribute is what makes the marker language-agnostic."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra=(
                    '<div class="dry-banner">DRY-RUN</div>'
                    '<p><span class="dryrun-prefix">would be </span>12.5 GB</p>'
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
        details = " ".join(
            v["detail"] for v in out["violations"]
            if v["kind"] == "dry_run_unmarked"
        )
        self.assertIn("dry-banner", details)

    def test_dry_run_requires_number_prefix_span(self):
        """Banner is correct but no .dryrun-prefix anywhere — fails."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra=(
                    '<div class="dry-banner" data-dryrun="true">DRY-RUN</div>'
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
        details = " ".join(v["detail"] for v in out["violations"]
                           if v["kind"] == "dry_run_unmarked")
        self.assertIn("dryrun-prefix", details)

    def test_dry_run_with_banner_and_prefix_passes(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra=(
                    '<div class="dry-banner" data-dryrun="true">DRY-RUN</div>'
                    '<p><span class="dryrun-prefix">would be </span>12.5 GB</p>'
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

    def test_dry_run_banner_accepts_any_language_prose(self):
        """Banner prose in Japanese, prefix span in Arabic — structural
        check is language-agnostic, both markers present → passes."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra=(
                    '<div class="dry-banner" data-dryrun="true">'
                    'ドライラン — ファイルに変更はありません'
                    '</div>'
                    '<p><span class="dryrun-prefix">تقديريًا </span>12.5 GB</p>'
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

    def test_dry_run_banner_attribute_accepts_alternate_order(self):
        """data-dryrun may sit before the class attribute on the element —
        the regex must not require a specific attribute order."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra=(
                    '<div data-dryrun="true" class="dry-banner">DRY-RUN</div>'
                    '<p><span class="dryrun-prefix">would be </span>12.5 GB</p>'
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

    # ---------- i18n: dict structure ----------

    def test_i18n_dict_empty_object_passes(self):
        """Empty {} is the default English-run shape; spans render from
        their data-i18n baseline text and need no dict."""
        # _well_formed_html already uses {} by default.
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(_well_formed_html())
            code, out, _ = _run(report)
        self.assertEqual(code, 0, msg=out)
        self.assertTrue(out["ok"])

    def test_i18n_dict_populated_with_canonical_keys_passes(self):
        """A populated dict whose keys all appear in strings.json AND as
        data-i18n attrs in the rendered HTML passes."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                i18n_dict=(
                    '<script type="application/json" id="i18n-dict">'
                    '{"brand.by":"作者","hero.unit":"已释放"}'
                    '</script>'
                ),
                data_i18n_attrs=(
                    '<span data-i18n="brand.by">by</span>'
                    '<span data-i18n="hero.unit">freed</span>'
                ),
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 0, msg=out)
        self.assertTrue(out["ok"])

    def test_i18n_dict_missing_container_fails(self):
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

    def test_i18n_dict_non_string_value_fails(self):
        """Every dict value must be a string (the hydration script calls
        textContent assignment which expects a string)."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                i18n_dict=(
                    '<script id="i18n-dict">'
                    '{"brand.by": 42}'
                    '</script>'
                ),
                data_i18n_attrs='<span data-i18n="brand.by">by</span>',
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("i18n_dict_malformed", kinds)

    def test_i18n_dict_key_not_in_template_fails(self):
        """A dict carrying a key that the template does not reference
        (via data-i18n) is stale — flag it so agents catch typos and
        removed keys."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                i18n_dict=(
                    '<script id="i18n-dict">'
                    '{"brand.by":"作者","ghost.key":"幽灵"}'
                    '</script>'
                ),
                data_i18n_attrs='<span data-i18n="brand.by">by</span>',
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("i18n_dict_malformed", kinds)
        details = " ".join(v["detail"] for v in out["violations"])
        self.assertIn("ghost.key", details)

    def test_template_data_i18n_key_not_in_strings_json_fails(self):
        """A template that references a data-i18n key absent from the
        canonical strings.json means the project has an orphan label —
        flag it so the canonical source stays authoritative."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                data_i18n_attrs='<span data-i18n="nonexistent.canonical.key">x</span>',
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("template_key_missing_from_strings", kinds)
        details = " ".join(
            v["detail"] for v in out["violations"]
            if v["kind"] == "template_key_missing_from_strings"
        )
        self.assertIn("nonexistent.canonical.key", details)


if __name__ == "__main__":
    unittest.main()
