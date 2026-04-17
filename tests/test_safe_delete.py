"""Tests for scripts/safe_delete.py.

All tests use tempfile.TemporaryDirectory for workdir and payloads; no real
filesystem mutation outside the temp tree. subprocess and shutil.which calls
are mocked to avoid depending on the host having `trash`, `tar`, `rsync`,
`tmutil`, etc.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import safe_delete  # noqa: E402


def _write_file(p: Path, size: int = 100) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)


def _run_with_payload(payload: dict, workdir: Path, dry_run: bool = False) -> tuple[int, dict, str]:
    """Run safe_delete.run() with a JSON payload on stdin. Returns (exit, stdout_obj, stderr)."""
    argv = ["--workdir", str(workdir)]
    if dry_run:
        argv.append("--dry-run")

    stdin = io.StringIO(json.dumps(payload))
    stdout = io.StringIO()
    stderr = io.StringIO()
    with mock.patch.object(sys, "stdin", stdin), mock.patch.object(
        sys, "stdout", stdout
    ), mock.patch.object(sys, "stderr", stderr):
        exit_code = safe_delete.run(argv)
    stdout.seek(0)
    out_text = stdout.getvalue()
    try:
        obj = json.loads(out_text)
    except json.JSONDecodeError:
        obj = {"_raw": out_text}
    return exit_code, obj, stderr.getvalue()


class TestDispatch(unittest.TestCase):
    def test_delete_real_file(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            target = Path(td) / "victim.txt"
            _write_file(target, 500)
            payload = {
                "confirmed_items": [
                    {"id": "t1", "path": str(target), "action": "delete",
                     "size_bytes": 500, "category": "app_cache",
                     "risk_level": "L1", "reason": "test"}
                ]
            }
            code, out, _ = _run_with_payload(payload, work)
            self.assertEqual(code, 0)
            self.assertFalse(target.exists())
            self.assertEqual(out["reclaimed_bytes"], 500)
            self.assertEqual(out["freed_now_bytes"], 500)
            self.assertEqual(out["pending_in_trash_bytes"], 0)
            self.assertEqual(out["archived_source_bytes"], 0)
            self.assertEqual(out["archived_count"], 0)
            self.assertEqual(out["records"][0]["status"], "success")

    def test_trash_uses_cli_when_available(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            target = Path(td) / "cached.bin"
            _write_file(target, 200)

            def fake_run(cmd, **kw):
                # Simulate trash CLI success and actually remove the file so
                # post-run assertions see the effect.
                if os.path.basename(cmd[0]) == "trash":
                    os.remove(cmd[1])
                    return mock.Mock(returncode=0, stdout="", stderr="")
                raise AssertionError(f"unexpected subprocess call: {cmd}")

            with mock.patch.object(safe_delete.shutil, "which", return_value="/usr/local/bin/trash"), \
                 mock.patch.object(safe_delete.subprocess, "run", side_effect=fake_run) as m_run:
                payload = {
                    "confirmed_items": [
                        {"id": "t2", "path": str(target), "action": "trash",
                         "size_bytes": 200, "category": "app_cache",
                         "risk_level": "L2", "reason": "test"}
                    ]
                }
                code, out, _ = _run_with_payload(payload, work)

            self.assertEqual(code, 0)
            self.assertEqual(out["records"][0]["status"], "success")
            self.assertIsNotNone(out["records"][0]["trash_location"])
            self.assertEqual(out["freed_now_bytes"], 0)
            self.assertEqual(out["pending_in_trash_bytes"], 200)
            m_run.assert_called_once()

    def test_trash_falls_back_to_move_when_no_cli(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            target = Path(td) / "fallback.bin"
            _write_file(target, 300)
            fake_home = Path(td) / "fakehome"
            fake_home.mkdir()

            with mock.patch.object(safe_delete.shutil, "which", return_value=None), \
                 mock.patch.object(safe_delete.Path, "home", return_value=fake_home):
                payload = {
                    "confirmed_items": [
                        {"id": "t3", "path": str(target), "action": "trash",
                         "size_bytes": 300, "category": "app_cache",
                         "risk_level": "L2", "reason": "test"}
                    ]
                }
                code, out, _ = _run_with_payload(payload, work)

            self.assertEqual(code, 0)
            self.assertFalse(target.exists())
            trashed = list((fake_home / ".Trash").iterdir())
            self.assertEqual(len(trashed), 1)
            self.assertIn("fallback.bin", trashed[0].name)
            self.assertEqual(out["pending_in_trash_bytes"], 300)
            self.assertEqual(out["freed_now_bytes"], 0)

    def test_archive_success_full(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            target = Path(td) / "pile"
            target.mkdir()
            _write_file(target / "a.bin", 400)

            run_log: list[list[str]] = []

            def fake_run(cmd, **kw):
                run_log.append(cmd)
                if cmd[0] == "tar":
                    Path(cmd[2]).parent.mkdir(parents=True, exist_ok=True)
                    Path(cmd[2]).write_bytes(b"TAR")
                    return mock.Mock(returncode=0, stdout="", stderr="")
                if os.path.basename(cmd[0]) == "trash":
                    import shutil as _sh
                    _sh.rmtree(cmd[1])
                    return mock.Mock(returncode=0, stdout="", stderr="")
                raise AssertionError(f"unexpected cmd: {cmd}")

            with mock.patch.object(safe_delete.shutil, "which", return_value="/usr/bin/trash"), \
                 mock.patch.object(safe_delete.subprocess, "run", side_effect=fake_run):
                payload = {
                    "confirmed_items": [
                        {"id": "ar1", "path": str(target), "action": "archive",
                         "size_bytes": 400, "category": "downloads",
                         "risk_level": "L3", "reason": "big archive"}
                    ]
                }
                code, out, _ = _run_with_payload(payload, work)

            self.assertEqual(code, 0)
            rec = out["records"][0]
            self.assertEqual(rec["status"], "success")
            self.assertTrue(rec["archive_location"].endswith("pile.tar.gz"))
            self.assertIsNotNone(rec["trash_location"])
            self.assertFalse(target.exists())
            self.assertEqual(out["pending_in_trash_bytes"], 400)
            self.assertEqual(out["archived_source_bytes"], 400)
            self.assertEqual(out["archived_count"], 1)
            self.assertEqual(out["freed_now_bytes"], 0)

    def test_archive_only_success_when_trash_fails(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            target = Path(td) / "bigthing"
            target.mkdir()
            _write_file(target / "data.bin", 500)

            def fake_run(cmd, **kw):
                if cmd[0] == "tar":
                    Path(cmd[2]).parent.mkdir(parents=True, exist_ok=True)
                    Path(cmd[2]).write_bytes(b"TAR")
                    return mock.Mock(returncode=0, stdout="", stderr="")
                if os.path.basename(cmd[0]) == "trash":
                    import subprocess as _sp
                    raise _sp.CalledProcessError(1, cmd, stderr="boom")
                raise AssertionError(f"unexpected cmd: {cmd}")

            with mock.patch.object(safe_delete.shutil, "which", return_value="/usr/bin/trash"), \
                 mock.patch.object(safe_delete.subprocess, "run", side_effect=fake_run), \
                 mock.patch.object(safe_delete.shutil, "move", side_effect=OSError("move denied")):
                payload = {
                    "confirmed_items": [
                        {"id": "ar2", "path": str(target), "action": "archive",
                         "size_bytes": 500, "category": "downloads",
                         "risk_level": "L3", "reason": "t"}
                    ]
                }
                code, out, _ = _run_with_payload(payload, work)

            self.assertEqual(code, 1)  # archive_only triggers non-zero exit
            rec = out["records"][0]
            self.assertEqual(rec["status"], "archive_only_success")
            self.assertTrue(rec["archive_location"])
            self.assertIsNotNone(rec["error"])
            # No metric counts the partial state.
            self.assertEqual(out["reclaimed_bytes"], 0)
            self.assertEqual(out["freed_now_bytes"], 0)
            self.assertEqual(out["pending_in_trash_bytes"], 0)
            self.assertEqual(out["archived_source_bytes"], 0)
            self.assertEqual(out["archived_count"], 0)
            self.assertEqual(out["archive_only_count"], 1)

    def test_system_snapshots_invokes_tmutil(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            calls: list[list[str]] = []

            def fake_run(cmd, **kw):
                calls.append(cmd)
                if cmd[0] == "tmutil":
                    return mock.Mock(returncode=0, stdout="", stderr="")
                raise AssertionError(f"unexpected cmd: {cmd}")

            with mock.patch.object(safe_delete.subprocess, "run", side_effect=fake_run):
                payload = {
                    "confirmed_items": [
                        {"id": "snap1",
                         "path": "snapshot:com.apple.TimeMachine.2026-04-16-024706.local",
                         "action": "delete",
                         "size_bytes": 0,
                         "category": "system_snapshots",
                         "risk_level": "L2",
                         "reason": "old snapshot"}
                    ]
                }
                code, out, _ = _run_with_payload(payload, work)

            self.assertEqual(code, 0)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], "tmutil")
            self.assertEqual(calls[0][1], "deletelocalsnapshots")
            self.assertEqual(calls[0][2], "2026-04-16-024706")
            self.assertEqual(out["records"][0]["status"], "success")

    def test_simctl_unavailable_invokes_xcrun(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            calls: list[list[str]] = []

            def fake_run(cmd, **kw):
                calls.append(cmd)
                if cmd[0] == "xcrun":
                    return mock.Mock(returncode=0, stdout="", stderr="")
                raise AssertionError(f"unexpected cmd: {cmd}")

            with mock.patch.object(safe_delete.subprocess, "run", side_effect=fake_run), \
                 mock.patch.object(safe_delete.os, "remove") as m_remove, \
                 mock.patch.object(safe_delete.shutil, "rmtree") as m_rmtree:
                payload = {
                    "confirmed_items": [
                        {"id": "sim1",
                         "path": "xcrun:simctl-unavailable",
                         "action": "delete",
                         "size_bytes": 0,
                         "category": "sim_runtime",
                         "risk_level": "L1",
                         "reason": "unavailable runtimes"}
                    ]
                }
                code, out, _ = _run_with_payload(payload, work)

            self.assertEqual(code, 0)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0], ["xcrun", "simctl", "delete", "unavailable"])
            self.assertEqual(out["records"][0]["status"], "success")
            m_remove.assert_not_called()
            m_rmtree.assert_not_called()

    def test_simctl_with_udid_path_invokes_xcrun(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            calls: list[list[str]] = []
            udid = "ABCD1234-5678-90AB-CDEF-1234567890AB"
            sim_path = f"/Users/me/Library/Developer/CoreSimulator/Devices/{udid}"

            def fake_run(cmd, **kw):
                calls.append(cmd)
                if cmd[0] == "xcrun":
                    return mock.Mock(returncode=0, stdout="", stderr="")
                raise AssertionError(f"unexpected cmd: {cmd}")

            # path doesn't exist on disk; simctl is the source of truth.
            # Specialised category bypasses the dispatch-level exists() check.
            with mock.patch.object(safe_delete.subprocess, "run", side_effect=fake_run):
                payload = {
                    "confirmed_items": [
                        {"id": "sim2", "path": sim_path, "action": "delete",
                         "size_bytes": 4_000_000_000, "category": "sim_runtime",
                         "risk_level": "L1", "reason": "old simulator"}
                    ]
                }
                code, out, _ = _run_with_payload(payload, work)

            self.assertEqual(code, 0)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0], ["xcrun", "simctl", "delete", udid])
            self.assertEqual(out["records"][0]["status"], "success")

    def test_simctl_booted_failure_propagates(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"

            def fake_run(cmd, **kw):
                if cmd[0] == "xcrun":
                    raise subprocess.CalledProcessError(
                        returncode=1, cmd=cmd, stderr="device is booted")
                raise AssertionError(f"unexpected cmd: {cmd}")

            with mock.patch.object(safe_delete.subprocess, "run", side_effect=fake_run):
                payload = {
                    "confirmed_items": [
                        {"id": "sim3", "path": "xcrun:simctl-unavailable",
                         "action": "delete", "size_bytes": 0,
                         "category": "sim_runtime", "risk_level": "L1", "reason": "t"}
                    ]
                }
                code, out, _ = _run_with_payload(payload, work)

            self.assertEqual(code, 1)
            rec = out["records"][0]
            self.assertEqual(rec["status"], "failed")
            self.assertIn("simctl failed", rec["error"])

    def test_migrate_success_full(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            target = Path(td) / "tomigrate"
            target.mkdir()
            _write_file(target / "blob", 100)
            dest = Path(td) / "ext"
            dest.mkdir()

            calls: list[list[str]] = []

            def fake_run(cmd, **kw):
                calls.append(cmd)
                if cmd[0] == "rsync":
                    return mock.Mock(returncode=0, stdout="", stderr="")
                if os.path.basename(cmd[0]) == "trash":
                    import shutil as _sh
                    _sh.rmtree(cmd[1])
                    return mock.Mock(returncode=0, stdout="", stderr="")
                raise AssertionError(f"unexpected cmd: {cmd}")

            with mock.patch.object(safe_delete.shutil, "which", return_value="/usr/bin/trash"), \
                 mock.patch.object(safe_delete.subprocess, "run", side_effect=fake_run):
                payload = {
                    "confirmed_items": [
                        {"id": "mig_ok", "path": str(target), "action": "migrate",
                         "size_bytes": 100, "category": "large_media",
                         "risk_level": "L3", "reason": "moving to ext volume"}
                    ],
                    "action_overrides": {
                        "mig_ok": {"migrate_dest": str(dest)}
                    }
                }
                code, out, _ = _run_with_payload(payload, work)

            self.assertEqual(code, 0)
            rec = out["records"][0]
            self.assertEqual(rec["status"], "success")
            self.assertEqual(rec["migrate_destination"], str(dest))
            self.assertIsNotNone(rec["trash_location"])
            self.assertFalse(target.exists())
            # migrate success counts toward freed_now (different volume).
            self.assertEqual(out["freed_now_bytes"], 100)
            self.assertEqual(out["pending_in_trash_bytes"], 0)
            # rsync must have been called with the full move semantics
            rsync_calls = [c for c in calls if c[0] == "rsync"]
            self.assertEqual(len(rsync_calls), 1)
            self.assertIn("--remove-source-files", rsync_calls[0])

    def test_blocked_pattern_refuses_delete_on_ssh(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            ssh_dir = Path(td) / ".ssh"
            ssh_dir.mkdir()
            (ssh_dir / "id_rsa").write_text("PRIVATE KEY")

            payload = {
                "confirmed_items": [
                    {"id": "ssh1", "path": str(ssh_dir),
                     "action": "delete", "size_bytes": 100,
                     "category": "app_cache", "risk_level": "L1",
                     "reason": "agent misjudgement"}
                ]
            }
            code, out, _ = _run_with_payload(payload, work)

            self.assertEqual(code, 1)
            rec = out["records"][0]
            self.assertEqual(rec["status"], "failed")
            self.assertIn("blocked by safety pattern", rec["error"])
            # Crucially, the file is still there.
            self.assertTrue((ssh_dir / "id_rsa").exists())

    def test_blocked_pattern_refuses_trash_on_keychains(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            target = Path(td) / "Library" / "Keychains" / "login.keychain-db"
            target.parent.mkdir(parents=True)
            target.write_text("KEY")

            payload = {
                "confirmed_items": [
                    {"id": "kc1", "path": str(target),
                     "action": "trash", "size_bytes": 50,
                     "category": "app_cache", "risk_level": "L2",
                     "reason": "agent thought it was a cache"}
                ]
            }
            code, out, _ = _run_with_payload(payload, work)

            self.assertEqual(code, 1)
            rec = out["records"][0]
            self.assertEqual(rec["status"], "failed")
            self.assertIn("blocked by safety pattern", rec["error"])
            self.assertTrue(target.exists())

    def test_blocked_pattern_refuses_env_file(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            target = Path(td) / ".env"
            target.write_text("SECRET=1")

            payload = {
                "confirmed_items": [
                    {"id": "env1", "path": str(target),
                     "action": "delete", "size_bytes": 10,
                     "category": "orphan", "risk_level": "L1", "reason": "t"}
                ]
            }
            code, out, _ = _run_with_payload(payload, work)

            self.assertEqual(code, 1)
            self.assertIn("blocked by safety pattern", out["records"][0]["error"])
            self.assertTrue(target.exists())

    def test_blocked_pattern_does_not_match_unrelated_paths(self):
        # Verify the regex set doesn't false-positive on adjacent names.
        from safe_delete import _is_blocked
        self.assertFalse(_is_blocked("/Users/me/Library/Caches/com.foo"))
        self.assertFalse(_is_blocked("/Users/me/Downloads/git-tutorial.pdf"))
        self.assertFalse(_is_blocked("/Users/me/Documents/notes.txt"))
        self.assertFalse(_is_blocked("/Users/me/.envvars-old.txt"))
        # And does match the protected ones
        self.assertTrue(_is_blocked("/Users/me/projects/foo/.git/objects"))
        self.assertTrue(_is_blocked("/Users/me/.ssh/config"))
        self.assertTrue(_is_blocked("/Users/me/Library/Keychains/login.keychain-db"))
        self.assertTrue(_is_blocked("/Users/me/Pictures/Photos Library.photoslibrary/originals"))
        self.assertTrue(_is_blocked("/Users/me/Documents/.env"))

    def test_migrate_dest_not_writable_fails_without_rsync(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            target = Path(td) / "tomove"
            target.mkdir()
            _write_file(target / "file.bin", 100)
            # Use an existing dest directory that we mark as not writable via
            # os.access mock, so we hit the writability check (not the
            # create-dir branch).
            dest = Path(td) / "dest"
            dest.mkdir()

            with mock.patch.object(safe_delete.os, "access", return_value=False), \
                 mock.patch.object(safe_delete.subprocess, "run") as m_run:
                payload = {
                    "confirmed_items": [
                        {"id": "mig1", "path": str(target), "action": "migrate",
                         "size_bytes": 100, "category": "large_media",
                         "risk_level": "L3", "reason": "t"}
                    ],
                    "action_overrides": {
                        "mig1": {"migrate_dest": str(dest)}
                    }
                }
                code, out, _ = _run_with_payload(payload, work)

            rec = out["records"][0]
            self.assertEqual(rec["status"], "failed")
            self.assertIn("not writable", rec["error"])
            m_run.assert_not_called()
            self.assertEqual(code, 1)

    def test_defer_writes_deferred_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            payload = {
                "confirmed_items": [
                    {"id": "d1", "path": "/Volumes/VM/bigvm.vmdk",
                     "action": "defer", "size_bytes": 50_000_000_000,
                     "category": "large_media", "risk_level": "L3",
                     "reason": "VM image, consider external volume"}
                ]
            }
            code, out, _ = _run_with_payload(payload, work)
            self.assertEqual(code, 0)
            self.assertEqual(out["deferred_count"], 1)
            deferred = (work / "deferred.jsonl").read_text().strip().splitlines()
            self.assertEqual(len(deferred), 1)
            self.assertIn("bigvm.vmdk", deferred[0])

    def test_skip_records_without_io(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            payload = {
                "confirmed_items": [
                    {"id": "sk1", "path": "/Users/me/something",
                     "action": "skip", "size_bytes": 9999,
                     "category": "orphan", "risk_level": "L4",
                     "reason": "no rule matched"}
                ]
            }
            code, out, _ = _run_with_payload(payload, work)
            self.assertEqual(code, 0)
            self.assertEqual(out["records"][0]["action"], "skip")
            self.assertEqual(out["reclaimed_bytes"], 0)

    def test_idempotent_on_missing_path(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            payload = {
                "confirmed_items": [
                    {"id": "gone1", "path": str(Path(td) / "never-existed"),
                     "action": "delete", "size_bytes": 100,
                     "category": "app_cache", "risk_level": "L1", "reason": "t"}
                ]
            }
            code, out, _ = _run_with_payload(payload, work)
            self.assertEqual(code, 0)
            rec = out["records"][0]
            self.assertEqual(rec["action"], "skip")
            self.assertEqual(rec["status"], "success")
            self.assertIn("already gone", rec["error"])

    def test_failure_is_isolated(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            ok = Path(td) / "ok.bin"
            bad = Path(td) / "bad.bin"
            _write_file(ok, 100)
            _write_file(bad, 100)

            real_remove = safe_delete.os.remove

            def flaky_remove(p):
                if str(p) == str(bad):
                    raise PermissionError("no")
                return real_remove(p)

            with mock.patch.object(safe_delete.os, "remove", side_effect=flaky_remove):
                payload = {
                    "confirmed_items": [
                        {"id": "a", "path": str(ok), "action": "delete",
                         "size_bytes": 100, "category": "app_cache",
                         "risk_level": "L1", "reason": "t"},
                        {"id": "b", "path": str(bad), "action": "delete",
                         "size_bytes": 100, "category": "app_cache",
                         "risk_level": "L1", "reason": "t"},
                    ]
                }
                code, out, _ = _run_with_payload(payload, work)

            self.assertEqual(code, 1)
            self.assertEqual(out["failed_count"], 1)
            self.assertFalse(ok.exists())
            self.assertTrue(bad.exists())

    def test_dry_run_does_not_touch_fs(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            target = Path(td) / "dry.bin"
            _write_file(target, 700)

            with mock.patch.object(safe_delete.subprocess, "run") as m_run, \
                 mock.patch.object(safe_delete.shutil, "rmtree") as m_rmtree, \
                 mock.patch.object(safe_delete.shutil, "move") as m_move, \
                 mock.patch.object(safe_delete.os, "remove") as m_remove:
                payload = {
                    "confirmed_items": [
                        {"id": "dr1", "path": str(target), "action": "delete",
                         "size_bytes": 700, "category": "app_cache",
                         "risk_level": "L1", "reason": "t"},
                        {"id": "dr2", "path": str(target), "action": "trash",
                         "size_bytes": 700, "category": "app_cache",
                         "risk_level": "L2", "reason": "t"},
                    ]
                }
                code, out, _ = _run_with_payload(payload, work, dry_run=True)

            self.assertEqual(code, 0)
            m_run.assert_not_called()
            m_rmtree.assert_not_called()
            m_move.assert_not_called()
            m_remove.assert_not_called()
            self.assertTrue(target.exists())
            for rec in out["records"]:
                self.assertTrue(rec["dry_run"])
            # Dry-run accumulates same way as real run, using size_before_bytes.
            # delete -> freed_now; trash -> pending_in_trash; no archive in this case.
            self.assertEqual(out["freed_now_bytes"], 700)
            self.assertEqual(out["pending_in_trash_bytes"], 700)
            self.assertEqual(out["archived_source_bytes"], 0)
            self.assertEqual(out["archived_count"], 0)
            self.assertEqual(out["reclaimed_bytes"], 1400)

    def test_empty_items(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            code, out, _ = _run_with_payload({"confirmed_items": []}, work)
            self.assertEqual(code, 0)
            self.assertEqual(out["reclaimed_bytes"], 0)
            self.assertEqual(out["records"], [])

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            argv = ["--workdir", str(work)]
            stdin = io.StringIO("not-json-at-all")
            stderr = io.StringIO()
            with mock.patch.object(sys, "stdin", stdin), \
                 mock.patch.object(sys, "stderr", stderr), \
                 mock.patch.object(sys, "stdout", io.StringIO()):
                code = safe_delete.run(argv)
            self.assertEqual(code, 2)
            self.assertIn("invalid stdin JSON", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
