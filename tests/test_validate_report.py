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


def _well_formed_html(extra: str = "") -> str:
    """A minimal report.html that passes all checks."""
    parts = [
        f"<!-- region:{region}:start --><p>filled {region}</p><!-- region:{region}:end -->"
        for region in validate_report.REGIONS
    ]
    return f"<html><body>{''.join(parts)}{extra}</body></html>"


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

    def test_well_formed_passes(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            report.write_text(_well_formed_html())
            code, out, _ = _run(report)
        self.assertEqual(code, 0)
        self.assertTrue(out["ok"])
        self.assertEqual(out["violations"], [])

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
                "<!-- region:summary:start --><p>filled summary</p><!-- region:summary:end -->",
                "<!-- region:summary:start -->   <!-- region:summary:end -->",
            )
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        empties = [v for v in out["violations"] if v["kind"] == "empty_region"]
        self.assertEqual(len(empties), 1)
        self.assertEqual(empties[0]["region"], "summary")

    def test_placeholder_marker_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.html"
            html = _well_formed_html(
                extra='<div data-placeholder="summary">Agent fills this block</div>')
            report.write_text(html)
            code, out, _ = _run(report)
        self.assertEqual(code, 1)
        kinds = [v["kind"] for v in out["violations"]]
        self.assertIn("placeholder_left", kinds)

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

    def test_missing_file_returns_violation(self):
        code, out, _ = _run(Path("/tmp/definitely-not-here-xyz123.html"))
        self.assertEqual(code, 1)
        self.assertFalse(out["ok"])
        self.assertEqual(out["violations"][0]["kind"], "missing_file")


if __name__ == "__main__":
    unittest.main()
