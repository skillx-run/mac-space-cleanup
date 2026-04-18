#!/usr/bin/env bash
# dry-e2e.sh — exercises the non-LLM pipeline end-to-end.
#
# What this covers:
#   collect_sizes -> safe_delete --dry-run -> simulated agent fill of
#   report.html -> validate_report.py.
# What this does NOT cover:
#   the agent's judgement (mode pick, classification, redaction reviewer).
#   For those, run the skill in a real Claude Code session.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

mkdir -p ~/.cache/mac-space-cleanup
export WORKDIR="$(mktemp -d ~/.cache/mac-space-cleanup/dry-e2e-XXXXXX)"
export SCRATCH="$(mktemp -d -t mac-space-cleanup-dry-e2e-scratch-XXXXXX)"
trap 'rm -rf "$WORKDIR" "$SCRATCH"' EXIT

echo "dry-e2e workdir: $WORKDIR"
echo "dry-e2e scratch: $SCRATCH"

# ---------------------------------------------------------------------
# A. Stage 3 simulation: collect_sizes against a few real paths the
# harness owns. Tests the size collector + JSON contract.
# ---------------------------------------------------------------------
echo "y" > "$SCRATCH/dev_cache_sample"
dd if=/dev/zero of="$SCRATCH/blob.bin" bs=1024 count=4 status=none

REAL_A="$SCRATCH" python3 - "$WORKDIR/paths.json" <<'PY'
import json, os, sys
json.dump({"paths": [os.environ["REAL_A"]]}, open(sys.argv[1], "w"))
PY

echo "--- A: collect_sizes ---"
python3 scripts/collect_sizes.py < "$WORKDIR/paths.json" > "$WORKDIR/sizes.json"
SIZES="$WORKDIR/sizes.json" python3 <<'PY'
import json, os
data = json.load(open(os.environ["SIZES"]))
assert len(data) == 1 and data[0]["exists"] and data[0]["size_bytes"] > 0
print("A OK")
PY

# ---------------------------------------------------------------------
# B. Stage 5 simulation: feed safe_delete --dry-run a fixture confirmed.json.
# Patch the fixture's placeholder path tokens to point at the scratch dir
# so dispatch's idempotent exists() check sees them. They are NOT actually
# touched (--dry-run).
# ---------------------------------------------------------------------
touch "$SCRATCH/dev_cache_sample"
touch "$SCRATCH/downloads_sample.dmg"
touch "$SCRATCH/archive_zip_sample.zip"
touch "$SCRATCH/large_vm.vmdk"

sed "s|__WILL_BE_REPLACED_AT_RUNTIME__|$SCRATCH|g" \
  tests/fixtures/sample-classified.json > "$WORKDIR/confirmed.json"

echo "--- B: safe_delete --dry-run ---"
python3 scripts/safe_delete.py --workdir "$WORKDIR" --dry-run \
  < "$WORKDIR/confirmed.json" > "$WORKDIR/exec.json"

EXEC="$WORKDIR/exec.json" python3 <<'PY'
import json, os
s = json.load(open(os.environ["EXEC"]))
assert len(s["records"]) == 4, f"expected 4 records, got {len(s['records'])}"
# Two L1 deletes (4096 + 8192) -> freed_now
assert s["freed_now_bytes"] == 12288, s["freed_now_bytes"]
# One L2 trash (2048) -> pending_in_trash
assert s["pending_in_trash_bytes"] == 2048, s["pending_in_trash_bytes"]
# One defer
assert s["deferred_count"] == 1
# Compatibility alias
assert s["reclaimed_bytes"] == 14336
# All real-action records dry_run flagged
for rec in s["records"]:
    if rec["action"] in {"delete","trash","archive","migrate","defer"}:
        assert rec["dry_run"] is True, rec
print("B OK")
PY

# ---------------------------------------------------------------------
# C. Stage 6 simulation: copy both templates to workdir, splice in fixture
# fill content for each region (4 on report.html, 4 on details.html),
# then run validate_report twice with --kind.
# ---------------------------------------------------------------------
cp assets/report-template.html  "$WORKDIR/report.html"
cp assets/details-template.html "$WORKDIR/details.html"
cp assets/report.css            "$WORKDIR/report.css"

FILL="tests/fixtures/sample-fill.html.fragment" python3 <<'PY'
import os, re

src = open(os.environ["FILL"]).read()
workdir = os.environ["WORKDIR"]

# Extract each "<!-- BEGIN region:NAME -->...<!-- END region:NAME -->" block
# from the fixture and use it to replace the matching paired marker in the
# file that declares that region.
block_re = re.compile(
    r"<!--\s*BEGIN\s+region:(\w+)\s*-->(.*?)<!--\s*END\s+region:\1\s*-->",
    re.DOTALL,
)
replacements = {name: body.strip() for name, body in block_re.findall(src)}

HERO = {"hero", "impact", "nextstep", "share"}
DETAILS = {"distribution", "actions", "observations", "runmeta"}
files = {
    os.path.join(workdir, "report.html"):  HERO,
    os.path.join(workdir, "details.html"): DETAILS,
}

for path, region_set in files.items():
    text = open(path).read()
    for name in region_set:
        if name not in replacements:
            raise SystemExit(f"fixture missing region: {name}")
        pattern = re.compile(
            rf"(<!--\s*region:{name}:start\s*-->).*?(<!--\s*region:{name}:end\s*-->)",
            re.DOTALL,
        )
        if not pattern.search(text):
            raise SystemExit(f"template {path} missing region: {name}")
        text = pattern.sub(rf"\1\n{replacements[name]}\n\2", text)
    open(path, "w").write(text)
print(f"C: filled {len(replacements)} regions across both pages")
PY

echo "--- C: validate_report (hero) ---"
python3 scripts/validate_report.py --report "$WORKDIR/report.html" \
  --kind hero > "$WORKDIR/validate-hero.json"
VAL="$WORKDIR/validate-hero.json" python3 <<'PY'
import json, os
v = json.load(open(os.environ["VAL"]))
assert v["ok"] is True, v
print("C hero OK")
PY

echo "--- C: validate_report (details) ---"
python3 scripts/validate_report.py --report "$WORKDIR/details.html" \
  --kind details > "$WORKDIR/validate-details.json"
VAL="$WORKDIR/validate-details.json" python3 <<'PY'
import json, os
v = json.load(open(os.environ["VAL"]))
assert v["ok"] is True, v
print("C details OK")
PY

echo ""
echo "All dry-e2e checks passed."
