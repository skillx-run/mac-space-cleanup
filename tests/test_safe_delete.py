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
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

import safe_delete  # noqa: E402
from _helpers import run_script_with_json  # noqa: E402


def _write_file(p: Path, size: int = 100) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)


def _run_with_payload(payload: dict, workdir: Path, dry_run: bool = False) -> tuple[int, dict, str]:
    argv = ["--workdir", str(workdir)]
    if dry_run:
        argv.append("--dry-run")
    return run_script_with_json(safe_delete, argv, payload)


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

    def test_brew_cleanup_invokes_brew_and_parses_freed_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            calls: list[list[str]] = []
            brew_stdout = (
                "Removing: /opt/homebrew/Cellar/foo/1.0... (123 files, 5.4MB)\n"
                "Removing: /opt/homebrew/Cellar/bar/2.0... (45 files, 1.2GB)\n"
                "==> This operation has freed approximately 1.2GB of disk space.\n"
            )

            def fake_run(cmd, **kw):
                calls.append(cmd)
                if cmd[:2] == ["brew", "cleanup"]:
                    return mock.Mock(returncode=0, stdout=brew_stdout, stderr="")
                raise AssertionError(f"unexpected cmd: {cmd}")

            with mock.patch.object(safe_delete.subprocess, "run", side_effect=fake_run):
                payload = {
                    "confirmed_items": [
                        {"id": "brew_clean", "path": "brew:cleanup-s",
                         "action": "delete", "size_bytes": 0,
                         "category": "pkg_cache", "risk_level": "L1",
                         "reason": "trim Cellar old versions"}
                    ]
                }
                code, out, _ = _run_with_payload(payload, work)

            self.assertEqual(code, 0)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0], ["brew", "cleanup", "-s"])
            rec = out["records"][0]
            self.assertEqual(rec["status"], "success")
            # 1.2 GB = 1.2 * 1024^3 = 1288490188
            self.assertEqual(rec["size_before_bytes"], int(1.2 * 1024 ** 3))
            self.assertEqual(out["freed_now_bytes"], int(1.2 * 1024 ** 3))

    def test_brew_cleanup_failure_propagates(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"

            def fake_run(cmd, **kw):
                if cmd[:2] == ["brew", "cleanup"]:
                    raise subprocess.CalledProcessError(
                        returncode=1, cmd=cmd, stderr="brew not found"
                    )
                raise AssertionError(f"unexpected cmd: {cmd}")

            with mock.patch.object(safe_delete.subprocess, "run", side_effect=fake_run):
                payload = {
                    "confirmed_items": [
                        {"id": "brew_fail", "path": "brew:cleanup-s",
                         "action": "delete", "size_bytes": 0,
                         "category": "pkg_cache", "risk_level": "L1", "reason": "t"}
                    ]
                }
                code, out, _ = _run_with_payload(payload, work)

            self.assertEqual(code, 1)
            rec = out["records"][0]
            self.assertEqual(rec["status"], "failed")
            self.assertIn("brew cleanup -s failed", rec["error"])
            self.assertEqual(out["freed_now_bytes"], 0)

    def test_docker_prune_dispatch_per_subcommand(self):
        """All three docker:* semantic paths must dispatch to the right
        prune sub-command and parse the 'Total reclaimed space: X' line.

        Docker uses Go's units.HumanSize which is base-1000 (decimal),
        unlike brew which uses Ruby's Utils::Bytes (base-1024 binary).
        """
        cases = [
            ("docker:build-cache", ["docker", "builder", "prune", "-f"], "456MB"),
            ("docker:dangling-images", ["docker", "image", "prune", "-f"], "1.5GB"),
            ("docker:stopped-containers", ["docker", "container", "prune", "-f"], "78kB"),
        ]
        expected_bytes = {
            "456MB": 456 * 1000 ** 2,
            "1.5GB": int(1.5 * 1000 ** 3),
            "78kB": 78 * 1000,
        }

        for path, expected_cmd, reclaimed in cases:
            with self.subTest(path=path):
                with tempfile.TemporaryDirectory() as td:
                    work = Path(td) / "work"
                    calls: list[list[str]] = []
                    docker_stdout = (
                        f"Deleted: ...some hash...\n"
                        f"Total reclaimed space: {reclaimed}\n"
                    )

                    def fake_run(cmd, **kw):
                        calls.append(cmd)
                        if cmd[0] == "docker":
                            return mock.Mock(returncode=0, stdout=docker_stdout, stderr="")
                        raise AssertionError(f"unexpected cmd: {cmd}")

                    with mock.patch.object(safe_delete.subprocess, "run", side_effect=fake_run):
                        payload = {
                            "confirmed_items": [
                                {"id": f"d-{path}", "path": path,
                                 "action": "delete", "size_bytes": 0,
                                 "category": "dev_cache", "risk_level": "L1",
                                 "reason": "test"}
                            ]
                        }
                        code, out, _ = _run_with_payload(payload, work)

                    self.assertEqual(code, 0)
                    self.assertEqual(calls, [expected_cmd])
                    rec = out["records"][0]
                    self.assertEqual(rec["status"], "success")
                    self.assertEqual(rec["size_before_bytes"], expected_bytes[reclaimed])

    def test_docker_prune_unknown_suffix_fails_safely(self):
        """An unrecognised docker:* path must fail with a clear error and
        must NOT shell out — protects against typos in confirmed.json."""
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"

            def fake_run(cmd, **kw):
                raise AssertionError(f"must not invoke for unknown suffix: {cmd}")

            with mock.patch.object(safe_delete.subprocess, "run", side_effect=fake_run):
                payload = {
                    "confirmed_items": [
                        {"id": "d_unknown", "path": "docker:unused-volumes",
                         "action": "delete", "size_bytes": 0,
                         "category": "dev_cache", "risk_level": "L1", "reason": "t"}
                    ]
                }
                code, out, _ = _run_with_payload(payload, work)

            self.assertEqual(code, 1)
            rec = out["records"][0]
            self.assertEqual(rec["status"], "failed")
            self.assertIn("unrecognised docker prune target", rec["error"])

    def test_brew_cleanup_dry_run_keeps_input_estimate(self):
        """Dry-run skips brew invocation and credits the input size estimate
        so the dry-run summary reflects the upper-bound reclaim."""
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"

            def fake_run(cmd, **kw):
                raise AssertionError(f"dry-run must not invoke: {cmd}")

            with mock.patch.object(safe_delete.subprocess, "run", side_effect=fake_run):
                payload = {
                    "confirmed_items": [
                        {"id": "brew_dry", "path": "brew:cleanup-s",
                         "action": "delete",
                         "size_bytes": 5 * 1024 ** 3,  # 5 GB pre-estimate
                         "category": "pkg_cache", "risk_level": "L1", "reason": "t"}
                    ]
                }
                code, out, _ = _run_with_payload(payload, work, dry_run=True)

            self.assertEqual(code, 0)
            rec = out["records"][0]
            self.assertEqual(rec["status"], "success")
            self.assertTrue(rec["dry_run"])
            self.assertEqual(rec["size_before_bytes"], 5 * 1024 ** 3)
            self.assertEqual(out["freed_now_bytes"], 5 * 1024 ** 3)

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
        is_blocked = safe_delete._is_blocked
        self.assertFalse(is_blocked("/Users/me/Library/Caches/com.foo"))
        self.assertFalse(is_blocked("/Users/me/Downloads/git-tutorial.pdf"))
        self.assertFalse(is_blocked("/Users/me/Documents/notes.txt"))
        self.assertFalse(is_blocked("/Users/me/.envvars-old.txt"))
        self.assertTrue(is_blocked("/Users/me/projects/foo/.git/objects"))
        self.assertTrue(is_blocked("/Users/me/.ssh/config"))
        self.assertTrue(is_blocked("/Users/me/Library/Keychains/login.keychain-db"))
        self.assertTrue(is_blocked("/Users/me/Pictures/Photos Library.photoslibrary/originals"))
        self.assertTrue(is_blocked("/Users/me/Documents/.env"))

    def test_blocked_pattern_refuses_vscode_family_user_data(self):
        """Even if confirmed.json mistakenly lists VSCode/Cursor/Windsurf
        User / Backups / History (which hold unsaved edits, git-stash
        equivalents, and edit history), dispatch must refuse — these are the
        runtime backstop for the Tier C subset whitelist."""
        is_blocked = safe_delete._is_blocked
        # Positive: every dangerous sibling under each of the three brands is
        # caught.
        for brand in ("Code", "Cursor", "Windsurf"):
            for guarded in ("User", "Backups", "History"):
                with self.subTest(brand=brand, guarded=guarded):
                    self.assertTrue(is_blocked(
                        f"/Users/me/Library/Application Support/{brand}/{guarded}"
                    ))
                    self.assertTrue(is_blocked(
                        f"/Users/me/Library/Application Support/{brand}/{guarded}/workspaceStorage/abc"
                    ))
        # Negative: the cleanable cache subdirs must NOT be blocked, otherwise
        # the v0.9.1 expansion would never reclaim anything.
        for cache_subdir in ("Cache", "CachedData", "GPUCache", "Code Cache", "logs"):
            with self.subTest(cache_subdir=cache_subdir):
                self.assertFalse(is_blocked(
                    f"/Users/me/Library/Application Support/Code/{cache_subdir}"
                ))
                self.assertFalse(is_blocked(
                    f"/Users/me/Library/Application Support/Cursor/{cache_subdir}/blob"
                ))

    def test_blocked_pattern_refuses_delete_on_vscode_user_data_via_dispatch(self):
        """End-to-end: a delete request against Code/User must come back as
        failed with the standard blocklist error message and must NOT delete
        anything from disk."""
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            target = Path(td) / "Library/Application Support/Code/User/workspaceStorage"
            target.mkdir(parents=True)
            (target / "state.vscdb").write_bytes(b"x" * 1234)

            payload = {
                "confirmed_items": [
                    {"id": "vsc1", "path": str(target), "action": "delete",
                     "size_bytes": 1234, "category": "app_cache",
                     "risk_level": "L1", "reason": "agent misjudged"}
                ]
            }
            code, out, _ = _run_with_payload(payload, work)

            self.assertEqual(code, 1)
            rec = out["records"][0]
            self.assertEqual(rec["status"], "failed")
            self.assertIn("blocked by safety pattern", rec["error"])
            self.assertTrue(target.exists(), "blocklist must protect disk state")
            self.assertTrue((target / "state.vscdb").exists())

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
        from _helpers import run_script
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            argv = ["--workdir", str(work)]
            code, _, stderr_text = run_script(safe_delete, argv, "not-json-at-all")
            self.assertEqual(code, 2)
            self.assertIn("invalid stdin JSON", stderr_text)


if __name__ == "__main__":
    unittest.main()
