"""Tests for the v0.9 Ollama per-model dispatcher in safe_delete.py.

Each test builds a fake ``~/.ollama/models/`` layout (manifests + blobs) in
a temp dir, points ``safe_delete.OLLAMA_MODELS_DIR`` at it, and invokes
``safe_delete.run`` through the shared helper. The key invariant under
test is reference-counting: a blob digest referenced by ANY other manifest
must survive a delete of the target model.
"""

from __future__ import annotations

import json
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


def _run_with_payload(payload: dict, workdir: Path, dry_run: bool = False) -> tuple[int, dict, str]:
    argv = ["--workdir", str(workdir)]
    if dry_run:
        argv.append("--dry-run")
    return run_script_with_json(safe_delete, argv, payload)


def _write_blob(blobs_dir: Path, digest: str, size: int) -> Path:
    """Create a sha256-<hex> file under blobs/ with the given size."""
    assert digest.startswith("sha256:"), "test fixture expects sha256:<hex>"
    blob_path = blobs_dir / digest.replace(":", "-", 1)
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_bytes(b"x" * size)
    return blob_path


def _write_manifest(
    manifests_root: Path,
    blobs_dir: Path,
    *,
    registry: str = "registry.ollama.ai",
    namespace: str = "library",
    name: str,
    tag: str,
    config_digest: str,
    layer_digests: list[str],
) -> Path:
    """Build an Ollama-style manifest JSON at the on-disk path for <name>:<tag>.

    The manifest's ``size`` field for each blob is filled from the actual
    on-disk blob byte count when available, so the fixture stays internally
    consistent even though the dispatcher only reads ``digest`` (not ``size``).
    Falls back to 0 for digests whose blob file doesn't yet exist.
    """

    def _real_size(digest: str) -> int:
        blob_path = blobs_dir / digest.replace(":", "-", 1)
        try:
            return blob_path.stat().st_size
        except OSError:
            return 0

    manifest_dir = manifests_root / registry / namespace / name
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / tag
    manifest_path.write_text(json.dumps({
        "schemaVersion": 2,
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {
            "mediaType": "application/vnd.docker.container.image.v1+json",
            "digest": config_digest,
            "size": _real_size(config_digest),
        },
        "layers": [
            {
                "mediaType": "application/vnd.ollama.image.model",
                "digest": d,
                "size": _real_size(d),
            }
            for d in layer_digests
        ],
    }))
    return manifest_path


class TestOllamaDispatcher(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.models = self.root / ".ollama" / "models"
        self.manifests = self.models / "manifests"
        self.blobs = self.models / "blobs"
        self.manifests.mkdir(parents=True)
        self.blobs.mkdir(parents=True)
        self._patcher = mock.patch.object(safe_delete, "OLLAMA_MODELS_DIR", self.models)
        self._patcher.start()

    def tearDown(self) -> None:
        self._patcher.stop()
        self._td.cleanup()

    # ---------- fixture builders ----------

    def _build_shared_blob_fixture(self) -> dict[str, Path]:
        """Two manifests (llama3:8b, llama3:70b) share one common config blob
        and each have one exclusive layer blob. Blob sizes: config=1000,
        each layer=2000."""
        shared = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        layer_a = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        layer_b = "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
        shared_blob = _write_blob(self.blobs, shared, 1000)
        layer_a_blob = _write_blob(self.blobs, layer_a, 2000)
        layer_b_blob = _write_blob(self.blobs, layer_b, 2000)
        manifest_a = _write_manifest(
            self.manifests, self.blobs, name="llama3", tag="8b",
            config_digest=shared, layer_digests=[layer_a],
        )
        manifest_b = _write_manifest(
            self.manifests, self.blobs, name="llama3", tag="70b",
            config_digest=shared, layer_digests=[layer_b],
        )
        return {
            "shared_blob": shared_blob,
            "layer_a_blob": layer_a_blob,
            "layer_b_blob": layer_b_blob,
            "manifest_a": manifest_a,
            "manifest_b": manifest_b,
        }

    # ---------- tests ----------

    def test_delete_model_removes_exclusive_blobs_keeps_shared(self):
        fx = self._build_shared_blob_fixture()
        with tempfile.TemporaryDirectory() as wd:
            work = Path(wd)
            payload = {
                "confirmed_items": [
                    {"id": "m1", "path": "ollama:llama3:8b", "action": "delete",
                     "size_bytes": 0, "category": "pkg_cache",
                     "risk_level": "L3", "reason": "test"}
                ]
            }
            code, out, _ = _run_with_payload(payload, work)

        self.assertEqual(code, 0)
        # Target manifest and its exclusive layer blob are gone.
        self.assertFalse(fx["manifest_a"].exists())
        self.assertFalse(fx["layer_a_blob"].exists())
        # The other model's manifest survives; so does the shared config blob
        # because manifest_b still references it.
        self.assertTrue(fx["manifest_b"].exists())
        self.assertTrue(fx["shared_blob"].exists())
        self.assertTrue(fx["layer_b_blob"].exists())
        # freed_now_bytes == exclusive blob size (one layer, 2000 bytes).
        self.assertEqual(out["freed_now_bytes"], 2000)
        self.assertEqual(out["records"][0]["size_before_bytes"], 2000)

    def test_delete_second_model_reclaims_shared_blob(self):
        """After deleting both manifests in sequence, the shared blob has
        zero remaining references and IS removed on the second pass."""
        fx = self._build_shared_blob_fixture()
        with tempfile.TemporaryDirectory() as wd:
            work = Path(wd)
            # First delete llama3:8b — shared blob stays.
            _run_with_payload(
                {"confirmed_items": [
                    {"id": "m1", "path": "ollama:llama3:8b", "action": "delete",
                     "size_bytes": 0, "category": "pkg_cache",
                     "risk_level": "L3", "reason": "t"}
                ]}, work,
            )
            self.assertTrue(fx["shared_blob"].exists())
            # Second delete llama3:70b — now it's exclusive.
            code, out, _ = _run_with_payload(
                {"confirmed_items": [
                    {"id": "m2", "path": "ollama:llama3:70b", "action": "delete",
                     "size_bytes": 0, "category": "pkg_cache",
                     "risk_level": "L3", "reason": "t"}
                ]}, work,
            )

        self.assertEqual(code, 0)
        self.assertFalse(fx["manifest_b"].exists())
        self.assertFalse(fx["layer_b_blob"].exists())
        self.assertFalse(fx["shared_blob"].exists())
        # Second pass reclaims the shared blob (1000) and the exclusive
        # layer_b blob (2000) = 3000.
        self.assertEqual(out["freed_now_bytes"], 3000)

    def test_dry_run_reports_exclusive_bytes_and_touches_nothing(self):
        fx = self._build_shared_blob_fixture()
        with tempfile.TemporaryDirectory() as wd:
            work = Path(wd)
            code, out, _ = _run_with_payload(
                {"confirmed_items": [
                    {"id": "m1", "path": "ollama:llama3:8b", "action": "delete",
                     "size_bytes": 0, "category": "pkg_cache",
                     "risk_level": "L3", "reason": "t"}
                ]}, work, dry_run=True,
            )

        self.assertEqual(code, 0)
        # Nothing moved on disk.
        self.assertTrue(fx["manifest_a"].exists())
        self.assertTrue(fx["layer_a_blob"].exists())
        self.assertTrue(fx["shared_blob"].exists())
        # Dry run still reports the same exclusive byte count.
        self.assertEqual(out["freed_now_bytes"], 2000)
        self.assertTrue(out["records"][0]["dry_run"])

    def test_corrupted_manifest_fails_without_leaking_full_path(self):
        fx = self._build_shared_blob_fixture()
        # Corrupt manifest_a in place.
        fx["manifest_a"].write_text("{not valid json")
        with tempfile.TemporaryDirectory() as wd:
            work = Path(wd)
            code, out, _ = _run_with_payload(
                {"confirmed_items": [
                    {"id": "m1", "path": "ollama:llama3:8b", "action": "delete",
                     "size_bytes": 0, "category": "pkg_cache",
                     "risk_level": "L3", "reason": "t"}
                ]}, work,
            )

        self.assertEqual(code, 1)
        rec = out["records"][0]
        self.assertEqual(rec["status"], "failed")
        self.assertIn("manifest missing or unreadable", rec["error"])
        # The error must not leak the full on-disk manifest path.
        self.assertNotIn(str(self.manifests), rec["error"])
        self.assertNotIn(str(fx["manifest_a"]), rec["error"])

    def test_missing_manifest_root_fails_cleanly(self):
        """When ``~/.ollama/models/manifests/`` does not exist at all (fresh
        Mac that never ran ``ollama pull`` but somehow ended up with a
        stale ``ollama:`` candidate in ``confirmed.json``), the dispatcher
        fails cleanly with the manifest-missing error rather than crashing
        during the walk. Exercises the code path where
        ``_collect_manifest_blobs`` returns None because the file doesn't
        exist at all (as opposed to existing-but-corrupt, which
        ``test_corrupted_manifest_fails_without_leaking_full_path`` covers).
        """
        # Remove the entire manifests dir — leave blobs/ alone so we don't
        # short-circuit through some other path.
        import shutil as _shutil
        _shutil.rmtree(self.manifests)
        with tempfile.TemporaryDirectory() as wd:
            work = Path(wd)
            code, out, _ = _run_with_payload(
                {"confirmed_items": [
                    {"id": "m", "path": "ollama:llama3:8b", "action": "delete",
                     "size_bytes": 0, "category": "pkg_cache",
                     "risk_level": "L3", "reason": "t"}
                ]}, work,
            )
        self.assertEqual(code, 1)
        rec = out["records"][0]
        self.assertEqual(rec["status"], "failed")
        self.assertIn("manifest missing or unreadable", rec["error"])
        # Same redaction contract as the corrupt-manifest case.
        self.assertNotIn(str(self.models), rec["error"])

    def test_malformed_path_form_fails_cleanly(self):
        """ollama:<name> without a tag, or ollama: with empty suffix, both
        come back as failed with a path-form error — no blob walk."""
        with tempfile.TemporaryDirectory() as wd:
            work = Path(wd)
            for bad in ("ollama:", "ollama:llama3", "ollama:llama3:"):
                with self.subTest(path=bad):
                    code, out, _ = _run_with_payload(
                        {"confirmed_items": [
                            {"id": "m", "path": bad, "action": "delete",
                             "size_bytes": 0, "category": "pkg_cache",
                             "risk_level": "L3", "reason": "t"}
                        ]}, work,
                    )
                    self.assertEqual(code, 1)
                    rec = out["records"][0]
                    self.assertEqual(rec["status"], "failed")
                    self.assertIn("invalid ollama path form", rec["error"])

    def test_third_party_registry_maps_to_literal_path(self):
        """`ollama:hf.co/bartowski/xxx:Q4` resolves to
        `hf.co/bartowski/xxx/Q4` — the first segment has a `.` so it is
        treated as a registry host, bypassing the default `library`
        namespace injection."""
        layer = "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
        layer_blob = _write_blob(self.blobs, layer, 5000)
        manifest = _write_manifest(
            self.manifests, self.blobs,
            registry="hf.co", namespace="bartowski",
            name="xxx", tag="Q4",
            config_digest=layer, layer_digests=[layer],
        )
        with tempfile.TemporaryDirectory() as wd:
            work = Path(wd)
            code, out, _ = _run_with_payload(
                {"confirmed_items": [
                    {"id": "m", "path": "ollama:hf.co/bartowski/xxx:Q4",
                     "action": "delete", "size_bytes": 0,
                     "category": "pkg_cache", "risk_level": "L3", "reason": "t"}
                ]}, work,
            )

        self.assertEqual(code, 0)
        self.assertFalse(manifest.exists())
        self.assertFalse(layer_blob.exists())
        # One blob, 5000 bytes.
        self.assertEqual(out["freed_now_bytes"], 5000)

    def test_user_namespace_under_default_registry(self):
        """`ollama:user/custom:v1` maps to
        `registry.ollama.ai/user/custom/v1` — the first segment lacks a `.`
        so it is treated as a namespace under the default registry."""
        layer = "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        _write_blob(self.blobs, layer, 7000)
        manifest = _write_manifest(
            self.manifests, self.blobs,
            registry="registry.ollama.ai",
            namespace="user", name="custom", tag="v1",
            config_digest=layer, layer_digests=[layer],
        )
        with tempfile.TemporaryDirectory() as wd:
            work = Path(wd)
            code, out, _ = _run_with_payload(
                {"confirmed_items": [
                    {"id": "m", "path": "ollama:user/custom:v1",
                     "action": "delete", "size_bytes": 0,
                     "category": "pkg_cache", "risk_level": "L3", "reason": "t"}
                ]}, work,
            )

        self.assertEqual(code, 0)
        self.assertFalse(manifest.exists())
        self.assertEqual(out["freed_now_bytes"], 7000)

    def test_ollama_path_not_matched_by_blocked_patterns(self):
        """Ollama semantic paths must not incidentally match any regex in
        ``_BLOCKED_PATTERNS``. If a future regex change (say a pattern for
        ``(^|/)\\.models/``) accidentally captures an ``ollama:`` path, this
        test flags it before the v0.9+ per-model path silently stops
        reclaiming. The separate ``is_specialised`` bypass in ``dispatch()``
        is a second line of defence exercised end-to-end by the dispatch
        path below — together the two ensure the path never hits the
        blocklist-refusal branch regardless of which catches it first.
        """
        self.assertFalse(safe_delete._is_blocked("ollama:llama3:8b"))
        self.assertFalse(safe_delete._is_blocked("ollama:hf.co/x/y:tag"))
        self.assertFalse(safe_delete._is_blocked("ollama:user/custom:v1"))
        # End-to-end: a real dispatch against an ollama: path never surfaces
        # the standard blocklist-refusal error message, even though
        # is_specialised is the mechanism that would save us if _is_blocked
        # ever did match (the positive assertion for that mechanism lives in
        # the existing brew:/docker: tests in test_safe_delete.py).
        fx = self._build_shared_blob_fixture()
        with tempfile.TemporaryDirectory() as wd:
            work = Path(wd)
            code, out, _ = _run_with_payload(
                {"confirmed_items": [
                    {"id": "m", "path": "ollama:llama3:8b", "action": "delete",
                     "size_bytes": 0, "category": "pkg_cache",
                     "risk_level": "L3", "reason": "t"}
                ]}, work,
            )
        self.assertEqual(code, 0)
        self.assertNotIn("blocked by safety pattern", out["records"][0].get("error") or "")
        self.assertFalse(fx["layer_a_blob"].exists())


if __name__ == "__main__":
    unittest.main()
