"""Tests for scripts/aggregate_history.py."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

import aggregate_history  # noqa: E402
from _helpers import run_script  # noqa: E402


def _write_run(
    cache_root: Path,
    run_name: str,
    items: list[dict] | None,
    action_records: list[dict],
) -> Path:
    """Create a fake run-* directory with cleanup-result.json + actions.jsonl.

    If ``items`` is None, cleanup-result.json is omitted (simulates a run
    interrupted before report assembly).
    """
    run_dir = cache_root / run_name
    run_dir.mkdir(parents=True)
    if items is not None:
        (run_dir / "cleanup-result.json").write_text(json.dumps({"items": items}))
    with (run_dir / "actions.jsonl").open("w") as fh:
        for rec in action_records:
            fh.write(json.dumps(rec) + "\n")
    return run_dir


def _invoke(cache_root: Path, workdir: Path, *extra: str):
    argv = ["--workdir", str(workdir), "--cache-root", str(cache_root), *extra]
    return run_script(aggregate_history, argv)


class TestAggregateHistory(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.cache = Path(self._tmp) / "cache"
        self.cache.mkdir()
        self.workdir = Path(self._tmp) / "wd"
        self.workdir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    # ------------------------------------------------------------------
    # Empty / degenerate inputs
    # ------------------------------------------------------------------

    def test_empty_cache_root_returns_zero_counts(self):
        code, out, _ = _invoke(self.cache, self.workdir, "--no-gc")
        self.assertEqual(code, 0)
        self.assertEqual(out["runs_analyzed"], 0)
        self.assertEqual(out["by_label"], [])

    def test_missing_cache_root_still_succeeds(self):
        missing = self.cache / "does-not-exist"
        code, out, _ = _invoke(missing, self.workdir, "--no-gc")
        self.assertEqual(code, 0)
        self.assertEqual(out["runs_analyzed"], 0)

    def test_missing_workdir_errors(self):
        code, _, err = _invoke(self.cache, self.workdir / "nope", "--no-gc")
        self.assertEqual(code, 1)
        self.assertIn("workdir not found", err)

    # ------------------------------------------------------------------
    # Aggregation semantics
    # ------------------------------------------------------------------

    def test_aggregates_by_label_and_category(self):
        _write_run(
            self.cache, "run-01",
            items=[
                {"id": "a", "source_label": "Gradle cache", "category": "pkg_cache"},
                {"id": "b", "source_label": "Browser cache", "category": "app_cache"},
            ],
            action_records=[
                {"item_id": "a", "action": "delete", "status": "success", "dry_run": False, "timestamp": 100},
                {"item_id": "b", "action": "trash", "status": "success", "dry_run": False, "timestamp": 200},
            ],
        )
        _write_run(
            self.cache, "run-02",
            items=[
                {"id": "c", "source_label": "Gradle cache", "category": "pkg_cache"},
            ],
            action_records=[
                {"item_id": "c", "action": "delete", "status": "success", "dry_run": False, "timestamp": 300},
            ],
        )

        code, out, _ = _invoke(self.cache, self.workdir, "--no-gc")
        self.assertEqual(code, 0)
        self.assertEqual(out["runs_analyzed"], 2)
        by_key = {(b["source_label"], b["category"]): b for b in out["by_label"]}
        self.assertEqual(by_key[("Gradle cache", "pkg_cache")]["confirmed"], 2)
        self.assertEqual(by_key[("Browser cache", "app_cache")]["confirmed"], 1)
        # last_ts reflects the newest timestamp observed for that tuple.
        self.assertEqual(by_key[("Gradle cache", "pkg_cache")]["last_ts"], 300)

    def test_dry_run_records_excluded(self):
        _write_run(
            self.cache, "run-01",
            items=[{"id": "a", "source_label": "Homebrew cache", "category": "pkg_cache"}],
            action_records=[
                {"item_id": "a", "action": "delete", "status": "success",
                 "dry_run": True, "timestamp": 100},
            ],
        )
        _, out, _ = _invoke(self.cache, self.workdir, "--no-gc")
        self.assertEqual(out["by_label"], [])

    def test_failed_status_excluded(self):
        _write_run(
            self.cache, "run-01",
            items=[{"id": "a", "source_label": "npm cache", "category": "pkg_cache"}],
            action_records=[
                {"item_id": "a", "action": "delete", "status": "failed",
                 "dry_run": False, "timestamp": 100, "error": "perm"},
            ],
        )
        _, out, _ = _invoke(self.cache, self.workdir, "--no-gc")
        self.assertEqual(out["by_label"], [])

    def test_skip_action_excluded(self):
        # skip is L4 record-only, not a user-intent signal.
        _write_run(
            self.cache, "run-01",
            items=[{"id": "a", "source_label": "System caches", "category": "app_cache"}],
            action_records=[
                {"item_id": "a", "action": "skip", "status": "success",
                 "dry_run": False, "timestamp": 100},
            ],
        )
        _, out, _ = _invoke(self.cache, self.workdir, "--no-gc")
        self.assertEqual(out["by_label"], [])

    def test_defer_counts_as_declined(self):
        _write_run(
            self.cache, "run-01",
            items=[{"id": "a", "source_label": "iOS backups", "category": "large_media"}],
            action_records=[
                {"item_id": "a", "action": "defer", "status": "success",
                 "dry_run": False, "timestamp": 100},
            ],
        )
        _, out, _ = _invoke(self.cache, self.workdir, "--no-gc")
        entry = out["by_label"][0]
        self.assertEqual(entry["confirmed"], 0)
        self.assertEqual(entry["declined"], 1)

    def test_archive_only_success_counts_as_confirmed(self):
        _write_run(
            self.cache, "run-01",
            items=[{"id": "a", "source_label": "Large files in Movies", "category": "large_media"}],
            action_records=[
                {"item_id": "a", "action": "archive", "status": "archive_only_success",
                 "dry_run": False, "timestamp": 100},
            ],
        )
        _, out, _ = _invoke(self.cache, self.workdir, "--no-gc")
        self.assertEqual(out["by_label"][0]["confirmed"], 1)

    def test_corrupt_jsonl_line_skipped(self):
        run_dir = self.cache / "run-01"
        run_dir.mkdir()
        (run_dir / "cleanup-result.json").write_text(json.dumps({
            "items": [
                {"id": "a", "source_label": "Gradle cache", "category": "pkg_cache"},
                {"id": "b", "source_label": "Gradle cache", "category": "pkg_cache"},
            ]
        }))
        with (run_dir / "actions.jsonl").open("w") as fh:
            fh.write(json.dumps({"item_id": "a", "action": "delete",
                                 "status": "success", "dry_run": False,
                                 "timestamp": 100}) + "\n")
            fh.write("{not valid json\n")
            fh.write(json.dumps({"item_id": "b", "action": "delete",
                                 "status": "success", "dry_run": False,
                                 "timestamp": 200}) + "\n")

        _, out, _ = _invoke(self.cache, self.workdir, "--no-gc")
        self.assertEqual(out["by_label"][0]["confirmed"], 2)

    def test_run_without_result_json_counted_separately(self):
        _write_run(
            self.cache, "run-01",
            items=None,  # cleanup-result.json omitted
            action_records=[
                {"item_id": "a", "action": "delete", "status": "success",
                 "dry_run": False, "timestamp": 100},
            ],
        )
        _, out, _ = _invoke(self.cache, self.workdir, "--no-gc")
        self.assertEqual(out["runs_analyzed"], 1)
        self.assertEqual(out["runs_without_result_json"], 1)
        self.assertEqual(out["by_label"], [])

    # ------------------------------------------------------------------
    # GC semantics
    # ------------------------------------------------------------------

    def test_gc_keeps_latest_n(self):
        # Create 5 runs with staggered mtimes.
        for i in range(5):
            _write_run(
                self.cache, f"run-{i:02d}",
                items=[{"id": f"x{i}", "source_label": "Homebrew cache", "category": "pkg_cache"}],
                action_records=[{"item_id": f"x{i}", "action": "delete",
                                 "status": "success", "dry_run": False,
                                 "timestamp": i}],
            )
            # Walk mtimes back so run-00 is the oldest.
            os.utime(self.cache / f"run-{i:02d}", (1_700_000_000 + i, 1_700_000_000 + i))

        code, out, _ = _invoke(self.cache, self.workdir, "--keep", "2")
        self.assertEqual(code, 0)
        self.assertEqual(out["runs_gc"]["removed"], 3)
        # kept counts physical dirs left on disk; kept + removed must equal
        # the 5 run-* dirs that existed before GC.
        self.assertEqual(out["runs_gc"]["kept"], 2)
        self.assertEqual(
            out["runs_gc"]["kept"] + out["runs_gc"]["removed"], 5,
        )
        remaining = sorted(p.name for p in self.cache.iterdir() if p.is_dir())
        self.assertEqual(remaining, ["run-03", "run-04"])

    def test_no_gc_flag_preserves_all_runs(self):
        for i in range(3):
            _write_run(
                self.cache, f"run-{i:02d}", items=[], action_records=[],
            )
        code, out, _ = _invoke(self.cache, self.workdir, "--keep", "1", "--no-gc")
        self.assertEqual(code, 0)
        self.assertEqual(out["runs_gc"]["removed"], 0)
        self.assertEqual(len(list(self.cache.iterdir())), 3)
        # kept must count physical dirs, not runs_analyzed. All 3 dirs are
        # on disk even though each has an empty actions.jsonl and 0 items.
        self.assertEqual(out["runs_gc"]["kept"], 3)

    def test_no_gc_counts_physical_dirs_even_without_actions_jsonl(self):
        # Regression: --no-gc used to report runs_analyzed as kept, which
        # under-counted run-* dirs whose actions.jsonl was missing.
        (self.cache / "run-missing").mkdir()  # no actions.jsonl
        _write_run(
            self.cache, "run-ok", items=[], action_records=[
                {"item_id": "x", "action": "delete", "status": "success",
                 "dry_run": False, "timestamp": 1},
            ],
        )
        code, out, _ = _invoke(self.cache, self.workdir, "--no-gc")
        self.assertEqual(code, 0)
        self.assertEqual(out["runs_gc"]["kept"], 2)

    def test_gc_ignores_non_run_prefix_dirs(self):
        # test-* / smoke-* / dry-e2e-* dirs must not be GC'd even though
        # they live under the same cache root.
        _write_run(self.cache, "run-01", items=[], action_records=[])
        (self.cache / "test-foo").mkdir()
        (self.cache / "smoke-bar").mkdir()
        (self.cache / "dry-e2e-baz").mkdir()
        for name in ("run-01", "test-foo", "smoke-bar", "dry-e2e-baz"):
            os.utime(self.cache / name, (1_600_000_000, 1_600_000_000))

        code, _, _ = _invoke(self.cache, self.workdir, "--keep", "0")
        self.assertEqual(code, 0)
        remaining = sorted(p.name for p in self.cache.iterdir() if p.is_dir())
        # run-01 got GC'd; the three non-run dirs survived.
        self.assertEqual(remaining, ["dry-e2e-baz", "smoke-bar", "test-foo"])

    def test_gc_skips_symlinks(self):
        real = self.cache / "run-real"
        real.mkdir()
        link = self.cache / "run-link"
        link.symlink_to(real)
        code, _, _ = _invoke(self.cache, self.workdir, "--keep", "0")
        self.assertEqual(code, 0)
        # Symlink still present; real dir removed (or kept, depending on order).
        self.assertTrue(link.is_symlink())

    def test_gc_never_deletes_protected_workdir(self):
        # Point the workdir *inside* the cache, and age it before filling
        # the cache with newer runs — the protection check should pin it.
        wd = self.cache / "run-workdir"
        wd.mkdir()
        os.utime(wd, (1_500_000_000, 1_500_000_000))
        for i in range(5):
            nd = self.cache / f"run-{i:02d}"
            nd.mkdir()
            os.utime(nd, (1_700_000_000 + i, 1_700_000_000 + i))

        code, out, _ = _invoke(self.cache, wd, "--keep", "2")
        self.assertEqual(code, 0)
        self.assertTrue(wd.is_dir(), "workdir must survive GC even when older than --keep cutoff")
        # 6 run-* dirs on disk (5 test runs + protected workdir); keep=2
        # removes 4 of the non-protected aged dirs; kept = 2 newest + 1
        # protected = 3; kept + removed = 6 matches the physical total.
        self.assertEqual(out["runs_gc"]["kept"], 3)
        self.assertEqual(out["runs_gc"]["removed"], 3)

    # ------------------------------------------------------------------
    # Privacy regression
    # ------------------------------------------------------------------

    def test_output_contains_no_paths_or_basenames(self):
        secret_home = "/Users/someone-secret/Projects/my-company/awesome-tool"
        _write_run(
            self.cache, "run-01",
            items=[{"id": "a", "source_label": "Project node_modules",
                    "category": "project_artifacts"}],
            action_records=[
                {"item_id": "a", "path": f"{secret_home}/node_modules",
                 "action": "delete", "status": "success", "dry_run": False,
                 "timestamp": 100},
            ],
        )

        _, out, _ = _invoke(self.cache, self.workdir, "--no-gc")
        serialised = json.dumps(out)
        self.assertNotIn("someone-secret", serialised)
        self.assertNotIn("my-company", serialised)
        self.assertNotIn("awesome-tool", serialised)
        self.assertNotIn("/Users/", serialised)
        self.assertNotIn("node_modules", serialised.split("\"source_label\"")[0])
        # Also check the on-disk artefact.
        history = json.loads((self.workdir / "history.json").read_text())
        self.assertNotIn("/Users/", json.dumps(history))


if __name__ == "__main__":
    unittest.main()
