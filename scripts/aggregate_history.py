#!/usr/bin/env python3
"""aggregate_history.py — cross-run confidence aggregator for mac-space-cleanup.

Walks ``~/.cache/mac-space-cleanup/run-*`` directories produced by prior
cleanup sessions, joins each run's ``actions.jsonl`` with its
``cleanup-result.json`` (by ``item_id``) to attach a ``source_label`` +
``category`` tag to every action, and aggregates into a
``(source_label, category) -> {confirmed, declined, last_ts}`` table.

Output shape (written to ``<workdir>/history.json``)::

    {
      "generated_at": "2026-04-18T00:30:16+0800",
      "runs_analyzed": 12,          # runs with a readable actions.jsonl
      "runs_without_result_json": 1, # runs whose cleanup-result.json is missing
      "runs_gc": {"kept": 20, "removed": 3, "removed_run_ids": [...]},
      "by_label": [
        {"source_label": "Gradle cache", "category": "pkg_cache",
         "confirmed": 3, "declined": 0, "last_ts": 1776443370000},
        ...
      ]
    }

Redaction contract: the output contains **no paths, no basenames,
no usernames, no project names** — only generic ``source_label`` +
``category`` tokens emitted by prior runs' classifier. The agent can
safely surface this data in the report / share text.

GC: by default keeps the most recent ``--keep`` run directories
(default 20) and removes older ones. Pass ``--no-gc`` to disable.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

DEFAULT_CACHE_ROOT = "~/.cache/mac-space-cleanup"
DEFAULT_KEEP = 20

FS_ACTIONS = {"delete", "trash", "archive", "migrate"}
DECLINED_ACTIONS = {"defer"}
IGNORED_ACTIONS = {"skip"}  # L4 record-only, not user intent

STATUS_SUCCESS = "success"
STATUS_ARCHIVE_ONLY = "archive_only_success"


def _load_result_index(run_dir: Path) -> dict[str, dict[str, str]] | None:
    """Return ``{item_id: {'source_label': ..., 'category': ...}}`` or None.

    None means the run has no readable cleanup-result.json — callers should
    skip aggregation for that run (but still count it).
    """
    result_path = run_dir / "cleanup-result.json"
    if not result_path.is_file():
        return None
    try:
        data = json.loads(result_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    items = data.get("items")
    if not isinstance(items, list):
        return None

    index: dict[str, dict[str, str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        iid = item.get("id")
        label = item.get("source_label")
        cat = item.get("category")
        if not iid or not label or not cat:
            continue
        index[str(iid)] = {"source_label": str(label), "category": str(cat)}
    return index


def _classify_action(record: dict[str, Any]) -> str | None:
    """Return 'confirmed' / 'declined' / None (for ignored actions).

    - dry_run records never reflect user intent → None.
    - failed records are treated as neutral → None.
    - skip is L4 record-only → None.
    - delete/trash/archive/migrate with success → 'confirmed'.
    - defer → 'declined' (user intentionally postponed).
    - archive_only_success is still a user-approved action → 'confirmed'.
    """
    if record.get("dry_run") is True:
        return None
    status = record.get("status")
    if status not in (STATUS_SUCCESS, STATUS_ARCHIVE_ONLY):
        return None
    action = record.get("action")
    if action in FS_ACTIONS:
        return "confirmed"
    if action in DECLINED_ACTIONS:
        return "declined"
    # ACTION_SKIP and anything unknown → ignored
    return None


def _aggregate_run(
    run_dir: Path,
    buckets: dict[tuple[str, str], dict[str, int]],
) -> tuple[bool, bool]:
    """Fold one run's actions.jsonl into ``buckets``.

    Returns ``(analyzed, had_result_json)`` — analyzed is True when we at
    least opened actions.jsonl (even if every line was ignored);
    had_result_json is True when the run also had a usable
    cleanup-result.json.
    """
    actions_path = run_dir / "actions.jsonl"
    if not actions_path.is_file():
        return (False, False)

    label_index = _load_result_index(run_dir)
    had_result = label_index is not None
    if label_index is None:
        # We still counted the run as analyzed but cannot aggregate without
        # the source_label / category tags.
        return (True, False)

    try:
        fh = actions_path.open()
    except OSError:
        return (False, False)

    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # Corrupt single line — skip, continue parsing the rest.
                continue
            if not isinstance(record, dict):
                continue
            bucket_key = _classify_action(record)
            if bucket_key is None:
                continue
            iid = record.get("item_id")
            if not iid:
                continue
            tag = label_index.get(str(iid))
            if tag is None:
                continue

            key = (tag["source_label"], tag["category"])
            bucket = buckets.setdefault(
                key, {"confirmed": 0, "declined": 0, "last_ts": 0}
            )
            bucket[bucket_key] += 1
            ts = record.get("timestamp")
            if isinstance(ts, (int, float)) and ts > bucket["last_ts"]:
                bucket["last_ts"] = int(ts)

    return (True, had_result)


def _list_run_dirs(cache_root: Path) -> list[Path]:
    """List existing ``run-*`` directories under cache_root, newest first.

    Non-directories, symlinks, and names that don't start with ``run-``
    are ignored — this avoids collateral damage to test / smoke / dry-e2e
    scratch dirs the harness creates with different prefixes.
    """
    if not cache_root.is_dir():
        return []
    results: list[Path] = []
    for entry in cache_root.iterdir():
        if not entry.name.startswith("run-"):
            continue
        if entry.is_symlink():
            continue
        if not entry.is_dir():
            continue
        results.append(entry)
    results.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return results


def _gc(
    cache_root: Path,
    keep: int,
    protect: Path | None,
) -> dict[str, Any]:
    """Remove run-* dirs beyond the most-recent ``keep``; never touch ``protect``.

    Returns a summary dict with ``kept`` / ``removed`` / ``removed_run_ids``.
    """
    protected_resolved: Path | None = None
    if protect is not None:
        try:
            protected_resolved = protect.resolve(strict=False)
        except OSError:
            protected_resolved = None

    runs = _list_run_dirs(cache_root)
    keepers = runs[:keep]
    removed_ids: list[str] = []
    for doomed in runs[keep:]:
        if protected_resolved is not None:
            try:
                if doomed.resolve(strict=False) == protected_resolved:
                    # Caller's current workdir is pinned regardless of age.
                    keepers.append(doomed)
                    continue
            except OSError:
                pass
        try:
            shutil.rmtree(doomed)
            removed_ids.append(doomed.name)
        except OSError:
            # Swallow GC failures — history.json is the primary output;
            # stale dirs are a minor cost.
            continue
    return {
        "kept": len(keepers),
        "removed": len(removed_ids),
        "removed_run_ids": removed_ids,
    }


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--workdir",
        required=True,
        help="Current run's workdir. history.json is written here.",
    )
    parser.add_argument(
        "--cache-root",
        default=DEFAULT_CACHE_ROOT,
        help=f"Root under which run-* directories live (default: {DEFAULT_CACHE_ROOT}).",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=DEFAULT_KEEP,
        help=f"How many most-recent run-* dirs to keep (default: {DEFAULT_KEEP}).",
    )
    parser.add_argument(
        "--no-gc",
        action="store_true",
        help="Aggregate only; do not remove older run-* directories.",
    )
    args = parser.parse_args(argv)

    workdir = Path(os.path.expanduser(args.workdir))
    if not workdir.is_dir():
        print(f"workdir not found: {workdir}", file=sys.stderr)
        return 1

    cache_root = Path(os.path.expanduser(args.cache_root))

    buckets: dict[tuple[str, str], dict[str, int]] = {}
    runs_analyzed = 0
    runs_without_result = 0
    for run_dir in _list_run_dirs(cache_root):
        analyzed, had_result = _aggregate_run(run_dir, buckets)
        if analyzed:
            runs_analyzed += 1
            if not had_result:
                runs_without_result += 1

    if args.no_gc:
        gc_summary = {"kept": runs_analyzed, "removed": 0, "removed_run_ids": []}
    else:
        gc_summary = _gc(cache_root, args.keep, protect=workdir)

    by_label = [
        {
            "source_label": label,
            "category": cat,
            "confirmed": v["confirmed"],
            "declined": v["declined"],
            "last_ts": v["last_ts"],
        }
        for (label, cat), v in sorted(buckets.items())
    ]

    output = {
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "runs_analyzed": runs_analyzed,
        "runs_without_result_json": runs_without_result,
        "runs_gc": gc_summary,
        "by_label": by_label,
    }

    history_path = workdir / "history.json"
    history_path.write_text(json.dumps(output, indent=2))
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(run())
