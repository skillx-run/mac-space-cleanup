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


def _well_formed_html(extra: str = "", kind: str = "hero") -> str:
    """A minimal HTML that fills every region required for `kind`."""
    regions = (validate_report.HERO_REGIONS if kind == "hero"
               else validate_report.DETAILS_REGIONS)
    parts = [
        f"<!-- region:{r}:start --><p>filled {r}</p><!-- region:{r}:end -->"
        for r in regions
    ]
    return f"<html><body>{''.join(parts)}{extra}</body></html>"


def _run(report: Path, kind: str = "hero") -> tuple[int, dict, str]:
    return run_script(
        validate_report,
        ["--report", str(report), "--kind", kind],
        None,
    )


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

    def test_well_formed_hero_passes(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(_well_formed_html(kind="hero"))
            code, out, _ = _run(report, kind="hero")
        self.assertEqual(code, 0)
        self.assertTrue(out["ok"])
        self.assertEqual(out["violations"], [])

    def test_well_formed_details_passes(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "details.html"
            report.write_text(_well_formed_html(kind="details"))
            code, out, _ = _run(report, kind="details")
        self.assertEqual(code, 0)
        self.assertTrue(out["ok"])

    def test_hero_all_good_nextstep_does_not_false_positive(self):
        """When pending_in_trash_bytes==0 the agent replaces the nextstep
        placeholder with `<p class="all-good">All freed bytes are
        immediately reclaimed — no follow-up needed.</p>`. That literal
        must not trigger placeholder_left (it contains none of the
        forbidden marker strings) or empty_region."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(kind="hero").replace(
                "<!-- region:nextstep:start --><p>filled nextstep</p><!-- region:nextstep:end -->",
                (
                    "<!-- region:nextstep:start -->"
                    '<p class="all-good">All freed bytes are immediately reclaimed'
                    " \u2014 no follow-up needed.</p>"
                    "<!-- region:nextstep:end -->"
                ),
            )
            report.write_text(html)
            code, out, _ = _run(report, kind="hero")
        self.assertEqual(code, 0, msg=out)
        self.assertTrue(out["ok"])

    # ---------- structural violations ----------

    def test_missing_region_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(kind="hero").replace(
                "<!-- region:share:start --><p>filled share</p><!-- region:share:end -->",
                "",
            )
            report.write_text(html)
            code, out, _ = _run(report, kind="hero")
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("missing_region", kinds)
        regions = [v.get("region") for v in out["violations"]
                   if v["kind"] == "missing_region"]
        self.assertIn("share", regions)

    def test_empty_region_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(kind="hero").replace(
                "<!-- region:hero:start --><p>filled hero</p><!-- region:hero:end -->",
                "<!-- region:hero:start -->   <!-- region:hero:end -->",
            )
            report.write_text(html)
            code, out, _ = _run(report, kind="hero")
        self.assertEqual(code, 1)
        empties = [v for v in out["violations"] if v["kind"] == "empty_region"]
        self.assertEqual(len(empties), 1)
        self.assertEqual(empties[0]["region"], "hero")

    def test_hero_fixture_with_details_kind_reports_all_details_regions_missing(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "details.html"
            report.write_text(_well_formed_html(kind="hero"))
            code, out, _ = _run(report, kind="details")
        self.assertEqual(code, 1)
        missing = {v.get("region") for v in out["violations"]
                   if v["kind"] == "missing_region"}
        self.assertEqual(missing, set(validate_report.DETAILS_REGIONS))

    # ---------- placeholder ----------

    def test_placeholder_marker_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                kind="hero",
                extra='<div data-placeholder="hero">Agent fills this block</div>',
            )
            report.write_text(html)
            code, out, _ = _run(report, kind="hero")
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("placeholder_left", kinds)

    def test_placeholder_impact_flagged(self):
        """A surviving impact placeholder is caught even though impact
        is a new region introduced in the two-page split."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                kind="hero",
                extra='<div data-placeholder="impact">TODO</div>',
            )
            report.write_text(html)
            code, out, _ = _run(report, kind="hero")
        self.assertEqual(code, 1)
        leaks = [v for v in out["violations"] if v["kind"] == "placeholder_left"]
        self.assertTrue(any('data-placeholder="impact"' in v["detail"]
                            for v in leaks))

    # ---------- redaction ----------

    def test_leaked_path_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(kind="hero",
                                     extra="<p>/Users/alice/Projects/secret</p>")
            report.write_text(html)
            code, out, _ = _run(report, kind="hero")
        self.assertEqual(code, 1)
        leaks = [v for v in out["violations"] if v["kind"] == "leaked_fragment"]
        self.assertTrue(any("/Users/" in v["detail"] for v in leaks))

    def test_leaked_path_in_details_flagged(self):
        """Details page enforces the same redaction dictionary as hero."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "details.html"
            html = _well_formed_html(kind="details",
                                     extra="<p>/Users/bob/stuff</p>")
            report.write_text(html)
            code, out, _ = _run(report, kind="details")
        self.assertEqual(code, 1)
        leaks = [v for v in out["violations"] if v["kind"] == "leaked_fragment"]
        self.assertTrue(any("/Users/" in v["detail"] for v in leaks))

    def test_leaked_credential_hint_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(kind="hero",
                                     extra="<code>id_rsa</code>")
            report.write_text(html)
            code, out, _ = _run(report, kind="hero")
        self.assertEqual(code, 1)
        leaks = [v for v in out["violations"] if v["kind"] == "leaked_fragment"]
        self.assertTrue(any("id_rsa" in v["detail"] for v in leaks))

    def test_runtime_username_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(kind="hero",
                                     extra="<p>user is alice today</p>")
            report.write_text(html)
            with mock.patch.object(validate_report, "_runtime_forbidden",
                                   return_value=["alice", "/Users/alice"]):
                code, out, _ = _run(report, kind="hero")
        self.assertEqual(code, 1)
        leaks = [v for v in out["violations"] if v["kind"] == "leaked_fragment"]
        self.assertTrue(any("alice" in v["detail"] for v in leaks))

    # ---------- input handling ----------

    def test_missing_file_returns_violation(self):
        code, out, _ = _run(Path("/tmp/definitely-not-here-xyz123.html"),
                            kind="hero")
        self.assertEqual(code, 1)
        self.assertFalse(out["ok"])
        self.assertEqual(out["violations"][0]["kind"], "missing_file")

    def test_missing_kind_arg_exits_2(self):
        """argparse rejects a CLI invocation that omits --kind."""
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(_well_formed_html(kind="hero"))
            with self.assertRaises(SystemExit) as ctx:
                run_script(
                    validate_report,
                    ["--report", str(report)],  # no --kind
                    None,
                )
        self.assertEqual(ctx.exception.code, 2)

    # ---------- dry-run marking ----------

    def test_dry_run_flag_requires_banner_and_prefix(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(
                _well_formed_html(kind="hero", extra="<p>12.5 GB freed</p>")
            )
            code, out, _ = run_script(
                validate_report,
                ["--report", str(report), "--kind", "hero", "--dry-run"],
                None,
            )
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertEqual(kinds.count("dry_run_unmarked"), 2)  # banner + prefix
        details = " ".join(v["detail"] for v in out["violations"])
        self.assertIn("dry-banner", details)
        self.assertIn("would be", details)

    def test_dry_run_flag_requires_banner_on_details_too(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "details.html"
            report.write_text(
                _well_formed_html(kind="details", extra="<p>12.5 GB freed</p>")
            )
            code, out, _ = run_script(
                validate_report,
                ["--report", str(report), "--kind", "details", "--dry-run"],
                None,
            )
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("dry_run_unmarked", kinds)

    def test_dry_run_flag_passes_with_banner_and_prefix(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                kind="hero",
                extra=(
                    '<div class="dry-banner">DRY-RUN — no files touched</div>'
                    '<p>would be 12.5 GB freed</p>'
                ),
            )
            report.write_text(html)
            code, out, _ = run_script(
                validate_report,
                ["--report", str(report), "--kind", "hero", "--dry-run"],
                None,
            )
        self.assertEqual(code, 0)
        self.assertTrue(out["ok"])

    def test_dry_run_flag_accepts_simulated_marker(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                kind="hero",
                extra=(
                    '<header><div class="dry-banner">DRY-RUN</div></header>'
                    '<p>12.5 GB (simulated)</p>'
                ),
            )
            report.write_text(html)
            code, out, _ = run_script(
                validate_report,
                ["--report", str(report), "--kind", "hero", "--dry-run"],
                None,
            )
        self.assertEqual(code, 0)

    def test_real_run_does_not_require_dry_run_markers(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(
                _well_formed_html(kind="hero", extra="<p>12.5 GB freed</p>")
            )
            code, out, _ = _run(report, kind="hero")
        self.assertEqual(code, 0)
        self.assertTrue(out["ok"])


if __name__ == "__main__":
    unittest.main()
