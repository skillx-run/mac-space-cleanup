#!/usr/bin/env python3
"""safe_delete.py — unified controlled dispatcher for mac-space-clean.

Reads a confirmed.json from stdin, dispatches each item to one of:
  delete / trash / archive / migrate / defer / skip
and appends one ActionRecord per item to <workdir>/actions.jsonl.

The agent must route every cleanup write through this script; agents must
not call rm/mv/trash directly.

Reclaim accounting (stdout summary fields)
------------------------------------------
- ``freed_now_bytes``       sum of ``size_before_bytes`` for successful
                            ``delete`` (incl. specialised
                            ``system_snapshots`` / ``sim_runtime``) and
                            successful ``migrate`` items. These bytes are
                            already off the disk.
- ``pending_in_trash_bytes`` sum for successful ``trash`` and the
                            originals of fully-successful ``archive``
                            items. Disk is *not* yet released — user must
                            empty ~/.Trash.
- ``archived_source_bytes`` sum of original sizes for fully-successful
                            ``archive`` items (the .tar.gz files live in
                            the workdir; we report source size, not tar
                            size, to avoid an extra stat).
- ``archived_count``        count of fully-successful ``archive`` items.
- ``reclaimed_bytes``       deprecated back-compat alias =
                            freed_now_bytes + pending_in_trash_bytes.
                            Kept for v0.1 consumers; new code should use
                            the split fields.

``status=archive_only_success`` items contribute to none of the above
(they are surfaced via ``archive_only_count`` and the report's deferred
section so the user can recover the partial state manually).

Dry-run mode (``--dry-run``) accumulates the same way as a successful real
run, using ``size_before_bytes`` from the input as the estimate. So a
dry-run summary matches the upper bound a real run would reach if every
target succeeded.
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

ACTION_DELETE = "delete"
ACTION_TRASH = "trash"
ACTION_ARCHIVE = "archive"
ACTION_MIGRATE = "migrate"
ACTION_DEFER = "defer"
ACTION_SKIP = "skip"
ALLOWED_ACTIONS = {
    ACTION_DELETE, ACTION_TRASH, ACTION_ARCHIVE,
    ACTION_MIGRATE, ACTION_DEFER, ACTION_SKIP,
}
_FS_ACTIONS = {ACTION_DELETE, ACTION_TRASH, ACTION_ARCHIVE, ACTION_MIGRATE}
# Successful actions in this set are counted toward freed_now_bytes
# (already off the disk). Trash/archive go to pending_in_trash instead.
_FREED_NOW_ACTIONS = {ACTION_DELETE, ACTION_MIGRATE}

STATUS_SUCCESS = "success"
STATUS_ARCHIVE_ONLY = "archive_only_success"
STATUS_FAILED = "failed"

CATEGORY_SYSTEM_SNAPSHOTS = "system_snapshots"
CATEGORY_SIM_RUNTIME = "sim_runtime"

_SNAPSHOT_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2}-\d{6})")
_SIMCTL_UDID_RE = re.compile(r"/CoreSimulator/Devices/([0-9A-Fa-f-]{36})(?:/|$)")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _emit_error(msg: str) -> None:
    print(msg, file=sys.stderr)


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


def _finalize(rec: dict[str, Any], t0: float, *, dry_run: bool = False) -> dict[str, Any]:
    """Stamp duration_ms (and dry_run flag) onto a record about to be returned."""
    if dry_run:
        rec["dry_run"] = True
    rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
    return rec


# ---------- action handlers ----------


def _handle_delete(item: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    rec = _base_record(item, ACTION_DELETE)
    t0 = time.monotonic()
    if dry_run:
        return _finalize(rec, t0, dry_run=True)

    path = item.get("path") or ""
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
    except OSError as e:
        rec["status"] = STATUS_FAILED
        rec["error"] = f"{type(e).__name__}: {e}"
    return _finalize(rec, t0)


def _handle_snapshot_delete(item: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    """tmutil deletelocalsnapshots <date>; path form: snapshot:<...YYYY-MM-DD-HHMMSS...>"""
    rec = _base_record(item, ACTION_DELETE)
    t0 = time.monotonic()
    raw = item.get("path") or ""
    m = _SNAPSHOT_DATE_RE.search(raw)
    if not m:
        rec["status"] = STATUS_FAILED
        rec["error"] = f"cannot parse snapshot date from: {raw}"
        return _finalize(rec, t0)

    if dry_run:
        return _finalize(rec, t0, dry_run=True)

    try:
        subprocess.run(
            ["tmutil", "deletelocalsnapshots", m.group(1)],
            check=True, capture_output=True, text=True, timeout=60,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        rec["status"] = STATUS_FAILED
        rec["error"] = f"tmutil failed: {e}"
    return _finalize(rec, t0)


def _handle_simctl_delete(item: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    """xcrun simctl delete <UDID> | unavailable.

    Recognised path forms:
      - "xcrun:simctl-unavailable" (semantic) -> simctl delete unavailable
      - ".../CoreSimulator/Devices/<UDID>"    -> simctl delete <UDID>

    Apple's simctl refuses to delete a booted device, giving us the safety
    that a plain rm -rf would not.
    """
    rec = _base_record(item, ACTION_DELETE)
    t0 = time.monotonic()
    raw = item.get("path") or ""

    if raw == "xcrun:simctl-unavailable":
        target = "unavailable"
    else:
        m = _SIMCTL_UDID_RE.search(raw)
        if not m:
            rec["status"] = STATUS_FAILED
            rec["error"] = f"cannot parse simulator UDID from: {raw}"
            return _finalize(rec, t0)
        target = m.group(1)

    if dry_run:
        return _finalize(rec, t0, dry_run=True)

    try:
        subprocess.run(
            ["xcrun", "simctl", "delete", target],
            check=True, capture_output=True, text=True, timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        rec["status"] = STATUS_FAILED
        rec["error"] = f"simctl failed: {e}"
    return _finalize(rec, t0)


def _handle_trash(item: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    rec = _base_record(item, ACTION_TRASH)
    t0 = time.monotonic()
    if dry_run:
        rec["trash_location"] = str(Path.home() / ".Trash")
        return _finalize(rec, t0, dry_run=True)

    path = item.get("path") or ""
    ok, location, err = _trash_path(path)
    if ok:
        rec["trash_location"] = location
    else:
        rec["status"] = STATUS_FAILED
        rec["error"] = err
    return _finalize(rec, t0)


def _trash_path(path: str) -> tuple[bool, str | None, str | None]:
    """Send path to Trash. Prefer `trash` CLI, fall back to move into ~/.Trash."""
    trash_cli = shutil.which("trash")
    if trash_cli:
        try:
            subprocess.run(
                [trash_cli, path], check=True, capture_output=True,
                text=True, timeout=120,
            )
            return True, str(Path.home() / ".Trash"), None
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            return False, None, f"trash cli failed: {e}"

    trash_dir = Path.home() / ".Trash"
    trash_dir.mkdir(exist_ok=True)
    basename = Path(path).name or "item"
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
    rec = _base_record(item, ACTION_ARCHIVE)
    t0 = time.monotonic()

    fmt = (overrides.get("archive_format") or "tar.gz").lower()
    if fmt != "tar.gz":
        rec["status"] = STATUS_FAILED
        rec["error"] = f"unsupported archive_format: {fmt}"
        return _finalize(rec, t0)

    path = item.get("path") or ""
    category = item.get("category") or "orphan"
    archive_dir = workdir / "archive" / category
    basename = Path(path).name or "item"
    archive_path = archive_dir / f"{basename}.tar.gz"
    rec["archive_location"] = str(archive_path)

    if dry_run:
        return _finalize(rec, t0, dry_run=True)

    archive_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["tar", "czf", str(archive_path),
             "-C", os.path.dirname(path) or "/", basename],
            check=True, capture_output=True, text=True, timeout=600,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        rec["status"] = STATUS_FAILED
        rec["error"] = f"tar failed: {e}"
        return _finalize(rec, t0)

    ok, trash_loc, err = _trash_path(path)
    if ok:
        rec["trash_location"] = trash_loc
    else:
        rec["status"] = STATUS_ARCHIVE_ONLY
        rec["error"] = f"archive ok but trash failed: {err}"
    return _finalize(rec, t0)


def _handle_migrate(
    item: dict[str, Any],
    workdir: Path,
    dry_run: bool,
    overrides: dict[str, Any],
) -> dict[str, Any]:
    rec = _base_record(item, ACTION_MIGRATE)
    t0 = time.monotonic()

    dest = overrides.get("migrate_dest")
    if not dest:
        rec["status"] = STATUS_FAILED
        rec["error"] = "migrate_dest missing in action_overrides"
        return _finalize(rec, t0)

    rec["migrate_destination"] = dest
    if dry_run:
        return _finalize(rec, t0, dry_run=True)

    path = item.get("path") or ""
    dest_dir = dest if os.path.isdir(dest) else os.path.dirname(dest) or dest
    try:
        os.makedirs(dest_dir, exist_ok=True)
    except OSError as e:
        rec["status"] = STATUS_FAILED
        rec["error"] = f"cannot create dest: {e}"
        return _finalize(rec, t0)
    if not os.access(dest_dir, os.W_OK):
        rec["status"] = STATUS_FAILED
        rec["error"] = f"dest not writable: {dest_dir}"
        return _finalize(rec, t0)

    try:
        subprocess.run(
            ["rsync", "-a", "--remove-source-files", path, dest],
            check=True, capture_output=True, text=True, timeout=1800,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        rec["status"] = STATUS_FAILED
        rec["error"] = f"rsync failed: {e}"
        return _finalize(rec, t0)

    if os.path.isdir(path):
        ok, trash_loc, err = _trash_path(path)
        if ok:
            rec["trash_location"] = trash_loc
        else:
            rec["status"] = STATUS_ARCHIVE_ONLY
            rec["error"] = f"migrate ok but source shell trash failed: {err}"
    return _finalize(rec, t0)


def _handle_defer(item: dict[str, Any], workdir: Path, dry_run: bool) -> dict[str, Any]:
    rec = _base_record(item, ACTION_DEFER)
    rec["dry_run"] = dry_run
    if not dry_run:
        deferred_file = workdir / "deferred.jsonl"
        with deferred_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return rec


def _handle_skip(item: dict[str, Any]) -> dict[str, Any]:
    rec = _base_record(item, ACTION_SKIP)
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

    category = item.get("category")
    is_snapshot = category == CATEGORY_SYSTEM_SNAPSHOTS
    is_sim_runtime = category == CATEGORY_SIM_RUNTIME
    is_specialised = is_snapshot or is_sim_runtime
    path = item.get("path") or ""

    # Idempotency: if a real fs target is gone, short-circuit to skip.
    # Specialised categories (snapshots, simulators) use synthetic paths or
    # managed resources where we want the official tool's error to surface,
    # so they bypass this check.
    if (action in _FS_ACTIONS and not is_specialised
            and path and not dry_run and not os.path.exists(path)):
        rec = _base_record(item, ACTION_SKIP)
        rec["error"] = "already gone"
        return rec

    if action == ACTION_DELETE:
        if is_snapshot:
            return _handle_snapshot_delete(item, dry_run)
        if is_sim_runtime:
            return _handle_simctl_delete(item, dry_run)
        return _handle_delete(item, dry_run)
    if action == ACTION_TRASH:
        return _handle_trash(item, dry_run)
    if action == ACTION_ARCHIVE:
        return _handle_archive(item, workdir, dry_run, overrides)
    if action == ACTION_MIGRATE:
        return _handle_migrate(item, workdir, dry_run, overrides)
    if action == ACTION_DEFER:
        return _handle_defer(item, workdir, dry_run)
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
    freed_now = 0
    pending_in_trash = 0
    archived_source = 0
    archived_count = 0
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
        size = rec.get("size_before_bytes") or 0

        if action == ACTION_DEFER:
            deferred += 1
        elif status == STATUS_FAILED:
            failed += 1
        elif status == STATUS_ARCHIVE_ONLY:
            archive_only += 1
        elif status == STATUS_SUCCESS:
            if action in _FREED_NOW_ACTIONS:
                freed_now += size
            elif action == ACTION_TRASH:
                pending_in_trash += size
            elif action == ACTION_ARCHIVE:
                pending_in_trash += size
                archived_source += size
                archived_count += 1

    summary = {
        "records": records,
        "freed_now_bytes": freed_now,
        "pending_in_trash_bytes": pending_in_trash,
        "archived_source_bytes": archived_source,
        "archived_count": archived_count,
        # Back-compat: reclaimed_bytes == freed_now + pending_in_trash.
        # Prefer the split fields above; this stays for v0.1 consumers.
        "reclaimed_bytes": freed_now + pending_in_trash,
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
