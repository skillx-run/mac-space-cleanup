#!/usr/bin/env python3
"""scan_projects.py — find user project roots and enumerate cleanable artifact subdirs.

A project root is any directory that contains a `.git` directory. Inside such
a root, certain conventional subdirectories (node_modules, target, build, ...)
are reproducible from source and safe to clean (subject to risk grading in
references/category-rules.md §10). Virtual environments (.venv, venv, env)
are surfaced separately because they may contain wheel pins that no longer
build cleanly.

This script does NOT compute sizes — that is collect_sizes.py's job. The
agent is expected to feed the artifact paths from this script's output into
collect_sizes.py before grading.

stdin:  {"roots": ["~", ...], "max_depth": 6}    # both keys optional
stdout: {
  "projects": [
    {"root": "...", "markers_found": [...], "artifacts": [
      {"path": "...", "subtype": "node_modules", "kind": "deletable"},
      ...
    ]}, ...
  ],
  "stats": {
    "projects_found": int,
    "artifacts_total": int,
    "errors": [{"root": str, "kind": "timeout|permission|other", "detail": str}]
  }
}
exit:   0 ok / 1 partial errors / 2 bad input
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

DEFAULT_ROOTS = ["~"]
DEFAULT_MAX_DEPTH = 6
FIND_TIMEOUT_SECONDS = 30
MAX_WORKERS = 4

# Error `kind` values surfaced via stats.errors[]. Keep aligned with the
# schema documented in the module docstring.
ERROR_TIMEOUT = "timeout"
ERROR_PERMISSION = "permission"
ERROR_OTHER = "other"

# Artifact `kind` values surfaced per artifact entry.
KIND_DELETABLE = "deletable"
KIND_VENV = "venv"

# Directories under each search root to prune from the find walk. These are
# system / package-manager caches that may contain cloned repos with .git
# (e.g. Homebrew taps, cocoapods specs, cargo registry checkouts) — they
# would masquerade as "user projects" otherwise.
PRUNE_RELATIVE = [
    "Library",
    ".cache",
    ".npm",
    ".pnpm-store",
    ".cocoapods",
    ".cargo",
    ".rustup",
    ".gradle",
    ".m2",
    ".gem",
    ".bundle",
    ".local",
    ".Trash",
]

# Files at the project root used to detect what kind of project it is. Used
# by the agent (via `markers_found`) to decide ambiguous subtypes (vendor
# only matters for Go; env only matters when there's a Python marker).
# Keep in sync with the marker list in references/cleanup-scope.md
# §"Project artifacts allowlist".
PROJECT_MARKERS = (
    "go.mod",
    "package.json",
    "Cargo.toml",
    "pyproject.toml",
    "requirements.txt",
    "setup.py",
    "Package.swift",
    "Gemfile",
    "composer.json",
    "pubspec.yaml",
)

# Conventional artifact subdirectory names. Order matters only for output
# stability (we emit in this order per project).
ARTIFACT_SUBTYPES_DELETABLE = (
    "node_modules",
    "target",
    "build",
    "dist",
    "out",
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".turbo",
    ".parcel-cache",
    "__pycache__",
    ".pytest_cache",
    ".tox",
    "Pods",
    "vendor",  # agent verifies go.mod presence
)

ARTIFACT_SUBTYPES_VENV = (
    ".venv",
    "venv",
    "env",  # agent verifies Python marker presence
)


def _build_find_cmd(root: str, max_depth: int) -> list[str]:
    """Construct: find <root> -maxdepth N \( -path A -o -path B ... \) -prune -o -type d -name .git -print"""
    cmd = ["find", root, "-maxdepth", str(max_depth)]
    if PRUNE_RELATIVE:
        cmd.append("(")
        for i, sub in enumerate(PRUNE_RELATIVE):
            if i:
                cmd.append("-o")
            cmd.extend(["-path", os.path.join(root, sub)])
        cmd.extend([")", "-prune", "-o"])
    cmd.extend(["-type", "d", "-name", ".git", "-print"])
    return cmd


def _find_git_dirs(root: str, max_depth: int) -> tuple[list[str], dict[str, str] | None]:
    """Return (git_dir_paths, error). error is None on success."""
    cmd = _build_find_cmd(root, max_depth)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=FIND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return [], {"root": root, "kind": ERROR_TIMEOUT,
                    "detail": f"find timed out after {FIND_TIMEOUT_SECONDS}s"}
    except OSError as e:
        return [], {"root": root, "kind": ERROR_OTHER,
                    "detail": f"find spawn failed: {e}"}

    # find may emit some "Permission denied" lines on stderr but still
    # return useful results. Treat rc != 0 as partial unless stdout is empty.
    paths = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    if proc.returncode != 0 and not paths:
        return [], {"root": root, "kind": ERROR_PERMISSION,
                    "detail": f"find rc={proc.returncode}: {proc.stderr.strip()[:200]}"}
    return paths, None


def _dedup_submodules(git_dirs: list[str]) -> list[str]:
    """Sort by path length asc; drop any .git whose project root sits under
    an already-accepted project root."""
    project_roots: list[str] = []
    accepted: list[str] = []
    # Sort by path length so outer .git is seen before any nested ones.
    for git_dir in sorted(git_dirs, key=len):
        proj_root = os.path.dirname(git_dir)
        # skip if this project root sits under (or equals) any accepted root
        if any(
            proj_root == r or proj_root.startswith(r + os.sep)
            for r in project_roots
        ):
            continue
        project_roots.append(proj_root)
        accepted.append(git_dir)
    return accepted


def _detect_markers(project_root: str) -> list[str]:
    """Return sorted list of project-marker filenames found at the root."""
    found: list[str] = []
    for marker in PROJECT_MARKERS:
        if os.path.isfile(os.path.join(project_root, marker)):
            found.append(marker)
    found.sort()
    return found


def _enumerate_artifacts(project_root: str) -> list[dict[str, str]]:
    """Return artifact dicts for every conventional subdir that exists."""
    artifacts: list[dict[str, str]] = []
    for sub in ARTIFACT_SUBTYPES_DELETABLE:
        full = os.path.join(project_root, sub)
        if os.path.isdir(full) and not os.path.islink(full):
            artifacts.append({"path": full, "subtype": sub, "kind": KIND_DELETABLE})
    for sub in ARTIFACT_SUBTYPES_VENV:
        full = os.path.join(project_root, sub)
        if os.path.isdir(full) and not os.path.islink(full):
            artifacts.append({"path": full, "subtype": sub, "kind": KIND_VENV})
    return artifacts


def scan(roots: list[str], max_depth: int) -> dict[str, Any]:
    expanded_roots: list[str] = []
    seen: set[str] = set()
    for r in roots:
        e = os.path.expanduser(r)
        if e and e not in seen:
            expanded_roots.append(e)
            seen.add(e)

    all_git_dirs: list[str] = []
    errors: list[dict[str, str]] = []

    if not expanded_roots:
        return {"projects": [], "stats": {"projects_found": 0, "artifacts_total": 0, "errors": []}}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_find_git_dirs, r, max_depth): r for r in expanded_roots}
        for fut in as_completed(futures):
            r = futures[fut]
            try:
                paths, err = fut.result()
            except Exception as e:  # defensive
                errors.append({"root": r, "kind": ERROR_OTHER,
                               "detail": f"worker crashed: {e}"})
                continue
            if err:
                errors.append(err)
            all_git_dirs.extend(paths)

    # Dedup duplicate .git paths (same root listed twice, etc.) before
    # submodule detection.
    unique_git_dirs = sorted(set(all_git_dirs))
    accepted_git_dirs = _dedup_submodules(unique_git_dirs)

    projects: list[dict[str, Any]] = []
    artifacts_total = 0
    for git_dir in accepted_git_dirs:
        proj_root = os.path.dirname(git_dir)
        markers = _detect_markers(proj_root)
        arts = _enumerate_artifacts(proj_root)
        artifacts_total += len(arts)
        projects.append({
            "root": proj_root,
            "markers_found": markers,
            "artifacts": arts,
        })

    projects.sort(key=lambda p: p["root"])

    return {
        "projects": projects,
        "stats": {
            "projects_found": len(projects),
            "artifacts_total": artifacts_total,
            "errors": errors,
        },
    }


def run(argv: list[str] | None = None) -> int:
    # No argparse — single-purpose stdin tool, matches collect_sizes.py style.
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except (json.JSONDecodeError, ValueError) as e:
        print(f"invalid stdin JSON: {e}", file=sys.stderr)
        return 2

    roots = payload.get("roots", DEFAULT_ROOTS)
    max_depth = payload.get("max_depth", DEFAULT_MAX_DEPTH)

    if not isinstance(roots, list):
        print("roots must be a list", file=sys.stderr)
        return 2
    if not isinstance(max_depth, int) or max_depth < 0:
        print("max_depth must be a non-negative int", file=sys.stderr)
        return 2

    result = scan(roots, max_depth)
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 1 if result["stats"]["errors"] else 0


if __name__ == "__main__":
    sys.exit(run())
