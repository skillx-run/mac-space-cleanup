---
name: mac-space-cleanup
description: "Guide the agent through macOS disk space cleanup with quick/deep modes and L1-L4 risk grading. Trigger when the user says things like \"clean up my Mac\", \"free up disk space\", \"what's eating my disk\", \"Mac 空间满了\", \"快速清理 / 深度清理\", \"腾点空间\". Produces a bilingual (EN/ZH) HTML report with a runtime language toggle and matching share text, all attributed to @heyiamlin."
version: "0.6.0"
author: "heyiamlin"
---

# mac-space-cleanup

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
mkdir -p ~/.cache/mac-space-cleanup
WORKDIR=$(mktemp -d ~/.cache/mac-space-cleanup/run-XXXXXX)
```

**Locale detection.** Inspect the user's triggering message (the one that activated the skill) and decide `LOCALE` in this order — the first matching rule wins:

1. Contains Japanese kana (`[\u3040-\u30ff]`, hiragana or katakana) → `LOCALE=en`. Japanese isn't a first-class locale in v0.6; falling back to EN avoids serving JP users a Chinese report just because JP kanji overlap with the CJK Unified Ideographs block.
2. Contains CJK Unified Ideographs (`[\u4e00-\u9fff]`) and no kana from rule 1 → `LOCALE=zh`.
3. Everything else (English, Spanish, French, Russian, Arabic, Korean, …) → `LOCALE=en`.

Persist it:

```bash
echo "$LOCALE" > "$WORKDIR/locale.txt"
```

This file is read by Stage 6 to decide the report's default language and to pick which `share.{en,zh}.txt` the X share button links to. It also binds the agent: **any natural-language copy you generate from now on** (Stage 5 `actions.jsonl` reason, Stage 6 hero caption, action reasons, observations recommendations, and each item's `source_label`) **must be emitted in BOTH en and zh**. Static template labels are wired through the i18n dictionary and do not need per-run translation.

The runtime toggle button in the report still lets any user flip to the other locale manually — EN users can peek at ZH and vice versa — but Stage 1 picks the default. Third-language support (JP, KR, ES, …) is out of scope for v0.6; adding one requires extending `assets/i18n/strings.json` with a new subtree, relaxing the two-key-set validator check in `scripts/validate_report.py`, and giving the toggle more options.

**Dry-run detection.** Decide `DRY_RUN` from the triggering message and persist it next to `locale.txt` — Stage 5 and multiple Stage 6 branches read this flag, so it must be a single source of truth, not re-derived from conversation history each time:

- `DRY_RUN=true` if the triggering message contains any of: `--dry-run`, `dry run`, `dry-run`, `预演`, `模拟`, `演练` (case-insensitive).
- Otherwise `DRY_RUN=false`.

```bash
echo "$DRY_RUN" > "$WORKDIR/dry_run.txt"
```

Downstream readers:
- **Stage 5** must pass `--dry-run` to `safe_delete.py` iff this flag is true.
- **Stage 6 step 4** reads it to pick real-run vs dry-run copy for hero unit (§ "Hero unit tense") and nextstep (§ three fill modes).
- **Stage 6 step 6** reads it to pick real-run vs dry-run templates for `share.{en,zh}.txt`.
- **Stage 6 step 8** reads it to decide whether to pass `--dry-run` to `validate_report.py` (which asserts the banner + number-prefix markers).

Never infer dry-run state from "did I just pass --dry-run to safe_delete?" or from the conversation scroll-back — always read `$WORKDIR/dry_run.txt`.

Announce the mode and workdir to the user briefly.

### Stage 2 · Environment probe

Run these in parallel and summarise the result internally (do not dump raw output to the user):

```bash
sw_vers
df -h /
which -a docker brew pnpm npm yarn pip uv cargo go gradle xcrun trash \
         flutter fnm pyenv rustup
ls -d ~/.cocoapods ~/.gradle ~/.m2 ~/.nvm \
      ~/Library/Android/sdk ~/Library/Caches/JetBrains 2>/dev/null
```

The `which -a` line gates Tier E rows that have a CLI probe; the `ls -d` line gates rows with a directory probe (nvm has no CLI on PATH; Android SDK and JetBrains are detected by their marker dirs). Keep these two lines in sync with `references/cleanup-scope.md` Tier E — when a row is added there, extend the matching probe here.

From the output, remember:
- macOS version.
- Filesystem free space before cleanup (`free_before`). Capture as bytes for later diff.
- Which enhancement tools are installed (CLI or directory marker). Skip rows in `references/cleanup-scope.md` Tier E for which neither probe fired.
- **Whether `trash` CLI is installed** (`which trash`). Record as `trash_cli=true|false` in your environment_profile.

Read `references/cleanup-scope.md` once — this is your map of **where to look** and **where never to touch**.

### Stage 2.5 · trash CLI nudge (only when missing)

If Stage 2 found `trash_cli=false`, before proceeding to Stage 3 surface a single short message to the user (not as `AskUserQuestion` — just inline text), e.g.:

> Heads-up: the optional `trash` CLI is not installed. `safe_delete.py` will fall back to `mv` into `~/.Trash`, which works but renames each item with a `-<timestamp>` suffix that looks odd in Finder. For a cleaner experience: `brew install trash`. I'll continue with the fallback unless you'd like to install first.

Then proceed to Stage 3 without waiting for an answer. The user can interrupt to install if they want; otherwise they have the heads-up. Do not nudge again in subsequent runs of the same session.

### Stage 2.6 · History recall

Before scanning, load cross-run confidence so Stage 5 knows which `(source_label, category)` tuples the user has previously approved or declined.

```bash
python3 scripts/aggregate_history.py --workdir "$WORKDIR" > /dev/null
```

This writes `$WORKDIR/history.json`. The script also garbage-collects `run-*` directories older than the 20 most recent (pass `--no-gc` to disable, `--keep N` to widen the window). The caller's workdir is always pinned regardless of age.

Read `$WORKDIR/history.json` and keep it in memory as `HISTORY_BY_LABEL`, keyed by `(source_label, category)`. See `references/safety-policy.md` §"History-driven UI adjustments" for the rules that bind how this data may influence Stage 5 — summary: history can only collapse per-item prompts into batch prompts, **never cross a risk-level boundary and never auto-execute something that would otherwise ask**.

On the first run of the skill on a given Mac, `history.json` will have `runs_analyzed: 0` and `by_label: []` — that's fine; every tag falls through to default behaviour.

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
- `quick`: skip `large_media` category; skip Tier C browser caches deeper than one level; prefer Tier A + Tier E `dev_cache / pkg_cache`. **Skip Stage 3.5 entirely.**
- `deep`: scan everything in Tier A–E, plus `tmutil` snapshots, plus run Stage 3.5.

### Stage 3.5 · Project artifacts scan (deep mode only)

Skip in quick mode (`category-rules.md` §10 has `mode_hit_tags=["deep"]`).

**Tell the user before starting** — first run on a developer Mac with many repos can take 10–30s because `find` walks `~`. Single-line nudge inline (no `AskUserQuestion`):

> Scanning your projects for cleanable build artifacts (node_modules, target, .venv, …). May take 10–30 seconds on first run.

Then:

```bash
echo '{"roots": ["~"], "max_depth": 6}' \
  | python3 scripts/scan_projects.py > "$WORKDIR/projects.json"
```

`projects.json` shape (see `scripts/scan_projects.py` docstring): each project carries `root`, `markers_found` (e.g. `["go.mod", "package.json"]`), and an `artifacts[]` list with `path / subtype / kind`.

**Get sizes for each artifact** by writing a separate `$WORKDIR/paths-projects.json` (one entry per artifact path) and running `collect_sizes.py` again:

```bash
python3 scripts/collect_sizes.py < "$WORKDIR/paths-projects.json" \
  > "$WORKDIR/sizes-projects.json"
```

Two separate paths/sizes JSON files (rather than appending to the Stage 3 `paths.json` and re-running) keeps the audit trail clean: `sizes.json` stays a snapshot of system-wide candidates, `sizes-projects.json` is the project-artifacts snapshot. Combine them in memory when building the candidate list for Stage 4.

**Disambiguation rules at Stage 4** are authoritative in `references/category-rules.md` §10 — read it for the per-subtype L1/L2 grading and the `vendor` (Go-only) / `env` (Python-marker-only) carve-outs that depend on `markers_found`. `source_label` is always `"Project " + subtype` (e.g. `"Project node_modules"`); never include the project root path or basename here — those appear only in the live confirm dialog at Stage 5 per `safety-policy.md` confirm-stage exception.

If `scan_projects.py` exit is 1 (partial errors), check `stats.errors` and surface a one-line summary to the user (e.g. "Skipped 3 directories due to permission denials"). Continue with the projects that were scanned successfully.

### Stage 4 · Classify & grade

For each candidate, consult `references/category-rules.md` and `references/safety-policy.md` to assign:

- `category` (one of 10, see rules doc)
- `risk_level` (`L1 | L2 | L3 | L4`)
- `recommended_action` (`delete | trash | archive | migrate | defer | skip`)
- `source_label` (UI-safe label, see rules doc table)
- `mode_hit_tags` (which modes should surface this)
- `reason` (one sentence describing why this rule fired)

If a directory's purpose is unclear, investigate before classifying: `ls -lah`, `file`, `head -c 200`. Do not guess. Unclassifiable items become `category=orphan, risk_level=L4, action=skip`.

**Guard against reflexive orphan fallback.** `orphan` is a last-resort bucket, not a "don't know, move on" shortcut. Before assigning it, do a deliberate second pass against the three rule blocks most commonly skipped:

- Does the candidate sit inside a project root returned by `scripts/scan_projects.py` (Stage 3.5)? Check `references/category-rules.md` §10 (`project_artifacts`) — `node_modules`, `target`, `build`, `dist`, `.next`, `.nuxt`, `__pycache__`, `Pods`, `.venv`, `venv` are **project_artifacts**, not orphan. Only `vendor/` in a non-Go project and `env/` in a non-Python project are legitimate orphans, and the rules doc spells that out explicitly.
- Does the path match any pattern in §1 (`dev_cache` — Xcode/Docker/JetBrains/Go/Gradle/Flutter) or §3 (`pkg_cache` — Homebrew/npm/pnpm/pip/uv/Cargo/CocoaPods/Android SDK/nvm/fnm/pyenv/rustup)? Concrete tool-named caches almost always belong here.
- Does the path match §4 (`app_cache`), §5 (`logs`), §6 (`downloads`), §7 (`large_media`), §8 (`system_snapshots`)?

Only after all of the above fail does `orphan` apply. If a run ends up with orphan dominating the freed bytes (say, >30% of `freed_now`), treat that as a red flag and re-audit classifications before Stage 5 — a report whose biggest finding is "Unclassified large item" is almost always a sign of skipped rule consultation, not a genuinely orphan-dominated disk.

**Filter by mode**: drop items whose `mode_hit_tags` does not include the current mode.

### Stage 5 · Confirm & execute

Present the candidates to the user, grouped by risk level. The confirmation bar is different per mode:

| Mode | L1 | L2 | L3 | L4 |
| --- | --- | --- | --- | --- |
| `quick` | Execute without asking† | Batch confirm by category | Record as `defer` only; do **not** interact | Hidden |
| `deep` | Show list + pre-checked; ask for batch OK† | Batch confirm by category | Per-item hard confirm, show default `trash`, allow override | Show as read-only |

† L1 includes `sim_runtime` (dispatched to `xcrun simctl delete`, which itself refuses to delete a booted simulator) and `system_snapshots` (dispatched to `tmutil deletelocalsnapshots`). These are L1 because the Apple-provided tools carry their own safety guards — `safe_delete.py` never `rm -rf`s these categories.

**History-driven confidence downgrade**: for each candidate with a `(source_label, category)` entry in `HISTORY_BY_LABEL` (loaded in Stage 2.6) where `confirmed ≥ 3` and `declined == 0`, collapse the prompt **one step finer**:

| Default bar for this tag | Downgraded bar (history-driven) | Bound |
| --- | --- | --- |
| L3 per-item hard confirm | batch-confirm all instances of the tag with a single Y/N | never auto-executes; still asks once |
| L2 batch by category | unchanged (already minimal) | n/a |
| L1 quick-auto / deep batch | unchanged | n/a |

Hard rules — see `references/safety-policy.md` §"History-driven UI adjustments" for the authoritative statement:

- Never cross a risk-level boundary. History cannot move L3 to L2 or to auto-execute. L4 never becomes interactive.
- Never cross a mode boundary. Tags whose `mode_hit_tags` excludes the current mode stay hidden regardless of history.
- One decline resets. If `declined > 0` for a tag, revert to the default confirmation bar.
- The `_BLOCKED_PATTERNS` regex inside `safe_delete.py` still overrides everything.

**Project artifacts (`category=project_artifacts`, only present in deep mode)** get their own confirmation grouping rather than being lumped with other L1/L2:

> "Found 12 Node projects with node_modules totalling 9.2 GB. Delete all? [yes / yes-but-let-me-pick / no]"
>
> "Found 3 Python virtual environments totalling 1.4 GB. Move to Trash? [yes / yes-but-let-me-pick / no]"

If the user picks `yes-but-let-me-pick`, enter per-project selection. Per the **confirm-stage exception** in `references/safety-policy.md`, you MAY use the project root's basename (e.g. `foo-app`) as a label in this conversation so the user can pick by name:

> "Pick which Node projects to clean (sorted by size):
>   [x] foo-app — 2.4 GB
>   [x] bar-frontend — 1.8 GB
>   [ ] internal-secret-tool — 800 MB
>   ..."

But **NEVER** write project basenames to `report.html` / `share-card.{en,zh}.svg` / `share.{en,zh}.txt` / `cleanup-result.json`'s `source_label`. Those continue to use only the generic `source_label` ("Project node_modules"). The post-render redaction reviewer + `validate_report.py` will catch leaks if you slip.

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

The report is a **single long page** `report.html` that carries eight regions top-to-bottom: `hero` + `share` (the win and the share CTA, grouped in the header), then `impact`, `nextstep`, `distribution`, `actions`, `observations`, `runmeta`. Everything goes through the same redaction + validator gate before the page is opened.

The 10 numbered sub-steps below split into four phases:
- **Assemble** (1–2): compute `free_after`, write `cleanup-result.json`.
- **Fill** (3–6): copy templates, edit the eight paired-marker regions, fill the share card, write share text.
- **Review** (7–8): redaction reviewer (fuzzy, LLM-based) → `validate_report.py` (deterministic). Both must pass.
- **Show** (9–10): open the report, summarise to the user.

1. Collect host info and compute `free_after`:
   - `free_after`: `df -k / | tail -1 | awk '{print $4}'` → bytes.
   - `device`: `system_profiler SPHardwareDataType 2>/dev/null | awk -F': ' '/Model Name/ {print $2; exit}'` → e.g. `MacBook Pro`. If the command fails, fall back to `"Mac"`.
2. Assemble an in-memory `CleanupResult` (see schema below) from scan observations + `actions.jsonl`. Write it to `$WORKDIR/cleanup-result.json` — this is the local audit record and **may contain full paths**.
3. Copy templates into the workdir (never edit `assets/` in place):

   ```bash
   cp assets/report-template.html    "$WORKDIR/report.html"
   cp assets/report.css              "$WORKDIR/report.css"
   cp assets/share-card-template.svg "$WORKDIR/share-card.svg"
   cp assets/i18n/strings.json       "$WORKDIR/i18n.json"
   ```

3.5. **Wire the i18n dictionary and locale into the report skeleton.** Read `$WORKDIR/locale.txt` (the value written in Stage 1). Use the `Edit` tool twice against `$WORKDIR/report.html`:

   - Change `<html lang="en" data-locale="en">` so `data-locale` matches the persisted locale (e.g. `data-locale="zh"`). Leave `lang="en"` on the opening tag — the inline script rewrites it at runtime.
   - Replace the empty placeholder `<script type="application/json" id="i18n-dict">{"en":{},"zh":{}}</script>` with the full JSON from `$WORKDIR/i18n.json`. The content inside the script tag must be exactly the JSON, no pretty-printing required but no wrapping brackets / prose either.

   The embedded JS then hydrates every `data-i18n` node on first paint. `localStorage` is only written when the user explicitly clicks the language toggle, so on a fresh report `data-locale` wins.

4. Use the `Edit` tool to fill the eight paired-marker regions in `$WORKDIR/report.html`. Match the markers exactly; anything you insert must use `source_label` + `category` only, never paths. **Follow the three bilingual patterns below** depending on whether the node has agent-dynamic content:

   **Pattern A — Pure static copy → `data-i18n` key only.** The node has no agent-generated content; all static labels (section titles, button text, column headers, empty notes, risk-meter legend, footer, dry-run banner copy, nextstep dialog / 30-day hints, `nextstep.allgood`) go through the dictionary. Keep an English fallback inside the span so a JS failure still renders something readable, e.g.:
   `<a class="share-btn" ...><span data-i18n="share.btn">Share to X</span></a>`.

   **Pattern B — Agent number + static suffix → number bare, suffix via `data-i18n`.** When the dynamic part is a human-readable number (e.g. `2.3 GB`, `12 items`), emit the number once (it reads identically in both locales) and attach the localizable suffix as a sibling i18n span:
   - `{pending_human} still in Trash` → `<span class="pending">{pending_human}</span> <span data-i18n="nextstep.pending.suffix">still in Trash</span>`
   - `{N} items` → `<span class="count">{N}</span> <span data-i18n="actions.count.suffix">items</span>`
   - risk-meter segment glyph + bytes inline; the legend row uses `data-i18n="risk.legend.l1..l4"`.

   **Pattern C — Agent natural language → bilingual sibling `<span>` pair.** The node is a sentence or short phrase written by you. Emit both locales; CSS shows whichever matches `html[data-locale]`:
   ```html
   <p class="hero-caption">
     <span data-locale-show="en">Clean run on <strong>MacBook Pro</strong>, macOS 14.5, in 2m 14s.</span>
     <span data-locale-show="zh">在 <strong>MacBook Pro</strong> 上完成清理，macOS 14.5，耗时 2 分 14 秒。</span>
   </p>
   ```
   Applies to: hero caption, each `actions-row .reason`, each `observations-list .rec`, and each category title (`source_label`) wherever it appears (hero share text is separate — see step 6). Both locales are subject to the same redaction rules as the rest of the report; `validate_report.py` scans both blindly.

   **Filling rules for each region:**

   - `<!-- region:hero:start -->` … `<!-- region:hero:end -->`: a `.hero-body` wrapper containing exactly two blocks — (1) a `<p class="hero-headline">` with the `freed_now` number and a unit span beside it; (2) a `<p class="hero-caption">` one-line prose summary weaving in device / os / duration, e.g. `Clean run on <strong>MacBook Pro</strong>, macOS 14.5, in 2m 14s.`. Do **not** add meta chips, risk-level chips, or a pending-in-trash chip here — the full device / os / duration / run_id breakdown lives in `runmeta`, L1-L4 risk distribution lives in the `.risk-meter` inside `runmeta`, and the pending-in-trash number has its own big callout inside `nextstep`'s CTA card. Keeping hero minimal is deliberate.

     **Hero headline shape depends on whether the run is real or dry:**
     - **Real run** — number + Pattern A unit from the dictionary:
       `<p class="hero-headline">56.20 GB <span class="unit" data-i18n="hero.unit">freed</span></p>`
       (The zh dict value is `已释放` — past completion — which reads correctly because the bytes are actually off the disk.)
     - **Dry run** — whole headline wrapped as a Pattern C bilingual pair. Both the dry-run prefix (`would be` / `预计`) and the unit get baked into each locale span, because the ZH natural word order differs from EN:
       ```html
       <p class="hero-headline">
         <span data-locale-show="en">would be 56.20 GB <span class="unit">freed</span></span>
         <span data-locale-show="zh">预计 56.20 GB <span class="unit">可释放</span></span>
       </p>
       ```
       Do **not** reach for `data-i18n="hero.unit"` here; the unit text lives inline per locale. (Rationale: `已释放` under `预计` is a tense contradiction — "estimated already freed" — so the zh unit must shift to the modal-future `可释放`. EN stays `would be X GB freed`, which is idiomatic virtual mood.)
   - `<!-- region:share:start -->` … `<!-- region:share:end -->`: a **single** share button that carries **both** locale tweet targets so the page toggle can switch the composer text, not just the button label. Emit:
     ```html
     <a class="share-btn" target="_blank" rel="noopener"
        data-href-en="https://x.com/intent/tweet?text={encoded_en}"
        data-href-zh="https://x.com/intent/tweet?text={encoded_zh}"
        href="https://x.com/intent/tweet?text={encoded_initial}">
       <span data-i18n="share.btn">Share to X</span>
     </a>
     ```
     `{encoded_en}` is the URL-encoded content of `$WORKDIR/share.en.txt`; `{encoded_zh}` is the URL-encoded content of `$WORKDIR/share.zh.txt` (both are produced in step 6). `{encoded_initial}` is whichever one matches the current `LOCALE` — it's the JS-off fallback and also the value the page starts with before hydration. The embedded JS hydrates `href` on every locale toggle by reading `data-href-{en,zh}`. No SVG preview, no language tabs, no text panes — the button goes straight to a composed tweet. The allowed content in both encoded texts is still: reclaimed, mode, top-3 categories, mac-space-cleanup, @heyiamlin, hashtags.
   - `<!-- region:impact:start -->` … `<!-- region:impact:end -->`: an `.impact-grid` with two `.impact-card`s. First card: a `.water-bar` comparing `free_before → free_after`; each segment gets an inline `style="width:N%"` — `.used-before` = `(total - free_before)/total * 100`, `.freed-delta` = `freed_now/total * 100`, `.free-after` = `(free_after - freed_now)/total * 100`, and a `.water-legend` below with the before/after free-space labels. Second card: a `.stack-bar` of `freed_now_bytes` broken down by category, each `<span>` getting `style="flex-basis:N%"` as a percent of `freed_now_bytes`, followed by a `.stack-legend` with the top five categories (`source_label` only).
   - `<!-- region:nextstep:start -->` … `<!-- region:nextstep:end -->`: **three fill modes**, chosen by `$WORKDIR/dry_run.txt` first, then `pending_in_trash_bytes`. Static copy flows through Pattern A (`data-i18n`), the pending number through Pattern B, the dry-run predict block through Pattern C.
     - **`DRY_RUN=true`** (regardless of pending bytes) — a real dry-run never touches `~/.Trash`, so `nextstep.pending.suffix="仍在废纸篓中" / "still in Trash"` would be a factual lie and the Empty Trash command would be nonsensical. Render a predict-only info block instead, and emit **neither** the `<code class="empty-cmd">` nor the `<p class="auto-note">`:
       ```html
       <div class="cta-card">
         <p class="pending">
           <span data-locale-show="en">Dry-run preview — nothing was moved. If you re-run without <code>--dry-run</code>, <strong>{pending_human}</strong> would go into <code>~/.Trash</code> and this card would show the one-line command to empty it.</span>
           <span data-locale-show="zh">本次为预演 — 没有真的移动任何文件。若去掉 <code>--dry-run</code> 实跑，其中 <strong>{pending_human}</strong> 会进入 <code>~/.Trash</code>，届时此处会显示清空废纸篓的一行命令。</span>
         </p>
       </div>
       ```
       When dry-run `pending_in_trash_bytes == 0`, keep the same block but reword the size clause to "nothing would go to Trash either" / "也不会有文件进入废纸篓" — one shape beats branching on a zero.
     - **`DRY_RUN=false` and `pending_in_trash_bytes > 0`** — a `<div class="cta-card">` containing:
       1. `<p class="pending"><span class="pending-size">{pending_human}</span> <span data-i18n="nextstep.pending.suffix">still in Trash</span></p>`.
       2. `<code class="empty-cmd">osascript -e 'tell application "Finder" to empty the trash'</code>` (the `user-select: all` on `.empty-cmd` lets the user copy with one click).
       3. `<p class="auto-note"><span data-i18n="nextstep.auto.dialog">Running the command above will trigger a Finder confirmation dialog — click 'Empty Trash' there to actually clear it.</span> <span data-i18n="nextstep.auto.thirty">macOS auto-empties 30 days after items enter the Trash if you've enabled Finder → Settings → Advanced → 'Remove items from the Trash after 30 days'.</span></p>`. Both sentences carry `data-i18n` keys so the runtime toggle flips them together; keep the English fallback inline for JS-off robustness.
     - **`DRY_RUN=false` and `pending_in_trash_bytes == 0`** — a single line: `<p class="all-good" data-i18n="nextstep.allgood">All freed bytes are immediately reclaimed — no follow-up needed.</p>`. Do not leave the placeholder hint visible.
   - `<!-- region:distribution:start -->` … `<!-- region:distribution:end -->`: a `.dist-grid` with one `.dist-card--detailed` per category, each containing a `.dist-title` (source_label), a three-column `.dist-metrics` row (pre-clean / freed / remaining — label + value), and a `.dist-inline-bar` showing `freed / pre-clean` as an inline `style="width:N%"`.
   - `<!-- region:actions:start -->` … `<!-- region:actions:end -->`: one `<details class="actions-group">` per action type that has at least one row (auto-cleaned / confirmed / archived / migrated / deferred / skipped / failed), each opening to a `.actions-list` whose `.actions-row` children have four columns. The `cat` cell holds the `source_label` as a Pattern C bilingual pair; `size` is a bare human string; `act` is the badge (class one of `auto / trash / archive / migrate / defer / skip / failed`); `reason` is a Pattern C bilingual pair (one-line, no paths). The `<summary>` should carry a `.group-meta` span showing `<span class="count">{N}</span> <span data-i18n="actions.count.suffix">items</span>` + aggregate bytes. If you want to include the column headers (`cat / size / act / reason`) inside the `<details>` body, hang each on `data-i18n="actions.col.*"`.
   - `<!-- region:observations:start -->` … `<!-- region:observations:end -->`: an `.observations-grid` with two `.observations-col`s. Left column `<h3 data-i18n="section.obs.deferred">You deferred</h3>` lists aggregated `deferred.jsonl` entries (by category). Right column `<h3 data-i18n="section.obs.worth">Worth a look</h3>` lists L3/L4 items that were surfaced but not acted on. Each row uses `.observations-list` with `.label` (category source_label as a Pattern C bilingual pair) + `.rec` (one-line recommendation, Pattern C bilingual pair) + `.size`. If either side is legitimately empty, emit a `<p class="empty-note" data-i18n="section.obs.empty">Nothing here.</p>` — **not** `.hint`, which is reserved for unfilled template placeholders and is styled as a dashed "missing content" box that would misrepresent an intentional empty column.
   - `<!-- region:runmeta:start -->` … `<!-- region:runmeta:end -->`: a `<dl class="runmeta-grid">` with rows for `run_id` (wrap the value in `<code>`), `mode`, `started_at`, `finished_at` and duration, `host_info` (`device` / `os` / `free_before` / `free_after`), plus a `.risk-meter-label`, a `.risk-meter` with four `<span class="seg-l{1..4}">` segments (inline `style="flex-basis:N%"` of the L-level's bytes over the scanned total; include `<span class="glyph">●/▲/■/✕</span>` + byte text inside), and a `.risk-meter-legend`. Each `<dt>` uses `data-i18n="runmeta.label.*"` (`run_id` / `mode` / `started` / `finished` / `duration` / `device` / `os` / `free_before` / `free_after`); the `.risk-meter-label` uses `data-i18n="risk.meter.label"` and each legend chip uses `data-i18n="risk.legend.l1..l4"`. `<dd>` values (IDs, dates, byte strings, mode name) are bare — they read identically in both locales. If the mode name needs localisation (`Quick Clean` vs `快速清理`), emit it as a Pattern C bilingual pair.

   **Budget**: keep the combined inserted HTML under ~280 lines.

   **Dry-run marking (mandatory)**: when the run was a `--dry-run`, the report must clearly say so or it misleads the user into thinking files were touched. Requirements, enforced by `validate_report.py --dry-run`:
   - **Banner**: insert a sticky `<div class="dry-banner" data-i18n="drybanner">DRY-RUN — no files touched</div>` at the very top of the `<main class="report">` element, right inside the open tag. The `data-i18n` key lets the locale toggle switch the banner copy at runtime.
   - **Number prefixes** (every numeric headline: hero total, category bytes, action aggregates, pending, risk-meter bytes, runmeta free-space values): the prefix must be emitted as a **Pattern C bilingual pair** so the runtime locale toggle flips it together with the rest of the page. Two accepted shapes:
     - **Prefix-wrap (default, compact)** — for most numeric spots (risk-meter bytes, runmeta values, category bytes, action aggregates):
       ```html
       <span data-locale-show="en">would be </span><span data-locale-show="zh">预计 </span>28.6 GB
       ```
       Keep the trailing space inside each span so the number doesn't butt up against the prefix.
     - **Whole-headline wrap** — for the hero headline, where ZH and EN want different orderings (`would be 56.20 GB freed` / `预计 56.20 GB 可释放`). See § "Hero headline shape" above for the full template.
   - Accepted marker vocabulary (either locale, substring-checked by `validate_report.py --dry-run`): **`would be`**, **`would-be`**, **`(simulated)`** (EN) / **`预计`**, **`模拟`** (ZH). `预计` and `would be` are the defaults — use the rarer ones only when rewording an awkward sentence.
   - **Anti-pattern — do NOT emit the prefix as bare text keyed off Stage 1's `LOCALE`** (e.g. emit only `预计 56.20 GB` because this run is `zh`). That was v0.6 pre-release behaviour; after an EN toggle the page reads `预计 56.20 GB freed` — mixed-locale gibberish. The Pattern C wrap is the only correct form.
   - For real runs, neither the banner nor the prefixes are required.

   **Maintenance note**: if you change a `data-placeholder=...` string or add/remove a region in `assets/report-template.html`, also update `REGIONS` and `_PLACEHOLDER_MARKERS` in `scripts/validate_report.py` so the validator keeps catching unfilled regions.

5. Fill the SVG placeholders. The card is **not** embedded into `report.html`, but is written as a standalone artifact so users who want to attach an image to their tweet can grab it from the workdir. Because the SVG has no JS / locale toggle, emit **both** locale variants side by side:

   ```bash
   cp assets/share-card-template.svg "$WORKDIR/share-card.en.svg"
   cp assets/share-card-template.svg "$WORKDIR/share-card.zh.svg"
   # delete the un-suffixed copy from step 3; workdir keeps only the two localised ones
   rm -f "$WORKDIR/share-card.svg"
   ```

   Then Edit each file in place, substituting:

   | Placeholder | EN value (en.svg) | ZH value (zh.svg) |
   | --- | --- | --- |
   | `${free_reclaimed}` | `37.4 GB` (same human-readable string in both) | `37.4 GB` |
   | `${mode_label}` | `Quick Clean` / `Deep Clean` | `快速清理` / `深度清理` |
   | `${top_categories}` | up to 3 English `source_label`s joined with ` · ` | same three labels in Chinese, joined with ` · ` |
   | `${label_reclaimed}` | `reclaimed on my Mac` | `在我的 Mac 上释放了` |
   | `${label_top}` | `top sources` | `主要来源` |
   | `${label_by}` | `by` | `作者` |

   Chinese `source_label`s should stay ≤6 characters per label so the three concatenated entries fit the SVG's `t-top` row (28 px at ~1056 px available width). Truncate with an ellipsis if a label runs long.

6. Write the two share-text files. **Use `freed_now_bytes` as the headline** (not `reclaimed_bytes`) — share text must reflect bytes that are *actually* off the disk, not bytes still sitting in `~/.Trash`. The **English** file is what the region `share` button links to (URL-encoded); the Chinese file is a workdir artifact for users who want to post in Chinese.

   - `$WORKDIR/share.en.txt` (default, drives the button):
     ```
     I just reclaimed {freed_now} on my Mac with the mac-space-cleanup skill by @heyiamlin.

     Biggest wins: {top3_joined}.

     #macspaceclean #maccleanup #buildinpublic
     ```

   - `$WORKDIR/share.zh.txt`:
     ```
     用 @heyiamlin 的 mac-space-cleanup 给我的 Mac 清出了 {freed_now} 空间。

     这次清理的大头：{top3_joined_zh}。

     #mac清理 #macspaceclean #buildinpublic
     ```

   **Dry-run variants (use these when the run was `--dry-run`)** — the past-tense "reclaimed" / "清出了" misleads when nothing was touched:

   - `$WORKDIR/share.en.txt` (dry-run):
     ```
     Previewed with @heyiamlin's mac-space-cleanup — it estimates I could reclaim {freed_now} on my Mac.

     Biggest wins in the preview: {top3_joined}.

     #macspaceclean #maccleanup #buildinpublic
     ```

   - `$WORKDIR/share.zh.txt` (dry-run):
     ```
     预演一下：用 @heyiamlin 的 mac-space-cleanup，预计能在我的 Mac 上清出 {freed_now} 空间。

     这次预演的大头：{top3_joined_zh}。

     #mac清理 #macspaceclean #buildinpublic
     ```

   Only substitute: `{freed_now}` (human-readable string from `freed_now_bytes`), `{top3_joined}`, `{top3_joined_zh}`. Same `source_label` taxonomy applies; no paths, usernames, or project names.

   **Shape of `{top3_joined}`**: each entry is `source_label (human_size)`, the three joined by `, `. Concrete example: `Xcode DerivedData (6.8 GB), node_modules (3.2 GB), Docker build cache (2.3 GB)`. The per-entry size is the category's `freed_now_bytes` for this run, human-formatted the same way as the headline. `{top3_joined_zh}` follows the same shape (the size unit string does not need translation — `GB` / `MB` read identically in Chinese).

   **Picking the three for resonance**: a tweet that reads `Biggest wins: Xcode DerivedData (6.8 GB), node_modules (3.2 GB), Docker build cache (2.3 GB).` lands for any Mac developer — they've fought those exact folders and the numbers make the scale concrete. One that reads `Biggest wins: Developer caches, Old installers, Generic archives.` reads like a cleanup app's marketing copy, which is the opposite of what we want. When sorting candidates by freed bytes, prefer the specific tool / product name that `source_label` already carries (`Xcode DerivedData`, `node_modules`, `Docker build cache`, `iOS Simulators`, `JetBrains caches`, `Homebrew cache`) over generic category summaries (`Developer caches`, `Package caches`). `references/category-rules.md` already spells source_labels this way for every category; this guidance just says out loud: **copy the specific label, don't paraphrase it up a level of abstraction.** The redaction rules still stand — these names never include personal / project / company info, which is why they're safe to ship.

   **Never ship `orphan` / `Unclassified large item` / `未分类大项` as a top-3 entry.** That label is an explicit *classifier fallback* surfaced in the report's Observations column for the user's manual review — it is not a real category. Shipping it in share text reads as "the cleanup tool couldn't figure out what it cleaned" and undercuts the whole point of specific source_labels. Two rules:
   - If any of the top 3 candidates (by freed_now_bytes) is `orphan`, **skip it and pick the next-ranked concrete source_label**. Do this even if the skipped orphan bucket is numerically the largest.
   - If orphan legitimately dominates the run (e.g. a clean workstation with no developer footprint), it is a signal that the classifier mis-bucketed items that *should* have matched concrete category rules. Before shipping a `top3_joined` that's padded with orphan, re-examine `confirmed.json` — many project-artifact or dev-cache items get mis-routed to orphan when the agent forgets to consult `references/category-rules.md`'s §10 / §1 taxonomy.

7. **Spawn a redaction reviewer** sub-agent to independently scan `$WORKDIR/report.html` for leaks the deterministic validator cannot catch (project names, company names, made-up names that look like personal data). Use the `Agent` tool with the prompt template in `references/reviewer-prompts.md` (section "Redaction reviewer"), passing the report HTML verbatim. The report carries bilingual content (`data-locale-show="en"` / `"zh"` sibling spans for agent-generated copy, plus two translations for each `source_label`); the reviewer prompt already instructs reviewers to scan both locales — a leak in zh that is absent in en is still a leak.
   - Reviewer returns `{"violations": [...]}`.
   - Empty list → proceed.
   - Non-empty → edit `$WORKDIR/report.html` to remove/abstract each flagged snippet **in both locale variants** (a leak found in one language is assumed to have a twin in the other and must be scrubbed from both), then re-spawn the reviewer with the updated HTML. Cap retries at **2**. After the second failure, stop and tell the user which violations remained — do **not** show the report.

8. **Run the deterministic validator** as a second line of defence. The reviewer is fuzzy (catches semantic leaks); the validator is exact (catches structural problems and a fixed dictionary of forbidden literal substrings). When the run was a `--dry-run`, also pass `--dry-run` so the banner and number prefixes from step 4 are asserted:

   ```bash
   # real run
   python3 scripts/validate_report.py --report "$WORKDIR/report.html"

   # dry-run
   python3 scripts/validate_report.py --report "$WORKDIR/report.html" --dry-run
   ```

   Exit 0 → all good. Exit 1 → stdout JSON's `violations` lists each problem (`missing_region`, `empty_region`, `placeholder_left`, `leaked_fragment`, `dry_run_unmarked`). Fix every violation by editing `$WORKDIR/report.html` and re-run the validator until it returns 0. Do not show the user the report while violations remain.

9. Open the report:

   ```bash
   open "$WORKDIR/report.html"
   ```

10. Summarise to the user in one short paragraph that **always reports both numbers**:
   - `freed_now_bytes` — already off the disk (or "would-be freed" on a dry-run).
   - `pending_in_trash_bytes` — waiting in `~/.Trash`; mention that emptying trash converts it to free space (the report's "One last step" section gives the one-line command).
   - `archived_count` if any.
   - `deferred_count`.

   Then surface the artefacts as a click-to-open list. Agent hosts differ: Claude Code and Claude-Agent-SDK-based apps render markdown (so `[text](file://…)` becomes a real clickable anchor); Codex-style CLIs, plain shell pipes, CI log viewers and some TUIs show raw text. **Plain `file://` URLs are the lowest common denominator** — every modern terminal auto-detects them for Cmd+click, and they stay readable even when markdown is not rendered. `[text](url)` in a non-rendering host is arguably *worse* than a bare URL (the trailing `)` can confuse some URL detectors). So:

   **Default — plain URLs, one per line, URL at end of line.** A short label, a colon, two spaces, then the URL. No indent, no alignment padding, no two URLs sharing a line. Example (the `alice` and `A1B2C3` are illustrative — **substitute the actual `$WORKDIR`**):

   ```
   报告已打开：
   report.html           file:///Users/alice/.cache/mac-space-cleanup/run-A1B2C3/report.html

   其他工件：
   cleanup-result.json   file:///Users/alice/.cache/.../cleanup-result.json
   share-card.en.svg     file:///Users/alice/.cache/.../share-card.en.svg
   share-card.zh.svg     file:///Users/alice/.cache/.../share-card.zh.svg
   share.en.txt          file:///Users/alice/.cache/.../share.en.txt
   share.zh.txt          file:///Users/alice/.cache/.../share.zh.txt
   confirmed.json        file:///Users/alice/.cache/.../confirmed.json   (dry-run only)
   ```

   **Optional upgrade — markdown link list**, if the agent knows the current host renders markdown (Claude Code session, an SDK app with a markdown-capable UI). Markdown links dodge terminal URL-detection entirely so they survive visual wrap even better. Same content as above:

   ```markdown
   **报告已打开：** [report.html](file:///Users/alice/.cache/.../report.html)

   **其他工件：**
   - [cleanup-result.json](file:///Users/alice/.cache/.../cleanup-result.json) — 审计记录
   - [share-card.en.svg](file:///Users/alice/.cache/.../share-card.en.svg) — 英文分享卡片
   - [share-card.zh.svg](file:///Users/alice/.cache/.../share-card.zh.svg) — 中文分享卡片
   - [share.en.txt](file:///Users/alice/.cache/.../share.en.txt) — 英文推文
   - [share.zh.txt](file:///Users/alice/.cache/.../share.zh.txt) — 中文推文
   - [confirmed.json](file:///Users/alice/.cache/.../confirmed.json) — 回放基础（dry-run only）
   ```

   When in doubt, use the plain-URL form — it works everywhere, and any host that renders markdown will also auto-link a bare `file://` URL.

   Rules (both formats):
   - **One artefact per line / list item.** Do not combine `share.en.txt` + `share.zh.txt` onto one line.
   - The `confirmed.json` line is **dry-run only** — omit on real runs, where re-executing it just produces `action=skip, reason="already gone"` noise.
   - Substitute the real `$WORKDIR`; do not emit the literal `alice/A1B2C3` example.
   - At minimum include the report URL in the tersest summary.

   **Self-check on `share.{en,zh}.txt` before step 9 (no automation backstop).** `validate_report.py` scans `report.html` only; the share-text files are on an unchecked path. Re-read both files and confirm:
   - Verb tense matches the run: real-run → past (`reclaimed` / `清出了`); dry-run → future-tense template from step 6 (`estimates I could reclaim` / `预计能在我的 Mac 上清出`).
   - `{top3_joined}` / `{top3_joined_zh}` contain only concrete source_labels from `references/category-rules.md` — no `orphan` / `Unclassified large item` / `未分类大项`.
   - All three hashtags present (`#macspaceclean #maccleanup #buildinpublic` for EN, `#mac清理 #macspaceclean #buildinpublic` for ZH).
   - No path / username / project name slipped through (the redaction reviewer sub-agent from step 7 only saw `report.html`).

   Honest framing: never report `reclaimed_bytes` to the user as "freed" — that field is back-compat only.

## `cleanup-result.json` schema

```
{
  "run_id": "<timestamp-based>",
  "started_at": <iso8601>,
  "finished_at": <iso8601>,
  "mode": "quick" | "deep",
  "host_info": {"device": "MacBook Pro", "os": "macOS 14.x", "free_before": <bytes>, "free_after": <bytes>},
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

- **Workdir**: `~/.cache/mac-space-cleanup/run-XXXXXX`, per run.
- **Never direct-write for cleanup**: route through `scripts/safe_delete.py`.
- **Redaction**: UI/share output uses `source_label` + `category` only; see `references/safety-policy.md`.
- **Enumerations**:
  - `risk_level`: `L1 | L2 | L3 | L4`
  - `action`: `delete | trash | archive | migrate | defer | skip`
  - `category`: `dev_cache | sim_runtime | pkg_cache | app_cache | logs | downloads | large_media | system_snapshots | orphan` — `sim_runtime` is dispatched via `xcrun simctl delete`, `system_snapshots` via `tmutil deletelocalsnapshots`; both bypass `rm`.
  - `action_status`: `success | archive_only_success | failed`
- **Degradation**: see §14-style matrix in `references/safety-policy.md`.
