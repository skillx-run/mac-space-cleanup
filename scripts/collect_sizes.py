#!/usr/bin/env python3
"""collect_sizes.py — parallel du/stat for a list of paths.

Reads {"paths": [...]} from stdin, runs `du -sk` and stat() for each path in
parallel, and emits a JSON list to stdout with per-path size_bytes / mtime /
exists / error. Each subprocess has a 30s timeout; failures are isolated so
one bad path does not block the others.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

TIMEOUT_SECONDS = 30
MAX_WORKERS = 8


def _stat_path(path: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": path,
        "size_bytes": 0,
        "mtime": None,
        "exists": False,
        "error": None,
    }
    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        result["error"] = "path does not exist"
        return result

    result["exists"] = True
    try:
        st = os.stat(expanded, follow_symlinks=False)
        result["mtime"] = int(st.st_mtime)
    except OSError as e:
        result["error"] = f"stat failed: {e}"
        return result

    try:
        proc = subprocess.run(
            ["du", "-sk", expanded],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        result["error"] = "timeout"
        return result
    except OSError as e:
        result["error"] = f"du spawn failed: {e}"
        return result

    if proc.returncode != 0:
        result["error"] = f"du rc={proc.returncode}: {proc.stderr.strip()[:200]}"
        return result

    # `du -sk` output: "<KB>\t<path>"
    token = proc.stdout.strip().split("\t", 1)[0] if proc.stdout else ""
    try:
        kb = int(token)
        result["size_bytes"] = kb * 1024
    except ValueError:
        result["error"] = f"could not parse du output: {proc.stdout[:200]!r}"

    return result


def run(argv: list[str] | None = None) -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"invalid stdin JSON: {e}", file=sys.stderr)
        return 2

    paths = payload.get("paths")
    if not isinstance(paths, list):
        print("paths must be a list", file=sys.stderr)
        return 2

    # Dedup while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for p in paths:
        if isinstance(p, str) and p not in seen:
            ordered.append(p)
            seen.add(p)

    results_by_path: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_stat_path, p): p for p in ordered}
        for fut in as_completed(futures):
            p = futures[fut]
            try:
                results_by_path[p] = fut.result()
            except Exception as e:  # defensive: thread-level escape
                results_by_path[p] = {
                    "path": p,
                    "size_bytes": 0,
                    "mtime": None,
                    "exists": False,
                    "error": f"worker crashed: {e}",
                }

    out = [results_by_path[p] for p in ordered]
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")

    any_failed = any(r.get("error") for r in out)
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(run())
