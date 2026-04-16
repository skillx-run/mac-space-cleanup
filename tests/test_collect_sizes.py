"""Tests for scripts/collect_sizes.py."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import collect_sizes  # noqa: E402


def _run(payload: dict) -> tuple[int, list | dict, str]:
    stdin = io.StringIO(json.dumps(payload))
    stdout = io.StringIO()
    stderr = io.StringIO()
    with mock.patch.object(sys, "stdin", stdin), \
         mock.patch.object(sys, "stdout", stdout), \
         mock.patch.object(sys, "stderr", stderr):
        code = collect_sizes.run([])
    try:
        obj = json.loads(stdout.getvalue())
    except json.JSONDecodeError:
        obj = {"_raw": stdout.getvalue()}
    return code, obj, stderr.getvalue()


class TestCollectSizes(unittest.TestCase):
    def test_three_real_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "a"; a.mkdir(); (a / "x").write_bytes(b"x" * 1024)
            b = Path(td) / "b"; b.mkdir(); (b / "y").write_bytes(b"y" * 4096)
            c = Path(td) / "c"; c.mkdir(); (c / "z").write_bytes(b"z" * 2048)
            code, out, _ = _run({"paths": [str(a), str(b), str(c)]})
            self.assertEqual(code, 0)
            self.assertEqual(len(out), 3)
            # order preserved
            self.assertEqual([r["path"] for r in out], [str(a), str(b), str(c)])
            for r in out:
                self.assertTrue(r["exists"])
                self.assertIsNone(r["error"])
                self.assertGreater(r["size_bytes"], 0)
                self.assertIsNotNone(r["mtime"])

    def test_nonexistent_path_isolated(self):
        with tempfile.TemporaryDirectory() as td:
            real = Path(td) / "real"; real.mkdir(); (real / "f").write_bytes(b"x" * 512)
            fake = "/definitely/not/a/real/path/xyz-12345"
            code, out, _ = _run({"paths": [str(real), fake]})
            self.assertEqual(code, 1)
            by_path = {r["path"]: r for r in out}
            self.assertTrue(by_path[str(real)]["exists"])
            self.assertIsNone(by_path[str(real)]["error"])
            self.assertFalse(by_path[fake]["exists"])
            self.assertIsNotNone(by_path[fake]["error"])

    def test_timeout(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "slow"; target.mkdir()
            with mock.patch.object(
                collect_sizes.subprocess, "run",
                side_effect=subprocess.TimeoutExpired(cmd="du", timeout=30),
            ):
                code, out, _ = _run({"paths": [str(target)]})
            self.assertEqual(code, 1)
            self.assertEqual(out[0]["error"], "timeout")

    def test_concurrent_stable_ordering(self):
        """10 paths: output order must match input order, no duplicates/omissions."""
        with tempfile.TemporaryDirectory() as td:
            dirs = []
            for i in range(10):
                p = Path(td) / f"d{i}"; p.mkdir()
                (p / "f").write_bytes(b"x" * (100 * (i + 1)))
                dirs.append(str(p))
            # Include one repeat to confirm dedup preserves first-seen order
            payload_paths = dirs + [dirs[0]]
            code, out, _ = _run({"paths": payload_paths})
            self.assertEqual(code, 0)
            self.assertEqual([r["path"] for r in out], dirs)
            for r in out:
                self.assertTrue(r["exists"])
                self.assertIsNone(r["error"])

    def test_invalid_json(self):
        stdin = io.StringIO("not json")
        stderr = io.StringIO()
        with mock.patch.object(sys, "stdin", stdin), \
             mock.patch.object(sys, "stdout", io.StringIO()), \
             mock.patch.object(sys, "stderr", stderr):
            code = collect_sizes.run([])
        self.assertEqual(code, 2)
        self.assertIn("invalid stdin JSON", stderr.getvalue())

    def test_paths_not_a_list(self):
        stdin = io.StringIO(json.dumps({"paths": "not a list"}))
        stderr = io.StringIO()
        with mock.patch.object(sys, "stdin", stdin), \
             mock.patch.object(sys, "stdout", io.StringIO()), \
             mock.patch.object(sys, "stderr", stderr):
            code = collect_sizes.run([])
        self.assertEqual(code, 2)
        self.assertIn("paths must be a list", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
