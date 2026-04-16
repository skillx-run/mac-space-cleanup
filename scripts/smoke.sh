#!/usr/bin/env bash
# smoke.sh — end-to-end sanity check for the mac-space-clean scripts.
# Runs collect_sizes.py against real macOS paths (some may be missing on
# CI runners — that's fine, error isolation is part of what we test) and
# safe_delete.py with --dry-run across all six action types, then asserts
# on the recorded artefacts. Exits 0 on full success, non-zero on any
# assertion failure.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

mkdir -p ~/.cache/mac-space-clean
WORKDIR="$(mktemp -d ~/.cache/mac-space-clean/smoke-XXXXXX)"
trap 'rm -rf "$WORKDIR"' EXIT

echo "smoke workdir: $WORKDIR"

# ---------------------------------------------------------------------
# Stage A: collect_sizes against deterministic real (and one fake) paths.
# Use self-created tempdirs so behaviour is identical on any macOS host
# (including CI runners where ~/.Trash or ~/Library/Caches may be missing
# or empty).
# ---------------------------------------------------------------------
REAL_A="$(mktemp -d -t mac-space-clean-real-A-XXXXXX)"
REAL_B="$(mktemp -d -t mac-space-clean-real-B-XXXXXX)"
REAL_C="$(mktemp -d -t mac-space-clean-real-C-XXXXXX)"
echo "x" > "$REAL_A/sample"
dd if=/dev/zero of="$REAL_B/blob" bs=1024 count=4 status=none
dd if=/dev/zero of="$REAL_C/blob" bs=1024 count=8 status=none
trap 'rm -rf "$WORKDIR" "$REAL_A" "$REAL_B" "$REAL_C"' EXIT

REAL_A_J="$REAL_A" REAL_B_J="$REAL_B" REAL_C_J="$REAL_C" python3 - "$WORKDIR/paths.json" <<'PY'
import json, os, sys
paths = [
    os.environ["REAL_A_J"],
    os.environ["REAL_B_J"],
    os.environ["REAL_C_J"],
    "/this/path/definitely/does/not/exist/xyz-12345",
]
json.dump({"paths": paths}, open(sys.argv[1], "w"))
PY

echo "--- A1: collect_sizes.py ---"
# collect_sizes returns exit 1 when any path errors (the fake one will);
# that is the documented contract, so do not treat it as failure here.
set +e
python3 scripts/collect_sizes.py < "$WORKDIR/paths.json" > "$WORKDIR/sizes.json"
collect_rc=$?
set -e
if [[ $collect_rc -ne 0 && $collect_rc -ne 1 ]]; then
  echo "FAIL: collect_sizes.py exit $collect_rc unexpected"
  exit 1
fi

# Assert: 4 entries, real ones have exists=true, fake has exists=false.
# Note: pass paths via env vars; heredoc + sys.argv together is fragile.
SIZES_JSON="$WORKDIR/sizes.json" python3 <<'PY'
import json, os
data = json.load(open(os.environ["SIZES_JSON"]))
assert len(data) == 4, f"expected 4 entries, got {len(data)}"
real = [r for r in data if not r["path"].startswith("/this/")]
fake = [r for r in data if r["path"].startswith("/this/")]
assert len(real) == 3 and len(fake) == 1
for r in real:
    assert r["exists"] is True, f"real path missing: {r}"
    assert r["error"] is None, f"real path error: {r}"
assert fake[0]["exists"] is False
assert fake[0]["error"] is not None
print("A1 OK: 4 paths, 3 real (exists=true, no error), 1 fake (exists=false, error set)")
PY

# ---------------------------------------------------------------------
# Stage B: safe_delete --dry-run across all six action types
# ---------------------------------------------------------------------
cat > "$WORKDIR/confirmed.json" <<'EOF'
{
  "mode": "quick",
  "confirmed_items": [
    {"id":"a","path":"/tmp/smoke-fake-cache","action":"delete",
     "size_bytes":1024,"category":"app_cache","risk_level":"L1","reason":"smoke"},
    {"id":"b","path":"/tmp/smoke-fake-trash","action":"trash",
     "size_bytes":2048,"category":"app_cache","risk_level":"L2","reason":"smoke"},
    {"id":"c","path":"snapshot:com.apple.TimeMachine.2026-04-16-024706.local",
     "action":"delete","size_bytes":0,"category":"system_snapshots",
     "risk_level":"L2","reason":"smoke"},
    {"id":"d","path":"/tmp/smoke-fake-vm.vmdk","action":"defer",
     "size_bytes":50000000000,"category":"large_media","risk_level":"L3","reason":"smoke"},
    {"id":"e","path":"/tmp/smoke-fake-archive","action":"archive",
     "size_bytes":4096,"category":"downloads","risk_level":"L3","reason":"smoke"},
    {"id":"f","path":"/tmp/smoke-fake-skip","action":"skip",
     "size_bytes":99,"category":"orphan","risk_level":"L4","reason":"smoke"}
  ],
  "action_overrides": {}
}
EOF

echo "--- B1: safe_delete.py --dry-run ---"
python3 scripts/safe_delete.py --workdir "$WORKDIR" --dry-run \
  < "$WORKDIR/confirmed.json" > "$WORKDIR/exec-summary.json"

# Assert summary: 6 records, reclaimed = 1024+2048+4096 = 7168, deferred=1, failed=0
SUMMARY="$WORKDIR/exec-summary.json" ACTIONS="$WORKDIR/actions.jsonl" python3 <<'PY'
import json, os
s = json.load(open(os.environ["SUMMARY"]))
assert len(s["records"]) == 6, f"expected 6 records, got {len(s['records'])}"
assert s["reclaimed_bytes"] == 7168, f"expected reclaimed 7168, got {s['reclaimed_bytes']}"
assert s["deferred_count"] == 1, f"expected deferred 1, got {s['deferred_count']}"
assert s["failed_count"] == 0, f"expected failed 0, got {s['failed_count']}"
assert s["archive_only_count"] == 0
# Every fs-touching record must be marked dry_run
for r in s["records"]:
    if r["action"] in {"delete","trash","archive","migrate","defer"}:
        assert r["dry_run"] is True, f"action {r['action']} should be dry_run: {r}"
    if r["action"] == "skip":
        assert r["dry_run"] is False
# actions.jsonl must have exactly 6 lines (one per item)
with open(os.environ["ACTIONS"]) as f:
    lines = [ln for ln in f if ln.strip()]
assert len(lines) == 6, f"expected 6 actions.jsonl lines, got {len(lines)}"
print("B1 OK: 6 records, reclaimed=7168, deferred=1, failed=0, all dry_run flagged, actions.jsonl=6 lines")
PY

# Assert no real fs writes happened: deferred.jsonl absent, archive/ absent,
# /tmp/smoke-fake-* absent.
echo "--- B2: dry-run side-effect quarantine ---"
[[ ! -e "$WORKDIR/deferred.jsonl" ]] || { echo "FAIL: deferred.jsonl appeared in dry-run"; exit 1; }
[[ ! -e "$WORKDIR/archive" ]] || { echo "FAIL: archive/ dir appeared in dry-run"; exit 1; }
for f in /tmp/smoke-fake-cache /tmp/smoke-fake-trash /tmp/smoke-fake-vm.vmdk /tmp/smoke-fake-archive /tmp/smoke-fake-skip; do
  [[ ! -e "$f" ]] || { echo "FAIL: $f exists, dry-run leaked an fs op"; exit 1; }
done
echo "B2 OK: no deferred.jsonl, no archive/, no /tmp side effects"

# ---------------------------------------------------------------------
# Stage C: real (non-dry-run) trash on a temp file we created
# ---------------------------------------------------------------------
echo "--- C1: real trash of a temp file ---"
REAL_TARGET="$(mktemp -t mac-space-clean-smoke-real-XXXXXX)"
echo "real target: $REAL_TARGET"
ls -la "$REAL_TARGET"
TARGET_SIZE=$(stat -f "%z" "$REAL_TARGET")

cat > "$WORKDIR/confirmed-real.json" <<EOF
{
  "mode": "quick",
  "confirmed_items": [
    {"id":"real1","path":"$REAL_TARGET","action":"trash",
     "size_bytes":$TARGET_SIZE,"category":"app_cache","risk_level":"L2","reason":"smoke-real"}
  ],
  "action_overrides": {}
}
EOF
python3 scripts/safe_delete.py --workdir "$WORKDIR" \
  < "$WORKDIR/confirmed-real.json" > "$WORKDIR/exec-real.json"

[[ ! -e "$REAL_TARGET" ]] || { echo "FAIL: $REAL_TARGET still exists after real trash"; exit 1; }

SUMMARY="$WORKDIR/exec-real.json" python3 <<'PY'
import json, os
s = json.load(open(os.environ["SUMMARY"]))
assert s["failed_count"] == 0
rec = s["records"][0]
assert rec["status"] == "success"
assert rec["dry_run"] is False
assert rec["trash_location"] is not None
print(f"C1 OK: real trash succeeded, location={rec['trash_location']}")
PY

echo ""
echo "All smoke checks passed."
