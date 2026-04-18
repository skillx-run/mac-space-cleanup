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
# Actions that reflect neither approval nor rejection of an item.
# ``skip`` covers L4 record-only; any future record-only disposition
# should be added here so _classify_action filters it explicitly.
IGNORED_ACTIONS = {"skip"}

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
    - IGNORED_ACTIONS (skip and friends) → None, filtered explicitly.
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
    if action in IGNORED_ACTIONS:
        return None
    if action in FS_ACTIONS:
        return "confirmed"
    if action in DECLINED_ACTIONS:
        return "declined"
    # Unknown action names fall through to ignored; keeps the function
    # robust against future schema additions in safe_delete.py.
    return None


def _aggregate_run(
    run_dir: Path,
    buckets: dict[tuple[str, str], dict[str, int]],
) -> tuple[bool, bool]:
    """Fold one run's actions.jsonl into ``buckets``.

    Returns ``(analyzed, had_result_json)`` — analyzed is True when the
    run has an ``actions.jsonl`` file on disk (even if we cannot open or
    parse it, and even if every line is later ignored); had_result_json
    is True when the run also had a usable ``cleanup-result.json`` whose
    items[] we could index for source_label / category tagging.

    Runs where actions.jsonl cannot be opened (permission denied, etc.)
    are still counted as ``analyzed`` so the caller can tell them apart
    from runs that were missing the file entirely.
    """
    actions_path = run_dir / "actions.jsonl"
    if not actions_path.is_file():
        return (False, False)

    label_index = _load_result_index(run_dir)
    had_result = label_index is not None
    if label_index is None:
        return (True, False)

    try:
        fh = actions_path.open()
    except OSError:
        # File existed but is unreadable — count the run as analyzed
        # (with had_result reflecting whether we at least got the index)
        # instead of silently dropping it.
        return (True, had_result)

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

    Returns a summary dict with ``kept`` / ``removed`` / ``removed_run_ids``
    where both counts are in units of physical ``run-*`` directories —
    ``kept + removed`` equals the total number of ``run-*`` dirs that
    existed before GC (and ``kept`` equals the number that still exist
    after GC, which includes the pinned ``protect`` dir even if it was
    older than the ``keep`` cutoff).
    """
    protected_resolved: Path | None = None
    if protect is not None:
        try:
            protected_resolved = protect.resolve(strict=False)
        except OSError:
            protected_resolved = None

    runs = _list_run_dirs(cache_root)
    survivors: set[Path] = set(runs[:keep])
    removed_ids: list[str] = []
    for doomed in runs[keep:]:
        if protected_resolved is not None:
            try:
                if doomed.resolve(strict=False) == protected_resolved:
                    # Caller's current workdir is pinned regardless of age.
                    survivors.add(doomed)
                    continue
            except OSError:
                pass
        try:
            shutil.rmtree(doomed)
            removed_ids.append(doomed.name)
        except OSError:
            # Swallow GC failures — history.json is the primary output;
            # stale dirs are a minor cost. The dir is still on disk, so
            # it counts as a survivor for bookkeeping purposes.
            survivors.add(doomed)
            continue
    return {
        "kept": len(survivors),
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
        # Match the --gc branch's unit: count physical run-* dirs on disk.
        gc_summary = {
            "kept": len(_list_run_dirs(cache_root)),
            "removed": 0,
            "removed_run_ids": [],
        }
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
