#!/usr/bin/env python3
"""safe_delete.py — unified controlled dispatcher for mac-space-clean.

Reads a confirmed.json from stdin, dispatches each item to one of:
  delete / trash / archive / migrate / defer / skip
and appends one ActionRecord per item to <workdir>/actions.jsonl.

The agent must route every cleanup write through this script; agents must
not call rm/mv/trash directly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ALLOWED_ACTIONS = {"delete", "trash", "archive", "migrate", "defer", "skip"}
STATUS_SUCCESS = "success"
STATUS_ARCHIVE_ONLY = "archive_only_success"
STATUS_FAILED = "failed"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _emit_error(msg: str) -> None:
    print(msg, file=sys.stderr)


def _size_of(path: str) -> int:
    """Return directory/file size in bytes, or 0 if unreadable."""
    if not os.path.exists(path):
        return 0
    if os.path.isfile(path) or os.path.islink(path):
        try:
            return os.path.getsize(path)
        except OSError:
            return 0
    total = 0
    for root, _, files in os.walk(path, followlinks=False):
        for name in files:
            fp = os.path.join(root, name)
            try:
                total += os.path.getsize(fp)
            except OSError:
                continue
    return total


def _append_record(workdir: Path, record: dict[str, Any]) -> None:
    actions_file = workdir / "actions.jsonl"
    with actions_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _base_record(item: dict[str, Any], action: str) -> dict[str, Any]:
    return {
        "item_id": item.get("id"),
        "path": item.get("path"),
        "action": action,
        "size_before_bytes": int(item.get("size_bytes") or 0),
        "status": STATUS_SUCCESS,
        "error": None,
        "duration_ms": 0,
        "trash_location": None,
        "archive_location": None,
        "migrate_destination": None,
        "timestamp": _now_ms(),
        "dry_run": False,
    }


# ---------- action handlers ----------


def _handle_delete(
    item: dict[str, Any],
    workdir: Path,
    dry_run: bool,
) -> dict[str, Any]:
    rec = _base_record(item, "delete")
    path = item.get("path") or ""
    t0 = time.monotonic()

    if item.get("category") == "system_snapshots":
        return _handle_snapshot(item, rec, dry_run, t0)

    if dry_run:
        rec["dry_run"] = True
        rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
        return rec

    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
    except FileNotFoundError:
        rec["action"] = "skip"
        rec["status"] = STATUS_SUCCESS
        rec["error"] = "already gone"
    except OSError as e:
        rec["status"] = STATUS_FAILED
        rec["error"] = f"{type(e).__name__}: {e}"

    rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
    return rec


def _handle_snapshot(
    item: dict[str, Any],
    rec: dict[str, Any],
    dry_run: bool,
    t0: float,
) -> dict[str, Any]:
    """tmutil deletelocalsnapshots <date>; path form: snapshot:com.apple.TimeMachine.YYYY-MM-DD-HHMMSS.local"""
    rec["action"] = "delete"
    raw = item.get("path") or ""
    m = re.search(r"(\d{4}-\d{2}-\d{2}-\d{6})", raw)
    if not m:
        rec["status"] = STATUS_FAILED
        rec["error"] = f"cannot parse snapshot date from: {raw}"
        rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
        return rec
    date_token = m.group(1)

    if dry_run:
        rec["dry_run"] = True
        rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
        return rec

    try:
        subprocess.run(
            ["tmutil", "deletelocalsnapshots", date_token],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        rec["status"] = STATUS_FAILED
        rec["error"] = f"tmutil failed: {e}"

    rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
    return rec


def _handle_trash(
    item: dict[str, Any],
    workdir: Path,
    dry_run: bool,
) -> dict[str, Any]:
    rec = _base_record(item, "trash")
    path = item.get("path") or ""
    t0 = time.monotonic()

    if dry_run:
        rec["dry_run"] = True
        rec["trash_location"] = str(Path.home() / ".Trash")
        rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
        return rec

    if not os.path.exists(path):
        rec["action"] = "skip"
        rec["status"] = STATUS_SUCCESS
        rec["error"] = "already gone"
        rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
        return rec

    ok, location, err = _trash_path(path)
    if ok:
        rec["trash_location"] = location
    else:
        rec["status"] = STATUS_FAILED
        rec["error"] = err

    rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
    return rec


def _trash_path(path: str) -> tuple[bool, str | None, str | None]:
    """Send path to Trash. Prefer `trash` CLI, fall back to move into ~/.Trash."""
    trash_cli = shutil.which("trash")
    if trash_cli:
        try:
            subprocess.run(
                [trash_cli, path],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return True, str(Path.home() / ".Trash"), None
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            return False, None, f"trash cli failed: {e}"

    # Fallback: shutil.move into ~/.Trash with a timestamped suffix
    trash_dir = Path.home() / ".Trash"
    trash_dir.mkdir(exist_ok=True)
    basename = os.path.basename(path.rstrip("/")) or "item"
    dest = trash_dir / f"{basename}-{int(time.time())}"
    try:
        shutil.move(path, str(dest))
        return True, str(dest), None
    except (shutil.Error, OSError) as e:
        return False, None, f"mv fallback failed: {e}"


def _handle_archive(
    item: dict[str, Any],
    workdir: Path,
    dry_run: bool,
    overrides: dict[str, Any],
) -> dict[str, Any]:
    rec = _base_record(item, "archive")
    path = item.get("path") or ""
    category = item.get("category") or "orphan"
    fmt = (overrides.get("archive_format") or "tar.gz").lower()
    if fmt != "tar.gz":
        rec["status"] = STATUS_FAILED
        rec["error"] = f"unsupported archive_format: {fmt}"
        return rec

    archive_dir = workdir / "archive" / category
    basename = os.path.basename(path.rstrip("/")) or "item"
    archive_path = archive_dir / f"{basename}.tar.gz"
    rec["archive_location"] = str(archive_path)
    t0 = time.monotonic()

    if dry_run:
        rec["dry_run"] = True
        rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
        return rec

    if not os.path.exists(path):
        rec["action"] = "skip"
        rec["status"] = STATUS_SUCCESS
        rec["error"] = "already gone"
        rec["archive_location"] = None
        rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
        return rec

    archive_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: tar
    try:
        subprocess.run(
            ["tar", "czf", str(archive_path), "-C", os.path.dirname(path) or "/", basename],
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        rec["status"] = STATUS_FAILED
        rec["error"] = f"tar failed: {e}"
        rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
        return rec

    # Step 2: trash original
    ok, trash_loc, err = _trash_path(path)
    if ok:
        rec["trash_location"] = trash_loc
        rec["status"] = STATUS_SUCCESS
    else:
        rec["status"] = STATUS_ARCHIVE_ONLY
        rec["error"] = f"archive ok but trash failed: {err}"

    rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
    return rec


def _handle_migrate(
    item: dict[str, Any],
    workdir: Path,
    dry_run: bool,
    overrides: dict[str, Any],
) -> dict[str, Any]:
    rec = _base_record(item, "migrate")
    path = item.get("path") or ""
    dest = overrides.get("migrate_dest")
    t0 = time.monotonic()

    if not dest:
        rec["status"] = STATUS_FAILED
        rec["error"] = "migrate_dest missing in action_overrides"
        rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
        return rec

    rec["migrate_destination"] = dest

    if dry_run:
        rec["dry_run"] = True
        rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
        return rec

    if not os.path.exists(path):
        rec["action"] = "skip"
        rec["status"] = STATUS_SUCCESS
        rec["error"] = "already gone"
        rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
        return rec

    # Writability check on destination
    dest_dir = dest if os.path.isdir(dest) else os.path.dirname(dest) or dest
    if not os.path.exists(dest_dir):
        try:
            os.makedirs(dest_dir, exist_ok=True)
        except OSError as e:
            rec["status"] = STATUS_FAILED
            rec["error"] = f"cannot create dest: {e}"
            rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
            return rec
    if not os.access(dest_dir, os.W_OK):
        rec["status"] = STATUS_FAILED
        rec["error"] = f"dest not writable: {dest_dir}"
        rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
        return rec

    # Run rsync -a --remove-source-files
    try:
        subprocess.run(
            ["rsync", "-a", "--remove-source-files", path, dest],
            check=True,
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        rec["status"] = STATUS_FAILED
        rec["error"] = f"rsync failed: {e}"
        rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
        return rec

    # Trash the (now empty) source directory shell
    if os.path.isdir(path):
        ok, trash_loc, err = _trash_path(path)
        if ok:
            rec["trash_location"] = trash_loc
        else:
            rec["status"] = STATUS_ARCHIVE_ONLY
            rec["error"] = f"migrate ok but source shell trash failed: {err}"

    rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
    return rec


def _handle_defer(item: dict[str, Any], workdir: Path, dry_run: bool) -> dict[str, Any]:
    rec = _base_record(item, "defer")
    rec["dry_run"] = dry_run
    if not dry_run:
        deferred_file = workdir / "deferred.jsonl"
        with deferred_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return rec


def _handle_skip(item: dict[str, Any]) -> dict[str, Any]:
    rec = _base_record(item, "skip")
    rec["error"] = item.get("reason") or "user skipped"
    return rec


# ---------- main dispatch ----------


def dispatch(
    item: dict[str, Any],
    workdir: Path,
    dry_run: bool,
    overrides: dict[str, Any],
) -> dict[str, Any]:
    action = item.get("action")
    if action not in ALLOWED_ACTIONS:
        rec = _base_record(item, action or "unknown")
        rec["status"] = STATUS_FAILED
        rec["error"] = f"unknown action: {action}"
        return rec

    # Idempotency pre-check (skip for defer/skip which don't touch fs)
    path = item.get("path") or ""
    if action in {"delete", "trash", "archive", "migrate"}:
        is_snapshot = item.get("category") == "system_snapshots"
        if not is_snapshot and path and not os.path.exists(path) and not dry_run:
            rec = _base_record(item, "skip")
            rec["error"] = "already gone"
            return rec

    if action == "delete":
        return _handle_delete(item, workdir, dry_run)
    if action == "trash":
        return _handle_trash(item, workdir, dry_run)
    if action == "archive":
        return _handle_archive(item, workdir, dry_run, overrides)
    if action == "migrate":
        return _handle_migrate(item, workdir, dry_run, overrides)
    if action == "defer":
        return _handle_defer(item, workdir, dry_run)
    # action == "skip"
    return _handle_skip(item)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="mac-space-clean safe dispatcher")
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    workdir: Path = args.workdir
    workdir.mkdir(parents=True, exist_ok=True)

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as e:
        _emit_error(f"invalid stdin JSON: {e}")
        return 2

    items = payload.get("confirmed_items") or []
    overrides_map = payload.get("action_overrides") or {}

    if not isinstance(items, list):
        _emit_error("confirmed_items must be a list")
        return 2

    records: list[dict[str, Any]] = []
    reclaimed = 0
    deferred = 0
    failed = 0
    archive_only = 0

    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id") or hashlib.sha1(
            (item.get("path") or "").encode()
        ).hexdigest()[:12]
        item["id"] = item_id
        overrides = overrides_map.get(item_id) or {}

        rec = dispatch(item, workdir, args.dry_run, overrides)
        _append_record(workdir, rec)
        records.append(rec)

        status = rec.get("status")
        action = rec.get("action")

        if action == "defer":
            deferred += 1
        elif status == STATUS_FAILED:
            failed += 1
        elif status == STATUS_ARCHIVE_ONLY:
            archive_only += 1
        elif action in {"delete", "trash", "archive", "migrate"} and status == STATUS_SUCCESS:
            size = rec.get("size_before_bytes") or 0
            if args.dry_run:
                reclaimed += size
            elif action == "archive":
                reclaimed += size
            else:
                reclaimed += size

    summary = {
        "records": records,
        "reclaimed_bytes": reclaimed,
        "deferred_count": deferred,
        "failed_count": failed,
        "archive_only_count": archive_only,
    }
    json.dump(summary, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")

    if failed or archive_only:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
