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
    """Create a fake project under <parent>/<name> with .git, marker files, subdirs.

    Both marker_files and subdirs accept nested relative paths (e.g. `.dvc/config`
    or `.dvc/cache`). Parent dirs are created on demand.
    """
    proj = parent / name
    (proj / ".git").mkdir(parents=True)
    for m in marker_files:
        marker_path = proj / m
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text("")
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

    def test_finds_new_deletable_subtypes(self):
        # v0.7 additions: .mypy_cache / .ruff_cache / .dart_tool / .nyc_output
        # These are all L1-deletable regardless of markers (unambiguous names).
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _mkproj(base, "py-app",
                    marker_files=["pyproject.toml"],
                    subdirs=[".mypy_cache", ".ruff_cache"])
            _mkproj(base, "flutter-app",
                    marker_files=["pubspec.yaml"],
                    subdirs=[".dart_tool"])
            _mkproj(base, "js-app",
                    marker_files=["package.json"],
                    subdirs=[".nyc_output"])
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        by_root = {p["root"]: p for p in out["projects"]}
        for proj_name, expected_sub in [
            ("py-app", ".mypy_cache"),
            ("py-app", ".ruff_cache"),
            ("flutter-app", ".dart_tool"),
            ("js-app", ".nyc_output"),
        ]:
            proj = next(p for root, p in by_root.items() if root.endswith("/" + proj_name))
            subs = {a["subtype"]: a["kind"] for a in proj["artifacts"]}
            self.assertIn(expected_sub, subs, msg=f"{expected_sub} missing in {proj_name}")
            self.assertEqual(subs[expected_sub], "deletable")

    def test_build_subtype_for_elixir_project(self):
        # v0.7: `_build/` is now detected as deletable subtype when `mix.exs`
        # marker is present. scan_projects emits it regardless; the agent uses
        # markers_found to keep the _build -> project_artifacts mapping only
        # for actual Elixir projects.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _mkproj(base, "phoenix-app",
                    marker_files=["mix.exs"],
                    subdirs=["_build"])
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        p = out["projects"][0]
        self.assertIn("mix.exs", p["markers_found"])
        build_arts = [a for a in p["artifacts"] if a["subtype"] == "_build"]
        self.assertEqual(len(build_arts), 1)
        self.assertEqual(build_arts[0]["kind"], "deletable")

    def test_coverage_subtype_uses_coverage_kind(self):
        # v0.7: `coverage/` is a new kind ("coverage", not "deletable" or
        # "venv") because the agent must gate on package.json / Python marker
        # at Stage 4. scan_projects surfaces it unconditionally.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _mkproj(base, "js-tested",
                    marker_files=["package.json"],
                    subdirs=["coverage"])
            # Bare git repo with no language marker — agent will downgrade
            # to orphan L4, but scan_projects still emits the artifact so the
            # agent has visibility.
            _mkproj(base, "bare-repo",
                    marker_files=[],
                    subdirs=["coverage"])
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        by_root = {p["root"]: p for p in out["projects"]}
        for root, proj in by_root.items():
            cov = [a for a in proj["artifacts"] if a["subtype"] == "coverage"]
            self.assertEqual(len(cov), 1, msg=f"coverage missing in {root}")
            self.assertEqual(cov[0]["kind"], "coverage")

    def test_mix_exs_in_project_markers(self):
        # Regression: `mix.exs` must be in PROJECT_MARKERS so Elixir projects
        # with no other marker still surface markers_found=["mix.exs"].
        self.assertIn("mix.exs", scan_projects.PROJECT_MARKERS)

    def test_dvc_config_in_project_markers(self):
        # v0.9: `.dvc/config` is a nested-path marker that gates the
        # `.dvc/cache` nested_cache subtype at Stage 4. Must appear in
        # PROJECT_MARKERS so the marker gate has a signal to check.
        self.assertIn(".dvc/config", scan_projects.PROJECT_MARKERS)

    def test_dvc_cache_subtype_emitted_as_nested_cache(self):
        # v0.9: DVC's `.dvc/cache/` is surfaced as kind="nested_cache" so the
        # agent can clean it while preserving the sibling `.dvc/config` (user
        # state). The parent `.dvc/` must NOT appear as a standalone artifact.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _mkproj(base, "ml-repo",
                    marker_files=["pyproject.toml", ".dvc/config"],
                    subdirs=[".dvc/cache"])
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        p = out["projects"][0]
        self.assertIn(".dvc/config", p["markers_found"])
        subs = {a["subtype"]: a for a in p["artifacts"]}
        # Nested cache surfaces under its literal relative path as subtype.
        self.assertIn(".dvc/cache", subs)
        self.assertEqual(subs[".dvc/cache"]["kind"], "nested_cache")
        # The parent `.dvc/` itself must not be emitted as a deletable artifact.
        self.assertNotIn(".dvc", subs)

    def test_dvc_cache_without_config_marker_still_emitted(self):
        # Stage 4 gates on markers_found — scan_projects emits the artifact
        # unconditionally so the agent gets visibility, analogous to how
        # `env` without a Python marker is still emitted and then downgraded
        # at Stage 4. Here: .dvc/cache exists but .dvc/config does NOT.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _mkproj(base, "no-dvc-config",
                    marker_files=["package.json"],
                    subdirs=[".dvc/cache"])
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        p = out["projects"][0]
        self.assertNotIn(".dvc/config", p["markers_found"])
        # Still emitted — agent demotes to orphan L4 at Stage 4 per §10d.
        nc = [a for a in p["artifacts"] if a["subtype"] == ".dvc/cache"]
        self.assertEqual(len(nc), 1)
        self.assertEqual(nc[0]["kind"], "nested_cache")

    def test_dvc_cache_missing_is_silent(self):
        # If `.dvc/cache/` doesn't exist on disk, no nested_cache artifact is
        # emitted — the marker alone is not enough to fabricate a path.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _mkproj(base, "dvc-no-cache-yet",
                    marker_files=["pyproject.toml", ".dvc/config"],
                    subdirs=[])
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        p = out["projects"][0]
        self.assertIn(".dvc/config", p["markers_found"])
        nc = [a for a in p["artifacts"] if a["kind"] == "nested_cache"]
        self.assertEqual(nc, [])

    # ------------------------------------------------------------------
    # version_pins (v0.9+) — each project carries a dict of language -> list
    # of pinned versions, read from .python-version / .nvmrc at the root.
    # The agent unions these across all projects to exclude them from the
    # global ~/.pyenv/versions/* and ~/.nvm/versions/node/* sweeps.
    # ------------------------------------------------------------------

    def _mkproj_with_pins(self, base: Path, name: str, pin_files: dict[str, str]) -> Path:
        proj = _mkproj(base, name)
        for fname, contents in pin_files.items():
            (proj / fname).write_text(contents)
        return proj

    def test_version_pins_absent_emits_empty_dict(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _mkproj(base, "no-pins")
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        p = out["projects"][0]
        self.assertIn("version_pins", p)
        self.assertEqual(p["version_pins"], {})

    def test_version_pins_python_single_version(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._mkproj_with_pins(base, "py",
                                   {".python-version": "3.11.4\n"})
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        self.assertEqual(out["projects"][0]["version_pins"],
                         {"python": ["3.11.4"]})

    def test_version_pins_python_multi_version_pyenv_chain(self):
        # `pyenv local 3.11.4 3.10.8` writes both on one line, and pyenv
        # treats the list as a fallback chain. Both versions are pinned.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._mkproj_with_pins(base, "chain",
                                   {".python-version": "3.11.4 3.10.8\n"})
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        self.assertEqual(out["projects"][0]["version_pins"],
                         {"python": ["3.11.4", "3.10.8"]})

    def test_version_pins_nvmrc(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._mkproj_with_pins(base, "js",
                                   {".nvmrc": "18\n"})
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        self.assertEqual(out["projects"][0]["version_pins"],
                         {"node": ["18"]})

    def test_version_pins_both_python_and_node(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._mkproj_with_pins(base, "polyglot",
                                   {".python-version": "3.12.1",
                                    ".nvmrc": "20.10.0"})
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        pins = out["projects"][0]["version_pins"]
        self.assertEqual(pins, {"python": ["3.12.1"], "node": ["20.10.0"]})

    def test_version_pins_empty_and_whitespace_only_files_omit_key(self):
        # An empty or whitespace-only pin file contributes no versions;
        # the lang key is omitted entirely so downstream consumers don't
        # see `{"python": []}` that they'd have to special-case.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._mkproj_with_pins(base, "empty",
                                   {".python-version": "",
                                    ".nvmrc": "   \n\t\n"})
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        self.assertEqual(out["projects"][0]["version_pins"], {})

    def test_version_pins_skips_comment_lines_and_handles_crlf(self):
        # Pyenv allows comment lines starting with '#'. CRLF line endings
        # (e.g. from a Windows collaborator) must not leak into the tokens.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._mkproj_with_pins(base, "commented",
                                   {".python-version":
                                    "# pinned for Apple Silicon compat\r\n"
                                    "3.11.4\r\n"
                                    "# fallback\r\n"
                                    "3.10.8\r\n"})
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        self.assertEqual(out["projects"][0]["version_pins"],
                         {"python": ["3.11.4", "3.10.8"]})

    def test_version_pins_missing_files_do_not_crash(self):
        # If .python-version / .nvmrc are absent the key is simply omitted;
        # projects without pin files coexist fine with projects that have them.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _mkproj(base, "no-pins")
            self._mkproj_with_pins(base, "has-pins",
                                   {".python-version": "3.11.4"})
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        by_root = {p["root"].rsplit("/", 1)[1]: p for p in out["projects"]}
        self.assertEqual(by_root["no-pins"]["version_pins"], {})
        self.assertEqual(by_root["has-pins"]["version_pins"],
                         {"python": ["3.11.4"]})

    def test_skips_directory_without_git(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "not-a-project" / "node_modules").mkdir(parents=True)
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        self.assertEqual(out["projects"], [])

    def test_sibling_projects_both_recognised(self):
        # Boundary: two .git dirs at equal depth with shared parent. Confirms
        # _dedup_submodules' startswith uses the os.sep guard rather than
        # bare prefix matching (which would incorrectly drop sibling proj_b
        # because its root starts with the literal 'proj_a' substring? — no,
        # they don't share substrings here, but this also confirms equal-len
        # ordering doesn't accidentally collapse siblings).
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            proj_a = _mkproj(base, "proj-a", subdirs=["node_modules"])
            proj_b = _mkproj(base, "proj-b", subdirs=["node_modules"])
            code, out, _ = _scan_dir(base)
        self.assertEqual(code, 0)
        roots = sorted(p["root"] for p in out["projects"])
        self.assertEqual(roots, sorted([str(proj_a), str(proj_b)]))
        self.assertEqual(len(out["projects"]), 2)

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
        def fake_run(cmd, **kw):
            root = cmd[1]
            if "first" in root:
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=30)
            return mock.MagicMock(returncode=0, stdout="", stderr="")

        with mock.patch.object(scan_projects.subprocess, "run", side_effect=fake_run):
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
        def fake_run(cmd, **kw):
            return mock.MagicMock(returncode=1, stdout="", stderr="Permission denied")

        with mock.patch.object(scan_projects.subprocess, "run", side_effect=fake_run):
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
