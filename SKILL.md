---
name: mac-space-clean
description: "Guide the agent through macOS disk space cleanup with quick/deep modes and L1-L4 risk grading. Trigger when the user says things like \"clean up my Mac\", \"free up disk space\", \"what's eating my disk\", \"Mac 空间满了\", \"快速清理 / 深度清理\", \"腾点空间\". Produces an HTML report and EN/ZH share text with @heyiamlin attribution."
version: "0.1.0"
author: "heyiamlin"
---

# mac-space-clean

An agent-driven macOS cleanup workflow. You (the agent) are the decision-maker; two small scripts under `scripts/` handle the write side (safe deletion) and bulk IO (parallel size collection). Three reference docs under `references/` are your knowledge base. Three templates under `assets/` are the report / share-card skeleton.

## When to activate

Activate when the user's intent matches cleanup, e.g. `clean up my Mac`, `free disk space`, `find what's eating my disk`, `quick clean`, `deep clean`, or Chinese equivalents `清理 Mac 空间 / 快速清理 / 深度清理 / Mac 空间满了 / 腾点空间 / 空间都去哪了`.

## Mode selection

| User intent | Mode |
| --- | --- |
| "quick clean", "马上腾点空间", "先清一波" | `quick` |
| "deep clean", "深度清理", "分析一下空间去哪了" | `deep` |
| Generic ("clean my Mac" with no qualifier) | `deep` (default: scan first, do not aggressively delete) |

## What you must NOT do

1. **Never call `rm`, `mv`, `trash`, `tar`, `rsync`, or `tmutil deletelocalsnapshots` directly.** All cleanup writes go through `scripts/safe_delete.py`.
2. **Never scan or clean paths on the blacklist** in `references/cleanup-scope.md`.
3. **Never put filesystem paths, basenames, usernames, project names, or company names into the HTML report, SVG card, or share text.** Use `source_label` + `category` only. See `references/safety-policy.md` for the full redaction policy.
4. **Never edit the files in `assets/` in place.** Always `cp` them into `$WORKDIR` first and edit the copies.

## Workflow (six stages)

### Stage 1 · Mode identification

Pick `quick` or `deep` based on user intent (see table above). Then create a per-run workdir (the parent dir may not exist on first run, so `mkdir -p` first):

```bash
mkdir -p ~/.cache/mac-space-clean
WORKDIR=$(mktemp -d ~/.cache/mac-space-clean/run-XXXXXX)
```

Announce the mode and workdir to the user briefly.

### Stage 2 · Environment probe

Run these in parallel and summarise the result internally (do not dump raw output to the user):

```bash
sw_vers
df -h /
which -a docker brew pnpm npm yarn pip uv cargo go gradle xcrun
ls -d ~/.cocoapods ~/.gradle ~/.m2 2>/dev/null
```

From the output, remember:
- macOS version.
- Filesystem free space before cleanup (`free_before`). Capture as bytes for later diff.
- Which enhancement tools are installed. Skip rows in `references/cleanup-scope.md` Tier E for missing tools.

Read `references/cleanup-scope.md` once — this is your map of **where to look** and **where never to touch**.

### Stage 3 · Scan

Build a target path list from `cleanup-scope.md` filtered by what Stage 2 found. Write it to `$WORKDIR/paths.json`:

```json
{"paths": ["~/Library/Caches", "~/Library/Developer/CoreSimulator/Devices", "..."]}
```

Then collect sizes in one batched call:

```bash
python3 scripts/collect_sizes.py < "$WORKDIR/paths.json" > "$WORKDIR/sizes.json"
```

For semantic/tool entries (not plain paths), probe directly:
- `docker system df` — parse for images / containers / volumes / build cache sizes.
- `xcrun simctl list devices available` then infer which CoreSimulator device dirs are orphaned.
- `brew --cache` then `du -sh` on it.
- `tmutil listlocalsnapshots /` — each snapshot becomes an item with `path="snapshot:<full-name>"`.

Collect every observation into your in-memory candidate list. If `collect_sizes.py` reports errors for some paths, note them but continue.

**Mode affects scan depth**:
- `quick`: skip `large_media` category; skip Tier C browser caches deeper than one level; prefer Tier A + Tier E `dev_cache / pkg_cache`.
- `deep`: scan everything in Tier A–E, plus `tmutil` snapshots.

### Stage 4 · Classify & grade

For each candidate, consult `references/category-rules.md` and `references/safety-policy.md` to assign:

- `category` (one of 9, see rules doc)
- `risk_level` (`L1 | L2 | L3 | L4`)
- `recommended_action` (`delete | trash | archive | migrate | defer | skip`)
- `source_label` (UI-safe label, see rules doc table)
- `mode_hit_tags` (which modes should surface this)
- `reason` (one sentence describing why this rule fired)

If a directory's purpose is unclear, investigate before classifying: `ls -lah`, `file`, `head -c 200`. Do not guess. Unclassifiable items become `category=orphan, risk_level=L4, action=skip`.

**Filter by mode**: drop items whose `mode_hit_tags` does not include the current mode.

### Stage 5 · Confirm & execute

Present the candidates to the user, grouped by risk level. The confirmation bar is different per mode:

| Mode | L1 | L2 | L3 | L4 |
| --- | --- | --- | --- | --- |
| `quick` | Execute without asking | Batch confirm by category | Record as `defer` only; do **not** interact | Hidden |
| `deep` | Show list + pre-checked; ask for batch OK | Batch confirm by category | Per-item hard confirm, show default `trash`, allow override | Show as read-only |

When the user asks "what's that huge folder?", run `ls -lah` / `file` / `head` live and explain in terms of `source_label`, not paths.

After confirmation, write `$WORKDIR/confirmed.json`:

```json
{
  "mode": "deep",
  "confirmed_items": [
    {"id": "abc123", "path": "/Users/me/Library/Caches/com.foo",
     "category": "app_cache", "size_bytes": 1234567890,
     "risk_level": "L2", "action": "trash", "reason": "stale app cache"}
  ],
  "action_overrides": {
    "def456": {"migrate_dest": "/Volumes/External/archive/", "archive_format": "tar.gz"}
  }
}
```

Then execute:

```bash
python3 scripts/safe_delete.py --workdir "$WORKDIR" < "$WORKDIR/confirmed.json"
```

The script appends one line per item to `$WORKDIR/actions.jsonl` and prints a summary JSON to stdout. A non-zero exit means some items failed or ended as `archive_only_success` — read `actions.jsonl` and mention failures in the report.

Use `--dry-run` whenever you want a rehearsal: no filesystem writes except `actions.jsonl` and `deferred.jsonl`, and `reclaimed_bytes` is estimated from `size_bytes`.

### Stage 6 · Report & share

1. Compute `free_after`: `df -k / | tail -1 | awk '{print $4}'` → bytes.
2. Assemble an in-memory `CleanupResult` (see schema below) from scan observations + `actions.jsonl`. Write it to `$WORKDIR/cleanup-result.json` — this is the local audit record and **may contain full paths**.
3. Copy templates into the workdir (never edit `assets/` in place):

   ```bash
   cp assets/report-template.html "$WORKDIR/report.html"
   cp assets/report.css "$WORKDIR/report.css"
   cp assets/share-card-template.svg "$WORKDIR/share-card.svg"
   ```

4. Use the `Edit` tool to fill the five report regions in `$WORKDIR/report.html`. Match the paired markers exactly:
   - `<!-- region:summary:start -->` … `<!-- region:summary:end -->`: reclaimed headline, mode chip, L1-L4 count chips.
   - `<!-- region:distribution:start -->` … `<!-- region:distribution:end -->`: one card per category, showing pre-clean size / freed / remaining candidates. Use `source_label` names only.
   - `<!-- region:actions:start -->` … `<!-- region:actions:end -->`: a list grouped by action type (auto-cleaned / confirmed / archived / migrated / deferred / skipped / failed). Each row: source_label + size + action badge + one-line reason. No paths.
   - `<!-- region:deferred:start -->` … `<!-- region:deferred:end -->`: recommendations for `deferred.jsonl` entries and L3/L4 observations, at category granularity.
   - `<!-- region:share:start -->` … `<!-- region:share:end -->`: embedded SVG card (inline or via `<img>`), English share text in a `.share-text` block, Chinese share text below it, and an X share button.

   Budget: keep the combined inserted HTML under ~200 lines.

5. Fill the SVG placeholders in `$WORKDIR/share-card.svg`:
   - `${free_reclaimed}` → e.g. `37.4 GB` (single human-readable string, no path).
   - `${mode_label}` → `Quick Clean` or `Deep Clean`.
   - `${top_categories}` → up to 3 `source_label`s joined with ` · `, e.g. `Docker · Downloads · Xcode`.

6. Write the two share-text files:

   - `$WORKDIR/share.en.txt` (default):
     ```
     I just reclaimed {reclaimed} on my Mac with the mac-space-clean skill by @heyiamlin.

     Biggest wins: {top3_joined}.

     #macspaceclean #maccleanup #buildinpublic
     ```

   - `$WORKDIR/share.zh.txt`:
     ```
     我刚用 mac-space-clean 这个 skill 清理了 Mac,释放了 {reclaimed} 空间,作者 @heyiamlin。

     这次最大的空间回收来自 {top3_joined_zh}。
     ```

   Only substitute: `{reclaimed}`, `{top3_joined}`, `{top3_joined_zh}` (use the same `source_label` taxonomy; no paths, no usernames, no project names).

7. Open the report:

   ```bash
   open "$WORKDIR/report.html"
   ```

8. Summarise to the user in one short paragraph: mode, reclaimed bytes (with the caveat that trash-based reclaim requires emptying `~/.Trash`), deferred count, and the report path.

## `cleanup-result.json` schema

```
{
  "run_id": "<timestamp-based>",
  "started_at": <iso8601>,
  "finished_at": <iso8601>,
  "mode": "quick" | "deep",
  "host_info": {"os": "macOS 14.x", "free_before": <bytes>, "free_after": <bytes>},
  "items": [
    {"id", "path", "category", "size_bytes", "mtime", "risk_level",
     "recommended_action", "source_label", "mode_hit_tags":["quick"|"deep"],
     "reversible": <bool>, "reason"}
  ],
  "actions": [ /* raw rows from actions.jsonl */ ],
  "totals": {"scanned_bytes", "reclaimed_bytes", "skipped_bytes",
             "deferred_bytes", "failed_bytes"},
  "risk_breakdown": {"L1": {"count","bytes"}, "L2": {...}, "L3": {...}, "L4": {...}}
}
```

## Quick reference

- **Workdir**: `~/.cache/mac-space-clean/run-XXXXXX`, per run.
- **Never direct-write for cleanup**: route through `scripts/safe_delete.py`.
- **Redaction**: UI/share output uses `source_label` + `category` only; see `references/safety-policy.md`.
- **Enumerations**:
  - `risk_level`: `L1 | L2 | L3 | L4`
  - `action`: `delete | trash | archive | migrate | defer | skip`
  - `category`: `dev_cache | sim_runtime | pkg_cache | app_cache | logs | downloads | large_media | system_snapshots | orphan`
  - `action_status`: `success | archive_only_success | failed`
- **Degradation**: see §14-style matrix in `references/safety-policy.md`.
