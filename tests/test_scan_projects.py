"""Tests for scripts/scan_projects.py."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

import scan_projects  # noqa: E402
from _helpers import run_script_with_json, run_script  # noqa: E402


def _mkproj(parent: Path, name: str, *, marker_files=(), subdirs=()) -> Path:
    """Create a fake project under <parent>/<name> with .git, marker files, subdirs."""
    proj = parent / name
    (proj / ".git").mkdir(parents=True)
    for m in marker_files:
        (proj / m).write_text("")
    for sub in subdirs:
        (proj / sub).mkdir(parents=True, exist_ok=True)
        (proj / sub / "placeholder").write_text("x")
    return proj


def _scan_dir(root: Path, **extra) -> tuple[int, dict, str]:
    """Run scan_projects against a single root and return (code, parsed, stderr)."""
    payload = {"roots": [str(root)], "max_depth": 6, **extra}
    return run_script_with_json(scan_projects, [], payload)


class TestScanProjects(unittest.TestCase):
    def test_finds_project_with_node_modules(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            proj = _mkproj(base, "foo",
                           marker_files=["package.json"],
                           subdirs=["node_modules"])
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        self.assertEqual(len(out["projects"]), 1)
        p = out["projects"][0]
        self.assertEqual(p["root"], str(proj))
        self.assertIn("package.json", p["markers_found"])
        subs = [a["subtype"] for a in p["artifacts"]]
        self.assertIn("node_modules", subs)

    def test_finds_multiple_artifact_subtypes_in_one_project(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _mkproj(base, "kitchen-sink",
                    marker_files=["package.json", "pyproject.toml"],
                    subdirs=["node_modules", "target", ".venv", "dist"])
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        self.assertEqual(len(out["projects"]), 1)
        arts = {a["subtype"]: a["kind"] for a in out["projects"][0]["artifacts"]}
        self.assertEqual(arts["node_modules"], "deletable")
        self.assertEqual(arts["target"], "deletable")
        self.assertEqual(arts["dist"], "deletable")
        self.assertEqual(arts[".venv"], "venv")

    def test_skips_directory_without_git(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "not-a-project" / "node_modules").mkdir(parents=True)
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        self.assertEqual(out["projects"], [])

    def test_skips_nested_submodule_git(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            outer = _mkproj(base, "outer",
                            marker_files=["package.json"],
                            subdirs=["node_modules"])
            # nested submodule under the outer project
            (outer / "vendor" / "sub").mkdir(parents=True)
            (outer / "vendor" / "sub" / ".git").mkdir()
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        self.assertEqual(len(out["projects"]), 1, msg="submodule must not be a 2nd project")
        self.assertEqual(out["projects"][0]["root"], str(outer))

    def test_prunes_system_cache_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            # plant a fake user project
            user_proj = _mkproj(base, "user-proj",
                                marker_files=["package.json"],
                                subdirs=["node_modules"])
            # plant a "Library/Caches/Homebrew" style repo that should be pruned
            cache_repo = base / "Library" / "Caches" / "Homebrew" / "Library" / "Taps" / "homebrew" / "core"
            cache_repo.mkdir(parents=True)
            (cache_repo / ".git").mkdir()
            (cache_repo / "node_modules").mkdir()
            # plant a ~/.cache/foo style repo
            cache_repo2 = base / ".cache" / "pip" / "wheels" / "deadbeef"
            cache_repo2.mkdir(parents=True)
            (cache_repo2 / ".git").mkdir()

            code, out, _ = _scan_dir(base)

        self.assertEqual(code, 0)
        roots = [p["root"] for p in out["projects"]]
        self.assertEqual(len(roots), 1, msg=f"expected 1 project, got {roots}")
        self.assertEqual(roots[0], str(user_proj))

    def test_markers_found_field_populated(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _mkproj(base, "polyglot",
                    marker_files=["go.mod", "package.json", "pyproject.toml"],
                    subdirs=[])
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        markers = out["projects"][0]["markers_found"]
        self.assertEqual(markers, sorted(["go.mod", "package.json", "pyproject.toml"]))

    def test_env_returned_with_empty_markers_for_agent_to_decide(self):
        # Project with bare env/ but no Python marker. scan_projects emits
        # env as "venv" subtype anyway; the agent (per category-rules.md and
        # SKILL.md) must check markers_found before treating it as venv.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _mkproj(base, "bare", marker_files=[], subdirs=["env"])
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        p = out["projects"][0]
        self.assertEqual(p["markers_found"], [])
        env_arts = [a for a in p["artifacts"] if a["subtype"] == "env"]
        self.assertEqual(len(env_arts), 1)
        self.assertEqual(env_arts[0]["kind"], "venv")

    def test_vendor_returned_with_markers_for_agent_to_decide(self):
        # Project has vendor/ but no go.mod. scan_projects emits it; SKILL.md
        # tells the agent to verify go.mod is in markers_found before keeping it.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _mkproj(base, "rb-app",
                    marker_files=["Gemfile"],
                    subdirs=["vendor"])
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        p = out["projects"][0]
        self.assertEqual(p["markers_found"], ["Gemfile"])
        self.assertNotIn("go.mod", p["markers_found"])
        vendor_arts = [a for a in p["artifacts"] if a["subtype"] == "vendor"]
        self.assertEqual(len(vendor_arts), 1)

    def test_max_depth_respected(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            # plant project 5 dirs deep
            deep = base / "a" / "b" / "c" / "d" / "e"
            _mkproj(deep, "deep-proj", subdirs=["node_modules"])
            # max_depth=4 from base does NOT reach the project's .git
            code, out, _ = run_script_with_json(
                scan_projects, [],
                {"roots": [str(base)], "max_depth": 4},
            )
        self.assertEqual(code, 0)
        self.assertEqual(out["projects"], [])

    def test_find_timeout_isolated(self):
        # Two roots; mock find to time out on the first, succeed on the second.
        from unittest.mock import patch, MagicMock

        def fake_run(cmd, **kw):
            root = cmd[1]
            if "first" in root:
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=30)
            stdout = ""
            return MagicMock(returncode=0, stdout=stdout, stderr="")

        with patch.object(scan_projects.subprocess, "run", side_effect=fake_run):
            code, out, _ = run_script_with_json(
                scan_projects, [],
                {"roots": ["/tmp/first-root", "/tmp/second-root"], "max_depth": 4},
            )
        self.assertEqual(code, 1)
        self.assertEqual(out["projects"], [])
        kinds = [e["kind"] for e in out["stats"]["errors"]]
        self.assertIn("timeout", kinds)
        # Schema: each error has root / kind / detail
        for err in out["stats"]["errors"]:
            self.assertIn("root", err)
            self.assertIn("kind", err)
            self.assertIn("detail", err)

    def test_errors_schema(self):
        # Same shape check via permission failure (rc != 0, no stdout).
        from unittest.mock import patch, MagicMock

        def fake_run(cmd, **kw):
            return MagicMock(returncode=1, stdout="", stderr="Permission denied")

        with patch.object(scan_projects.subprocess, "run", side_effect=fake_run):
            code, out, _ = run_script_with_json(
                scan_projects, [],
                {"roots": ["/no/such/root"], "max_depth": 4},
            )
        self.assertEqual(code, 1)
        self.assertEqual(len(out["stats"]["errors"]), 1)
        e = out["stats"]["errors"][0]
        self.assertEqual(set(e.keys()), {"root", "kind", "detail"})
        self.assertEqual(e["kind"], "permission")

    def test_invalid_stdin_returns_2(self):
        code, _, stderr = run_script(scan_projects, [], "not-json")
        self.assertEqual(code, 2)
        self.assertIn("invalid stdin JSON", stderr)

    def test_roots_not_a_list_returns_2(self):
        code, _, stderr = run_script_with_json(scan_projects, [], {"roots": "nope"})
        self.assertEqual(code, 2)
        self.assertIn("roots must be a list", stderr)

    def test_empty_roots_returns_empty_projects(self):
        code, out, _ = run_script_with_json(scan_projects, [], {"roots": []})
        self.assertEqual(code, 0)
        self.assertEqual(out["projects"], [])
        self.assertEqual(out["stats"]["projects_found"], 0)


if __name__ == "__main__":
    unittest.main()
