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

Three-tier decision: strong-quick signal → quick; strong-deep signal → deep; otherwise ask the user. Do **not** silently default to either mode when the intent is ambiguous — the wrong default frustrates the user (quick for someone who wanted analysis, or a 5-minute deep run for someone who wanted "just free up space fast").

### Strong `quick` signals (any match → run quick, no question)

EN: `quick clean`, `quick cleanup`, `free up space fast`, `free some space now`, `clean fast`, `tidy up fast`
ZH: `快速清理`, `快速清一下`, `快点清理`, `马上腾点空间`, `先清一波`, `腾点空间`

### Strong `deep` signals (any match → run deep, no question)

EN: `deep clean`, `analyze`, `analyse`, `find what's eating`, `where did my disk go`, `find big files`, `audit my disk`
ZH: `深度清理`, `深度`, `分析空间`, `分析一下空间`, `空间都去哪了`, `找大头`, `找出占空间的`

### Ambiguous (no strong signal) → **ask the user**

Examples that trigger the question: `clean up my Mac`, `clean my Mac`, `Mac 空间满了`, `盘满了`, `磁盘满了`, `tidy up my Mac`, plain `cleanup`.

Use the `AskUserQuestion` tool with a single question, two options:

- **Quick clean** — "Free space fast (~30s). Auto-cleans low-risk caches and obvious old installers; skips bigger investigations."
- **Deep clean** — "Full audit (~2-5 min). Scans everything, asks per-item for risky stuff, generates a full report."

Honour the user's choice. If they pick "Other" (free text) and the text matches a strong signal above, use that mode; otherwise re-ask once.

### Escape hatch

If the user's wording is not in the lists but its meaning is unmistakable to you (e.g. an unambiguous translation, a clear hybrid phrase), you may pick the matching mode without asking. When in doubt, ask.

## What you must NOT do

1. **Never call `rm`, `mv`, `trash`, `tar`, `rsync`, or `tmutil deletelocalsnapshots` directly.** All cleanup writes go through `scripts/safe_delete.py`.
2. **Never scan or clean paths on the blacklist** in `references/cleanup-scope.md`.
3. **Never put filesystem paths, basenames, usernames, project names, or company names into the HTML report, SVG card, or share text.** Use `source_label` + `category` only. See `references/safety-policy.md` for the full redaction policy.
4. **Never edit the files in `assets/` in place.** Always `cp` them into `$WORKDIR` first and edit the copies.

## Workflow (six stages)

### Stage 1 · Mode identification

Apply the three-tier decision from "Mode selection" above:
1. Strong quick signal → `MODE=quick`.
2. Strong deep signal → `MODE=deep`.
3. Ambiguous → call `AskUserQuestion` with the two options described above; do not proceed until you have a mode.

Then create a per-run workdir (the parent dir may not exist on first run, so `mkdir -p` first):

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
which -a docker brew pnpm npm yarn pip uv cargo go gradle xcrun trash
ls -d ~/.cocoapods ~/.gradle ~/.m2 2>/dev/null
```

From the output, remember:
- macOS version.
- Filesystem free space before cleanup (`free_before`). Capture as bytes for later diff.
- Which enhancement tools are installed. Skip rows in `references/cleanup-scope.md` Tier E for missing tools.
- **Whether `trash` CLI is installed** (`which trash`). Record as `trash_cli=true|false` in your environment_profile.

Read `references/cleanup-scope.md` once — this is your map of **where to look** and **where never to touch**.

### Stage 2.5 · trash CLI nudge (only when missing)

If Stage 2 found `trash_cli=false`, before proceeding to Stage 3 surface a single short message to the user (not as `AskUserQuestion` — just inline text), e.g.:

> Heads-up: the optional `trash` CLI is not installed. `safe_delete.py` will fall back to `mv` into `~/.Trash`, which works but renames each item with a `-<timestamp>` suffix that looks odd in Finder. For a cleaner experience: `brew install trash`. I'll continue with the fallback unless you'd like to install first.

Then proceed to Stage 3 without waiting for an answer. The user can interrupt to install if they want; otherwise they have the heads-up. Do not nudge again in subsequent runs of the same session.

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
| `quick` | Execute without asking† | Batch confirm by category | Record as `defer` only; do **not** interact | Hidden |
| `deep` | Show list + pre-checked; ask for batch OK† | Batch confirm by category | Per-item hard confirm, show default `trash`, allow override | Show as read-only |

† L1 includes `sim_runtime` (dispatched to `xcrun simctl delete`, which itself refuses to delete a booted simulator) and `system_snapshots` (dispatched to `tmutil deletelocalsnapshots`). These are L1 because the Apple-provided tools carry their own safety guards — `safe_delete.py` never `rm -rf`s these categories.

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

4. Use the `Edit` tool to fill the **six** report regions in `$WORKDIR/report.html`. Match the paired markers exactly:
   - `<!-- region:summary:start -->` … `<!-- region:summary:end -->`: headline `freed_now` (the honest number), mode chip, L1-L4 count chips. If `pending_in_trash_bytes > 0`, also show a smaller "+ {pending_human} pending in trash" line.
   - `<!-- region:distribution:start -->` … `<!-- region:distribution:end -->`: one card per category, showing pre-clean size / freed / remaining candidates. Use `source_label` names only.
   - `<!-- region:actions:start -->` … `<!-- region:actions:end -->`: a list grouped by action type (auto-cleaned / confirmed / archived / migrated / deferred / skipped / failed). Each row: source_label + size + action badge + one-line reason. No paths.
   - `<!-- region:deferred:start -->` … `<!-- region:deferred:end -->`: recommendations for `deferred.jsonl` entries and L3/L4 observations, at category granularity.
   - `<!-- region:nextstep:start -->` … `<!-- region:nextstep:end -->`: **two fill modes depending on `pending_in_trash_bytes`**:
     - **`pending_in_trash_bytes > 0`** — fill with three pieces:
       1. A `<p class="pending">{pending_human} still in Trash</p>` headline.
       2. A `<code class="empty-cmd">osascript -e 'tell application "Finder" to empty the trash'</code>` block (user can copy with one click thanks to `user-select: all`).
       3. A `<p class="auto-note">` paragraph that **must include both**: (a) the dialog warning — "Running the command above will trigger a Finder confirmation dialog — click 'Empty Trash' there to actually clear it." and (b) the auto-empty hint — "macOS auto-empties 30 days after items enter the Trash if you've enabled Finder → Settings → Advanced → 'Remove items from the Trash after 30 days'."
     - **`pending_in_trash_bytes == 0`** — replace the placeholder with a single positive line: `<p class="all-good">All freed bytes are immediately reclaimed — no follow-up needed.</p>`. Do not leave the placeholder hint visible.
   - `<!-- region:share:start -->` … `<!-- region:share:end -->`: embedded SVG card (inline or via `<img>`), English share text in a `.share-text` block, Chinese share text below it, and an X share button.

   Budget: keep the combined inserted HTML under ~250 lines.

5. Fill the SVG placeholders in `$WORKDIR/share-card.svg`:
   - `${free_reclaimed}` → e.g. `37.4 GB` (single human-readable string, no path).
   - `${mode_label}` → `Quick Clean` or `Deep Clean`.
   - `${top_categories}` → up to 3 `source_label`s joined with ` · `, e.g. `Docker · Downloads · Xcode`.

6. Write the two share-text files. **Use `freed_now_bytes` as the headline** (not `reclaimed_bytes`) — share text must reflect bytes that are *actually* off the disk, not bytes still sitting in `~/.Trash`.

   - `$WORKDIR/share.en.txt` (default):
     ```
     I just reclaimed {freed_now} on my Mac with the mac-space-clean skill by @heyiamlin.

     Biggest wins: {top3_joined}.

     #macspaceclean #maccleanup #buildinpublic
     ```

   - `$WORKDIR/share.zh.txt`:
     ```
     我刚用 mac-space-clean 这个 skill 清理了 Mac,释放了 {freed_now} 空间,作者 @heyiamlin。

     这次最大的空间回收来自 {top3_joined_zh}。
     ```

   Only substitute: `{freed_now}` (human-readable string from `freed_now_bytes`), `{top3_joined}`, `{top3_joined_zh}`. Same `source_label` taxonomy applies; no paths, usernames, or project names.

7. **Spawn a redaction reviewer** sub-agent to independently scan `$WORKDIR/report.html` for leaks the deterministic validator cannot catch (project names, company names, made-up names that look like personal data). Use the `Agent` tool with the prompt template in `references/reviewer-prompts.md` (section "Redaction reviewer"), passing the report HTML verbatim.
   - Reviewer returns `{"violations": [...]}`.
   - Empty list → proceed.
   - Non-empty → edit `$WORKDIR/report.html` to remove/abstract each flagged snippet, then re-spawn the reviewer with the updated HTML. Cap retries at **2**. After the second failure, stop and tell the user which violations remained — do **not** show the report.

8. **Run the deterministic validator** as a second line of defence. The reviewer is fuzzy (catches semantic leaks); the validator is exact (catches structural problems and a fixed dictionary of forbidden literal substrings):

   ```bash
   python3 scripts/validate_report.py --report "$WORKDIR/report.html"
   ```

   Exit 0 → all good. Exit 1 → stdout JSON's `violations` lists each problem (`missing_region`, `empty_region`, `placeholder_left`, `leaked_fragment`). Fix every violation by editing `$WORKDIR/report.html` and re-run the validator until it returns 0. Do not show the user the report while violations remain.

9. Open the report:

   ```bash
   open "$WORKDIR/report.html"
   ```

10. Summarise to the user in one short paragraph that **always reports both numbers**:
   - `freed_now_bytes` — already off the disk.
   - `pending_in_trash_bytes` — waiting in `~/.Trash`; mention that emptying trash converts it to free space (the report's "One last step" section gives the one-line command).
   - `archived_count` if any (archive_source goes into the workdir, point user at it).
   - `deferred_count` and the report path.

   Honest framing: never report `reclaimed_bytes` to the user as "freed" — that field is back-compat only.

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
  "totals": {
    "scanned_bytes",
    "freed_now_bytes",          // disk already free (delete + migrate)
    "pending_in_trash_bytes",   // waiting in ~/.Trash (trash + archive originals)
    "archived_source_bytes",    // fully-successful archive originals
    "archived_count",
    "reclaimed_bytes",          // deprecated alias = freed_now + pending_in_trash
    "skipped_bytes",
    "deferred_bytes",
    "failed_bytes"
  },
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
  - `category`: `dev_cache | sim_runtime | pkg_cache | app_cache | logs | downloads | large_media | system_snapshots | orphan` — `sim_runtime` is dispatched via `xcrun simctl delete`, `system_snapshots` via `tmutil deletelocalsnapshots`; both bypass `rm`.
  - `action_status`: `success | archive_only_success | failed`
- **Degradation**: see §14-style matrix in `references/safety-policy.md`.
