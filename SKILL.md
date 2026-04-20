---
name: mac-space-cleanup
description: "Guide the agent through macOS disk space cleanup with quick/deep modes and L1-L4 risk grading. Trigger when the user says things like \"clean up my Mac\", \"free up disk space\", \"what's eating my disk\", \"Mac 空间满了\", \"快速清理 / 深度清理\", \"腾点空间\". Produces a localized HTML report in the conversation's language and a matching share text, all attributed to @heyiamlin."
version: "0.11.0"
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

## Workflow (seven stages)

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

**Locale detection.** Decide the conversation's primary language from the user's triggering message and express it as a BCP-47 primary language subtag (e.g. `en`, `zh`, `ja`, `ko`, `es`, `fr`, `de`, `pt`, `ru`, `ar`). The default on ambiguity (mixed language, terse one-word trigger, ASCII-only phrasing) is `en`. No decision tree here — use the same judgement you'd apply to pick a reply language, then write it down:

```bash
echo "$LOCALE" > "$WORKDIR/locale.txt"
```

This file is read by Stage 6 to drive every natural-language node in the report, the share card (`share-card.svg`), and the share text (`share.txt`). The report is single-locale per run: you produce every hero caption, action reason, observation recommendation, dry-run note, and `source_label` rendering **once**, in `$LOCALE`. Static template labels carry `data-i18n` attributes with English baselines; Stage 6 step 3.5 decides whether to translate them via the embedded dictionary or leave the English baseline to render as-is. There is no runtime language toggle — the user's conversation language wins.

Right-to-left scripts (`ar`, `he`, `fa`, `ur`): Stage 6 step 3.5 sets `<html dir="rtl">`. Everything else defaults to `dir="ltr"`. CSS does not currently ship polished RTL tuning — basic direction flipping works, fine alignment is a known limitation.

**Dry-run detection.** Decide `DRY_RUN` from the triggering message and persist it next to `locale.txt` — Stage 5 and multiple Stage 6 branches read this flag, so it must be a single source of truth, not re-derived from conversation history each time:

- `DRY_RUN=true` if the user's intent in the triggering message is to **preview / rehearse / simulate** cleanup without touching the filesystem. Read the message for that intent in whatever language the user wrote — the skill is localised into many languages and your natural-language understanding is more reliable here than any fixed keyword list. Explicit signals include the CLI-style `--dry-run` / `dry run` / `dry-run` flag, and phrases like "preview only", "don't actually delete", "show me what you'd remove", "只预演不要真删", "先不要真的删", "essai à blanc", "Probelauf", etc.
- **Intent, not substring.** Do not trigger on a word that merely *happens to appear inside a cleanup target name*: "clean up my iOS **Simulator** caches" / "清理 iOS **模拟器** 缓存" is a request to delete real simulator runtimes (a Tier-B target), not a dry-run request, even though "simulator" / "模拟器" shares a root with "simulate" / "模拟".
- When the intent is ambiguous, prefer `DRY_RUN=false` and rely on Stage 5's per-item L2+ confirmation prompts to catch any remaining hesitation.
- Otherwise `DRY_RUN=false`.

```bash
echo "$DRY_RUN" > "$WORKDIR/dry_run.txt"
```

Downstream readers:
- **Stage 5** must pass `--dry-run` to `safe_delete.py` iff this flag is true.
- **Stage 6 step 4** reads it to pick real-run vs dry-run copy for hero unit (§ "Hero unit tense") and nextstep (§ three fill modes).
- **Stage 6 step 6** reads it to pick real-run vs dry-run templates for `share.txt`.
- **Stage 6 step 8** reads it to decide whether to pass `--dry-run` to `validate_report.py` (which asserts the banner + number-prefix markers).

Never infer dry-run state from "did I just pass --dry-run to safe_delete?" or from the conversation scroll-back — always read `$WORKDIR/dry_run.txt`.

Announce the mode and workdir to the user briefly.

### Stage 2 · Environment probe

Run these in parallel and summarise the result internally (do not dump raw output to the user):

```bash
sw_vers
df -h /
which -a docker brew pnpm npm yarn pip uv cargo go gradle xcrun trash \
         flutter fnm pyenv rustup bun deno \
         gem bundle composer poetry ccache sccache dart
ls -d ~/.cocoapods ~/.gradle ~/.m2 ~/.nvm \
      ~/Library/Android/sdk ~/Library/Caches/JetBrains \
      ~/Library/Caches/org.swift.swiftpm \
      ~/Library/Caches/org.carthage.CarthageKit \
      ~/.gem ~/.bundle ~/.composer ~/Library/Caches/composer \
      ~/Library/Caches/pypoetry \
      ~/.ccache ~/Library/Caches/ccache \
      ~/Library/Caches/Mozilla.sccache ~/.cache/sccache \
      ~/.pub-cache \
      ~/.cache/huggingface ~/.cache/torch \
      ~/.ollama ~/.cache/lm-studio ~/.lmstudio \
      ~/miniconda3/envs ~/anaconda3/envs \
      ~/opt/miniconda3/envs ~/opt/anaconda3/envs \
      ~/miniforge3/envs ~/mambaforge/envs ~/.mamba/envs \
      ~/Library/Caches/ms-playwright ~/.cache/ms-playwright \
      ~/Library/Caches/ms-playwright-driver ~/.cache/puppeteer \
      ~/.cache/whisper ~/.cache/openai-whisper \
      ~/.wandb ~/.cache/wandb 2>/dev/null
```

The `which -a` line gates Tier E rows that have a CLI probe; the `ls -d` line gates rows with a directory probe (nvm has no CLI on PATH; Android SDK and JetBrains are detected by their marker dirs). Keep these two lines in sync with `references/cleanup-scope.md` Tier E — when a row is added there, extend the matching probe here.

**Active iOS OS discovery (v0.9+).** When `xcrun` is on PATH, collect the iOS versions currently in active use — physically paired devices (via `devicectl`, Xcode 15+) and available simulators (via `simctl`, all Xcode versions). The union becomes `environment_profile.active_ios_versions` (list of `"17.4"`-style strings) and downgrades the matching `iOS DeviceSupport/<OS-version>` entries from L2 `trash` to L3 `defer` at Stage 4 — the user is almost certainly debugging against those OSes.

```bash
# Physical devices (Xcode 15+). `devicectl` returns JSON; older Xcode lacks it.
# Both xcrun and python3 stderr are silenced — the block must stay quiet
# whether xcrun is missing, the JSON schema drifts, or the inline script ever
# tripped over a Python version difference. Empty output is the correct
# failure mode; tracebacks bleeding into the agent transcript are not.
xcrun devicectl list devices --json-output - 2>/dev/null \
  | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin)
except Exception:
    sys.exit(0)
for dev in d.get("result",{}).get("devices",[]):
    v=dev.get("hardwareProperties",{}).get("productVersion") or ""
    # normalize "17.4.1" -> "17.4"; matched via equal-string compare against
    # DeviceSupport entries after those are similarly reduced to major.minor.
    parts=v.split(".")
    if len(parts)>=2: print(".".join(parts[:2]))' 2>/dev/null \
  > "$WORKDIR/active_ios_versions.txt"

# Available simulators (all Xcode versions).
xcrun simctl list devices available --json 2>/dev/null \
  | python3 -c 'import json,sys,re
try:
    d=json.load(sys.stdin)
except Exception:
    sys.exit(0)
for key in d.get("devices",{}).keys():
    # key looks like "com.apple.CoreSimulator.SimRuntime.iOS-17-4"
    m=re.search(r"iOS-(\d+)-(\d+)", key)
    if m: print(f"{m.group(1)}.{m.group(2)}")' 2>/dev/null \
  >> "$WORKDIR/active_ios_versions.txt"

sort -u "$WORKDIR/active_ios_versions.txt" -o "$WORKDIR/active_ios_versions.txt"
```

Empty / missing file → `active_ios_versions=[]`; treat as "no active-OS hint available" and keep the default L2 `trash` grading for every DeviceSupport entry. Do not treat the empty case as an error — most Macs without Xcode paired devices will have an empty simctl intersection on older runtimes, and that's fine.

From the output, remember:
- macOS version.
- Filesystem free space before cleanup (`free_before`). Capture as bytes for later diff.
- Which enhancement tools are installed (CLI or directory marker). Skip rows in `references/cleanup-scope.md` Tier E for which neither probe fired.
- **Whether `trash` CLI is installed** (`which trash`). Record as `trash_cli=true|false` in your environment_profile.
- **Active iOS versions** (read `$WORKDIR/active_ios_versions.txt`; may be empty). Used by Stage 4 to downgrade `iOS DeviceSupport` entries that match a currently-in-use OS from L2 `trash` to L3 `defer`.

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

For semantic/tool entries (not plain paths), probe directly. Each becomes a candidate item with `path="<semantic-prefix>:<entry>"`; `safe_delete.py` recognises the prefix and dispatches to the right CLI rather than `rm` (so `size_bytes` may be `0` here — the dispatcher reports actual freed bytes back via `actions.jsonl`):
- `docker system df` — parse for images / containers / volumes / build cache sizes. Surface as four items: `path="docker:build-cache"`, `path="docker:dangling-images"`, `path="docker:stopped-containers"` (each L1 delete via `docker container/image/builder prune -f`); **`docker:unused-volumes` is intentionally not surfaced** because volumes hold user data.
- `xcrun simctl list devices available` then infer which CoreSimulator device dirs are orphaned.
- `brew --cache` then `du -sh` on it. **Also surface** `path="brew:cleanup-s"` as one extra item (L1 delete; `safe_delete.py` runs `brew cleanup -s` to drop old Cellar versions and stale downloads — pinned formulae are preserved automatically by Homebrew).
- `tmutil listlocalsnapshots /` — each snapshot becomes an item with `path="snapshot:<full-name>"`.
- **Ollama per-model enumeration (v0.9+, deep mode only; in quick mode keep the v0.8 single-aggregate behaviour).** When `~/.ollama/models/manifests/` exists, walk the manifest tree and emit one candidate per model+tag with `path="ollama:<name>:<tag>"`, `source_label="Ollama model"`, `category="pkg_cache"`, `risk_level="L3"`, `recommended_action="defer"`, `mode_hit_tags=["deep"]`. The manifest tree layout is `manifests/<registry>/<namespace>/<name>/<tag>` — each leaf file is one manifest; reconstruct the UI name from the `<registry>/<namespace>/<name>` prefix (see the registry mapping rules in `references/category-rules.md` §3 Ollama block; the `safe_delete.py` dispatcher uses the same rules in the other direction). Do NOT also surface the aggregate `~/.ollama/models/` path in deep mode — per-model entries and the aggregate would double-count bytes. If the manifest walk fails for any reason (unexpected layout, permission error), fall back to the v0.8 single-aggregate behaviour. `size_bytes` may be `0`; `safe_delete.py`'s dispatcher computes the real exclusive-blob byte count via reference counting and overrides `size_before_bytes` in `actions.jsonl`.

Semantic-path size hints: for `brew:cleanup-s` you can pre-estimate via `brew cleanup -ns` (dry-run) and parse the "would remove" output; for the three `docker:*` items, parse the matching row of `docker system df` (Reclaimable column); for `ollama:<name>:<tag>` items the dispatcher always recomputes the exclusive-blob byte count from on-disk blob sizes so any Stage 3 hint is overridden — pass `0` unless you have a local heuristic (`ollama list` prints approximate model sizes in its SIZE column but those reflect total model weight, not exclusive-to-this-tag weight, so they overshoot for tags that share layers with a sibling). When the hint is unavailable use `0` and the dispatcher will report the real freed bytes.

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

`projects.json` shape (see `scripts/scan_projects.py` docstring): each project carries `root`, `markers_found` (e.g. `["go.mod", "package.json"]`), `version_pins` (e.g. `{"python": ["3.11.4"], "node": ["18"]}` — may be `{}` if no pin files exist), and an `artifacts[]` list with `path / subtype / kind`.

**Version-pin union for Tier E per-version sweeps (v0.9+).** Before classifying `~/.pyenv/versions/*` or `~/.nvm/versions/node/*` candidates, collect the union of `project.version_pins.python` across all scanned projects and append it to the pyenv exclusion set (alongside `pyenv version --bare` — the global default). Same for `version_pins.node` and nvm. This replaces the older "agent must `cd` into each project and run `pyenv local`" choreography with a single-pass scan. Leave the existing CLI-based fallback ("if version_pins is `{}`, still run `pyenv version --bare`") in place for projects that lack pin files but still pin via shell-level `PYENV_VERSION`.

**Get sizes for each artifact** by writing a separate `$WORKDIR/paths-projects.json` (one entry per artifact path) and running `collect_sizes.py` again:

```bash
python3 scripts/collect_sizes.py < "$WORKDIR/paths-projects.json" \
  > "$WORKDIR/sizes-projects.json"
```

Two separate paths/sizes JSON files (rather than appending to the Stage 3 `paths.json` and re-running) keeps the audit trail clean: `sizes.json` stays a snapshot of system-wide candidates, `sizes-projects.json` is the project-artifacts snapshot. Combine them in memory when building the candidate list for Stage 4.

**Disambiguation rules at Stage 4** are authoritative in `references/category-rules.md` §10 — read it for the per-subtype L1/L2 grading and the `vendor` (Go-only) / `env` (Python-marker-only) / `_build` (Elixir-only) / `coverage` (JS-or-Python-marker-only) carve-outs that depend on `markers_found`. `source_label` is always `"Project " + subtype` (e.g. `"Project node_modules"`, `"Project coverage"`); never include the project root path or basename here — those appear only in the live confirm dialog at Stage 5 per `safety-policy.md` confirm-stage exception.

If `scan_projects.py` exit is 1 (partial errors), check `stats.errors` and surface a one-line summary to the user (e.g. "Skipped 3 directories due to permission denials"). Continue with the projects that were scanned successfully.

**Large-directory surfacing (deep mode, tail of Stage 3.5).** `category-rules.md` §7 `large_media` includes a `du -d 2 ~` probe for any orphan directory ≥ 2 GiB that other rules miss. Run it after `scan_projects.py` so items that `scan_projects` already grouped as `project_artifacts` aren't double-surfaced:

```bash
# macOS BSD `du` defaults to 512-byte blocks; `-k` forces 1 KB so the
# awk threshold reads as "≥ 2 GiB in KB". `timeout 45` caps the scan
# so a multi-TB $HOME doesn't block the pipeline.
timeout 45 du -k -d 2 ~ 2>/dev/null \
  | awk '$1 >= 2*1024*1024 { print }' \
  | sort -rn \
  | head -30 \
  > "$WORKDIR/large-dirs.txt"
```

Then fold the output into the candidate list:

1. Normalise every path before comparison — expand `~` to `$HOME` and take `realpath` on both the large-dirs output and your existing candidate set (Stage 3 + Stage 3.5). Without normalisation `~/Library/Caches` and `/Users/alice/Library/Caches` compare unequal and the entry gets surfaced twice.
2. Drop any path that is already in the candidate set, or that matches a blacklist entry from `cleanup-scope.md` (the `safe_delete.py::_BLOCKED_PATTERNS` backstop catches what the agent misses, but filter here so the user doesn't see noise).
3. Remaining entries become `category=large_media`, `risk_level=L3`, `recommended_action=defer`, `source_label="Unclassified large directory"` *as the default*. Step 4 may refine `category` and `source_label` before this default is finalised.
4. **Orphan investigation pass** — for each remaining entry from step 3, run a brief read-only investigation per `references/safety-policy.md` §"Orphan investigation" before finalising the labels. Use at most 6 commands per candidate from this set:
   - `ls -lah <path>` (top-level contents, 1 call)
   - `file <path>/<file>` (at most 3 representative files)
   - `head -c 200 <file>` (at most 2 README / config files)
   - Existence checks for marker files: `.gguf`, `.safetensors`, `pytorch_model.bin`, `model_index.json`, `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `mix.exs`, `Pipfile`, `.iso`, `.dmg`, large `.mp4` / `.mov`.

   Based on the findings, **refine** `category` (must be ∈ §1-§9 of `category-rules.md`; **never §10 `project_artifacts`** — that category is reserved for items returned by `scan_projects.py`) and `source_label` (use a canonical label from the §3-end source_label table, or coin a new one following the convention "tool/product name + category descriptor" such as `"ML model cache"`, `"Diffusion model cache"`, `"Conda env cache"`, `"AI training dataset"`). Set `reason` to one short sentence describing the evidence (e.g. `"found .gguf files indicating local LLM model cache"`).

   **Hard locks — `risk_level` stays L3 and `recommended_action` stays `defer`**, regardless of what the refined category's defaults would otherwise be. Even if the agent confidently identifies the directory as a Homebrew cache (canonical L1 `delete`) or a HuggingFace cache (canonical L3 `defer`), the du-probe-pathway item stays L3 / defer. The fact that the directory was discovered by a fallback probe rather than a whitelisted path is the signal that it is non-canonical and not eligible for the canonical risk treatment. See `safety-policy.md` §"Orphan investigation" and Operating invariant #7 for the full rationale.

   When the investigation cannot pin a more specific category (no marker matched, README missing or unhelpful), keep step 3's defaults — `category=large_media`, `source_label="Unclassified large directory"`.

   Quick heuristic table (not exhaustive — apply judgement):
   - `.gguf` / `.safetensors` / `pytorch_model.bin` → `pkg_cache`, `source_label="ML model cache"`
   - `model_index.json` (Diffusers) → `pkg_cache`, `source_label="Diffusion model cache"`
   - `.iso` / `.dmg` / many `.mp4` / `.mov` → keep `large_media`, `source_label="Media archive"`
   - `package.json` without a `.git` sibling → `orphan`, `source_label="Orphan Node project"` (NOT `project_artifacts` — that requires `.git` and goes through `scan_projects.py`; NOT `app_cache` either — that bucket is for user-app caches like Safari / IM clients per §4, not for abandoned project workspaces. Mirrors the §10 convention where a non-Go `vendor/` falls back to `orphan` rather than being forced into a category that doesn't fit.)
   - `pyproject.toml` / `requirements.txt` without a `.git` sibling → `orphan`, `source_label="Orphan Python project"` (same rationale)
   - README explicitly names a tool → use that tool's name in `source_label` (e.g. README mentions Plex → `"Plex transcode cache"`)

Redaction note: `Unclassified large directory` is a deliberately generic `source_label` — no path fragment, basename, or container name enters it. The same redaction rule applies to any newly coined label produced by step 4: tool / product / category descriptors only, never paths or basenames. Because L3 `defer` contributes zero `freed_now_bytes`, none of these labels can surface in `share.txt`'s top-3 either; Stage 6 step 6's existing "skip orphan, take next concrete label" guard covers it naturally.

### Stage 4 · Classify & grade

For each candidate, consult `references/category-rules.md` and `references/safety-policy.md` to assign:

- `category` (one of 10, see rules doc)
- `risk_level` (`L1 | L2 | L3 | L4`)
- `recommended_action` (`delete | trash | archive | migrate | defer | skip`)
- `source_label` (UI-safe label, see rules doc table)
- `mode_hit_tags` (which modes should surface this)
- `reason` (one sentence describing why this rule fired)

If a directory's purpose is unclear, investigate before classifying: `ls -lah`, `file`, `head -c 200`. Do not guess. Unclassifiable items become `category=orphan, risk_level=L4, action=skip`.

**Refine `app_cache` source_label for creative apps** (v0.9+): after assigning `category=app_cache`, consult `references/category-rules.md` §4's "Source label refinement for creative apps" table before falling back to the generic `"System caches"` / `"Editor cache"` labels. Adobe Media Cache, Final Cut Pro, and Logic Pro paths have specific labels that make the report name the actual workflow. Never descend into any `Adobe/*/Auto-Save/**` path — those are user work, not cache, and are blocked in both the blacklist and `safe_delete.py`.

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

But **NEVER** write project basenames to `report.html` / `share-card.svg` / `share.txt` / `cleanup-result.json`'s `source_label`. Those continue to use only the generic `source_label` ("Project node_modules"). The post-render redaction reviewer + `validate_report.py` will catch leaks if you slip.

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

The 9 numbered sub-steps below split into four phases:
- **Assemble** (1–2): compute `free_after`, write `cleanup-result.json`.
- **Fill** (3–6): copy templates, edit the eight paired-marker regions, fill the share card, write share text.
- **Review** (7–8): redaction reviewer (fuzzy, LLM-based) → `validate_report.py` (deterministic). Both must pass.
- **Show** (9): summarise to the user. **Stage 7** then self-checks `share.txt` and opens the report.

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

3.5. **Wire locale and (if needed) translate the i18n dictionary.** Read `$WORKDIR/locale.txt` (the value written in Stage 1).

   First, update the opening `<html>` tag so `lang`, `data-locale`, and `dir` all reflect `$LOCALE`:
   - `lang="$LOCALE"` and `data-locale="$LOCALE"` (e.g. `lang="ja" data-locale="ja"`).
   - `dir="rtl"` when `$LOCALE` is `ar`, `he`, `fa`, or `ur`; otherwise `dir="ltr"`.

   Then decide what goes inside the `<script type="application/json" id="i18n-dict">...</script>` container:
   - **If `$LOCALE == en`**: leave it as `{}`. The template ships English baseline text inside every `<span data-i18n="...">` node, so the hydration script has nothing to replace and the page renders English directly. Skip the rest of this step.
   - **If `$LOCALE != en`**: open `$WORKDIR/i18n.json` (the flat EN dict copied in step 3), translate **every** value into `$LOCALE` — all ~40 keys, **in a single mental pass** (read the full dict, produce all translations together as one response, don't iterate key-by-key) — and write the result as a JSON object into the container. Use one `Edit` call that replaces `{}` with the serialized dict:
     ```
     # Pseudocode — what you actually do as a single edit
     Edit(
       file_path="$WORKDIR/report.html",
       old_string='<script type="application/json" id="i18n-dict">{}</script>',
       new_string='<script type="application/json" id="i18n-dict">{"doc.title":"<translated>","brand.by":"<translated>",...,"footer.generated":"<translated>"}</script>',
     )
     ```
     Keys are preserved verbatim; only the values are translated. No pretty-printing required — serialize the JSON compactly on one line.

   Translation quality notes:
   - Keep labels short and idiomatic in the target language — match natural UI phrasing, not literal word-by-word translation.
   - Preserve any leading / trailing whitespace inside a value that carries grammatical meaning (e.g. a trailing space before a number in a label like `"Free before "`).
   - Brand strings (`mac-space-cleanup`, `@heyiamlin`, `macOS`, `GB`, `MB`) stay unchanged even in target-language values.

   The embedded hydration script (see step 4's "Static labels" note) replaces each matched `data-i18n` key's textContent on first paint. A key present in the dict but absent from the template, or a key in the template but absent from `strings.json`, is a structural bug — `validate_report.py` will flag it in step 8.

4. Use the `Edit` tool to fill the eight paired-marker regions in `$WORKDIR/report.html`. Match the markers exactly; anything you insert must use `source_label` + `category` only, never paths. All agent-authored natural-language content is written **once, directly in `$LOCALE`** — no sibling-span locale pairs, no `data-locale-show` markup.

   **Static labels (template already handles these).** Nodes with `data-i18n="<key>"` carry an English baseline inside the span. You do not rewrite them at fill time — step 3.5 either left the dict as `{}` (English run, baseline renders directly) or populated it with translations (non-English run, the short hydration script swaps text on load). When a fill rule below says "label via `data-i18n=..`", just emit the `data-i18n` span with the English fallback text; the dict plumbing takes care of the rest.

   **Dynamic prose.** Hero caption, action reasons, observation recommendations, `source_label` rendering, and dry-run prose go into the HTML as plain text in `$LOCALE`. One language per node, no duplicates.

   **Number + localizable suffix.** When a node composes an agent-emitted number with a localizable suffix (e.g. `{N} items`, `{pending_human} still in Trash`), emit the number in a bare span and hang the suffix on a `data-i18n` span so the dict owns its translation:
   - `{pending_human} still in Trash` → `<span class="pending-size">{pending_human}</span> <span data-i18n="nextstep.pending.suffix">still in Trash</span>`
   - `{N} items` → `<span class="count">{N}</span> <span data-i18n="actions.count.suffix">items</span>`

   **Class vocabulary is closed.** The class names in the snippets below are the complete set the agent may emit inside fill regions. Do **not** invent new class names — every class must appear in `assets/report.css`. `validate_report.py` runs a class-allowlist lint after render and will flag any unknown class as `undefined_class`. If a new visual element is ever needed, it must land as a coordinated `report.css` + `SKILL.md` + test change — not a one-off improvisation during rendering.

   **Filling rules for each region:**

   - `<!-- region:hero:start -->` … `<!-- region:hero:end -->`: a `.hero-body` wrapper containing exactly two blocks — (1) a `<p class="hero-headline">` with the `freed_now` number and a unit span; (2) a `<p class="hero-caption">` one-line prose summary in `$LOCALE` weaving in device / os / duration. EN example: `Clean run on <strong>MacBook Pro</strong>, macOS 14.5, in 2m 14s.`. Do **not** add meta chips, risk-level chips, or a pending-in-trash chip here — the full device / os / duration / run_id breakdown lives in `runmeta`, L1-L4 risk distribution lives in the `.risk-meter` inside `runmeta`, and the pending-in-trash number has its own big callout inside `nextstep`'s CTA card. Keeping hero minimal is deliberate.

     **Hero headline shape:**
     - **Real run** — bare number + `data-i18n="hero.unit"` span:
       `<p class="hero-headline">56.20 GB <span class="unit" data-i18n="hero.unit">freed</span></p>`
       The dict carries the target-language rendering of `freed` when `$LOCALE != en`.
     - **Dry run** — the number gets a `<span class="dryrun-prefix">` sibling and the unit is emitted **without** `data-i18n` (tense shifts across locales — past "freed" vs modal-future "would be freed" / "可释放" — so the dict can't carry one answer). Write both the prefix and the unit in `$LOCALE`. Examples:
       - EN: `<p class="hero-headline"><span class="dryrun-prefix">would be </span>56.20 GB <span class="unit">freed</span></p>`
       - ZH: `<p class="hero-headline"><span class="dryrun-prefix">预计 </span>56.20 GB <span class="unit">可释放</span></p>`
       `validate_report.py --dry-run` checks that the `.dryrun-prefix` wrapper is present; it does not match on vocabulary, so any target-language phrasing is accepted.

   - `<!-- region:share:start -->` … `<!-- region:share:end -->`: a single share button pointing at one URL-encoded `share.txt`. Emit:
     ```html
     <a class="share-btn" target="_blank" rel="noopener"
        href="https://x.com/intent/tweet?text={encoded_share_txt}">
       <span data-i18n="share.btn">Share to X</span>
     </a>
     ```
     `{encoded_share_txt}` is the URL-encoded content of `$WORKDIR/share.txt` (produced in step 6). The button label goes through the dict via `data-i18n="share.btn"`. The allowed content in the tweet is still: reclaimed, mode, top-3 categories, mac-space-cleanup, @heyiamlin, hashtags.

   - `<!-- region:impact:start -->` … `<!-- region:impact:end -->`: an `.impact-grid` with two `.impact-card`s.

     **Card 1 — water-bar** (comparing `free_before → free_after`):
     ```html
     <div class="impact-card">
       <div class="water-bar">
         <span class="used-before" style="width:{A}%"></span>
         <span class="freed-delta" style="width:{B}%"></span>
         <span class="free-after"  style="width:{C}%"></span>
       </div>
       <p class="water-legend">
         <span><b>{free_before_human}</b> <span data-i18n="runmeta.label.free_before">Free before</span></span>
         <span><b>{free_after_human}</b>  <span data-i18n="runmeta.label.free_after">Free after</span></span>
       </p>
     </div>
     ```
     `A` = `(total - free_before)/total * 100`; `B` = `freed_now/total * 100`; `C` = `(free_after - freed_now)/total * 100`.

     **Card 2 — stack-bar + stack-legend** (top five categories of `freed_now_bytes`). **Use the CSS-defined `.seg-1..5` classes; do not emit inline `background` colour** — the design system's `--seg-1..5` palette owns the hues.
     ```html
     <div class="impact-card">
       <div class="stack-bar">
         <span class="seg-1" style="flex-basis:{P1}%" title="{label1}"></span>
         <span class="seg-2" style="flex-basis:{P2}%" title="{label2}"></span>
         <span class="seg-3" style="flex-basis:{P3}%" title="{label3}"></span>
         <span class="seg-4" style="flex-basis:{P4}%" title="{label4}"></span>
         <span class="seg-5" style="flex-basis:{P5}%" title="{label5}"></span>
         <span class="seg-rest" style="flex-basis:{P_rest}%"></span>
       </div>
       <ul class="stack-legend">
         <li><span class="swatch seg-1"></span><span class="name">{label1}</span><span class="bytes">{bytes1}</span></li>
         <!-- repeat for seg-2 … seg-5 -->
       </ul>
     </div>
     ```
     Fewer than 5 categories? Emit only the populated `<li>`s and segments; do not emit empty ones (they still reserve padding).

   - `<!-- region:nextstep:start -->` … `<!-- region:nextstep:end -->`: **three fill modes**, chosen by `$WORKDIR/dry_run.txt` first, then `pending_in_trash_bytes`. All prose is written in `$LOCALE`.
     - **`DRY_RUN=true`** (regardless of pending bytes) — a real dry-run never touches `~/.Trash`, so claiming items are "still in Trash" would be a factual lie and an Empty Trash command would be nonsensical. Render a predict-only info block instead; do **not** emit `<code class="empty-cmd">` or `<p class="auto-note">`:
       ```html
       <div class="cta-card">
         <p class="pending">
           Dry-run preview — nothing was moved. If you re-run without <code>--dry-run</code>, <strong>{pending_human}</strong> would go into <code>~/.Trash</code> and this card would show the one-line command to empty it.
         </p>
       </div>
       ```
       Translate the full sentence into `$LOCALE`. When dry-run `pending_in_trash_bytes == 0`, keep the same block but reword the size clause to "nothing would go to Trash either" (or the `$LOCALE` equivalent) — one shape beats branching on a zero.
     - **`DRY_RUN=false` and `pending_in_trash_bytes > 0`** — a `<div class="cta-card">` containing:
       1. `<p class="pending"><span class="pending-size">{pending_human}</span> <span data-i18n="nextstep.pending.suffix">still in Trash</span></p>`.
       2. `<code class="empty-cmd">osascript -e 'tell application "Finder" to empty the trash'</code>` (the `user-select: all` on `.empty-cmd` lets the user copy with one click).
       3. `<p class="auto-note"><span data-i18n="nextstep.auto.dialog">Running the command above will trigger a Finder confirmation dialog — click 'Empty Trash' there to actually clear it.</span> <span data-i18n="nextstep.auto.thirty">macOS auto-empties 30 days after items enter the Trash if you've enabled Finder → Settings → Advanced → 'Remove items from the Trash after 30 days'.</span></p>`. Both sentences go through the dict for non-English locales.
     - **`DRY_RUN=false` and `pending_in_trash_bytes == 0`** — a single line: `<p class="all-good" data-i18n="nextstep.allgood">All freed bytes are immediately reclaimed — no follow-up needed.</p>`. Do not leave the placeholder hint visible.

   - `<!-- region:distribution:start -->` … `<!-- region:distribution:end -->`: a `.dist-grid` with one `.dist-card--detailed` per category. **Use the CSS-defined `.metric-label` / `.metric-value` / `.metric-value.freed` class names**, not improvised shorthands. Metric column labels (pre-clean / freed / remaining) are **per-run prose in `$LOCALE`** — write them inline, do **not** route through the i18n dict (mirrors how `mode_label` / `action_title` are handled):
     ```html
     <div class="dist-card--detailed">
       <div class="dist-header">
         <div class="dist-title">{source_label in $LOCALE}</div>
         <div class="dist-metrics">
           <div>
             <div class="metric-label">{preclean_label in $LOCALE}</div>
             <div class="metric-value">{preclean_human}</div>
           </div>
           <div>
             <div class="metric-label">{freed_label in $LOCALE}</div>
             <div class="metric-value freed">{freed_human}</div>
           </div>
           <div>
             <div class="metric-label">{remaining_label in $LOCALE}</div>
             <div class="metric-value">{remaining_human}</div>
           </div>
         </div>
       </div>
       <div class="dist-inline-bar"><span style="width:{freed_over_preclean}%"></span></div>
     </div>
     ```
     Label vocabulary by locale — EN `Pre-clean` / `Freed` / `Remaining`; zh-CN `清理前` / `已释放` / `剩余`; ja `削減前` / `解放` / `残り`; pick the natural UI wording for other locales. Keep each label short (≤ ~12 display columns) so the three metrics fit one row on desktop.

   - `<!-- region:actions:start -->` … `<!-- region:actions:end -->`: one `<details class="actions-group">` per action type that has at least one row (auto-cleaned / confirmed / archived / migrated / deferred / skipped / failed). **Use the CSS-defined `.act` + modifier class names** (`.act.auto / .trash / .archive / .migrate / .defer / .skip / .failed`), not `.badge.*`:
     ```html
     <details class="actions-group" open>
       <summary>
         <span>{action_title in $LOCALE, e.g. "Auto-cleaned"}</span>
         <span class="group-meta">
           <span class="count">{N}</span> <span data-i18n="actions.count.suffix">items</span>
           · {aggregate_bytes_human}
         </span>
       </summary>
       <ul class="actions-list">
         <li class="actions-row">
           <span class="cat">{source_label in $LOCALE}</span>
           <span class="size">{size_human}</span>
           <span class="act auto">{act_label in $LOCALE}</span>
           <span class="reason">{reason_sentence in $LOCALE}</span>
         </li>
         <!-- more rows … -->
       </ul>
     </details>
     ```
     **Do not emit a column-header row** (no `.actions-head`, no `<li class="actions-row header">`). The `<summary>` already conveys the group's identity (e.g. `Auto-cleaned · 101 items · 59.18 GB`); a separate header row duplicates semantically and invites an extra class outside the allowlist. Column roles are carried by cell classes (`.cat / .size / .act / .reason`) alone.

   - `<!-- region:observations:start -->` … `<!-- region:observations:end -->`: an `.observations-grid` with two `.observations-col`s. Left column lists aggregated `deferred.jsonl` entries (by category); right column lists L3/L4 items surfaced but not acted on. **Use `<ul class="observations-list"><li>` — not `.observations-row` divs.** Each `<li>` carries three children: `.label` (category source_label in `$LOCALE`) + `.rec` (one-line recommendation in `$LOCALE`) + `.size`.
     ```html
     <div class="observations-grid">
       <div class="observations-col">
         <h3 data-i18n="section.obs.deferred">You deferred</h3>
         <ul class="observations-list">
           <li>
             <span class="label">{source_label in $LOCALE}</span>
             <span class="rec">{recommendation in $LOCALE}</span>
             <span class="size">{size_human}</span>
           </li>
           <!-- … -->
         </ul>
       </div>
       <div class="observations-col">
         <h3 data-i18n="section.obs.worth">Worth a look</h3>
         <ul class="observations-list"><!-- … --></ul>
       </div>
     </div>
     ```
     If either side is legitimately empty, replace the `<ul>` with `<p class="empty-note" data-i18n="section.obs.empty">Nothing here.</p>` — **not** `.hint` (which is reserved for unfilled template placeholders and is styled as a dashed "missing content" box that would misrepresent an intentional empty column).

   - `<!-- region:runmeta:start -->` … `<!-- region:runmeta:end -->`:
     ```html
     <dl class="runmeta-grid">
       <dt data-i18n="runmeta.label.run_id">Run ID</dt>     <dd><code>{run_id}</code></dd>
       <dt data-i18n="runmeta.label.mode">Mode</dt>         <dd>{mode_label in $LOCALE}</dd>
       <dt data-i18n="runmeta.label.started">Started</dt>   <dd>{started_at}</dd>
       <dt data-i18n="runmeta.label.finished">Finished</dt> <dd>{finished_at}</dd>
       <dt data-i18n="runmeta.label.duration">Duration</dt> <dd>{duration_human}</dd>
       <dt data-i18n="runmeta.label.device">Device</dt>     <dd>{device}</dd>
       <dt data-i18n="runmeta.label.os">macOS</dt>          <dd>{os}</dd>
       <dt data-i18n="runmeta.label.free_before">Free before</dt> <dd>{free_before_human}</dd>
       <dt data-i18n="runmeta.label.free_after">Free after</dt>   <dd>{free_after_human}</dd>
     </dl>

     <div class="risk-meter-label" data-i18n="risk.meter.label">Risk distribution</div>
     <div class="risk-meter">
       <span class="seg-l1" style="flex-basis:{P_L1}%" title="{bytes_L1_human}">
         <span class="glyph">●</span><span class="seg-text">{bytes_L1_human}</span>
       </span>
       <span class="seg-l2" style="flex-basis:{P_L2}%" title="{bytes_L2_human}">
         <span class="glyph">▲</span><span class="seg-text">{bytes_L2_human}</span>
       </span>
       <span class="seg-l3" style="flex-basis:{P_L3}%" title="{bytes_L3_human}">
         <span class="glyph">■</span><span class="seg-text">{bytes_L3_human}</span>
       </span>
       <span class="seg-l4" style="flex-basis:{P_L4}%" title="{bytes_L4_human}">
         <span class="glyph">✕</span><span class="seg-text">{bytes_L4_human}</span>
       </span>
     </div>
     <div class="risk-meter-legend">
       <span class="legend-chip l1"><span class="swatch l1"></span><span data-i18n="risk.legend.l1">L1 safe to clean</span></span>
       <span class="legend-chip l2"><span class="swatch l2"></span><span data-i18n="risk.legend.l2">L2 review</span></span>
       <span class="legend-chip l3"><span class="swatch l3"></span><span data-i18n="risk.legend.l3">L3 caution</span></span>
       <span class="legend-chip l4"><span class="swatch l4"></span><span data-i18n="risk.legend.l4">L4 hold</span></span>
     </div>
     ```
     `<dd>` values (IDs, dates, byte strings) are bare — they read identically across locales. The `mode` value is a short label; write it in `$LOCALE` directly (e.g. EN `Quick Clean`, zh `快速清理`, ja `クイック清掃`) rather than routing through the dict — it's a per-run string, not a static template label.

     **Risk-meter segment text-collapse rule** (agent-side; there is intentionally no CSS attribute selector for this):
     - When `P_L{N} < 5` (percent), omit `<span class="seg-text">` and keep only `<span class="glyph">`. The `title` attribute still carries the full byte count for hover.
     - When `bytes_L{N} == 0`, omit the entire `<span class="seg-l{N}">` from the bar (CSS `gap` handles the spacing of the remaining segments). Keep all four legend chips regardless — the legend is the reader's orientation key, not a per-run inventory.
     - `title` is a bare byte count (e.g. `"59.18 GB"`). **Do not prefix with `"L1: "` / `"L2: "` etc.** — the class name + glyph + legend colour already encode the level, and hard-coded English prefixes read poorly in non-English locales while having no i18n key to hang on.

   **Budget**: keep the combined inserted HTML under ~280 lines.

   **Dry-run marking (mandatory)**: when the run was a `--dry-run`, the report must clearly say so or it misleads the user into thinking files were touched. Requirements, enforced by `validate_report.py --dry-run`:
   - **Banner**: insert a sticky `<div class="dry-banner" data-dryrun="true"><span data-i18n="drybanner">DRY-RUN — no files touched</span></div>` at the very top of the `<main class="report">` element, right inside the open tag. The `data-dryrun="true"` attribute is the structural marker the validator checks for — the banner text goes through the dict like any other static label.
   - **Number prefixes** (every numeric headline: hero total, category bytes, action aggregates, pending, risk-meter bytes, runmeta free-space values): wrap the prefix in a `<span class="dryrun-prefix">` that precedes the number. Its content is whatever "projected / would be / estimated" reads like in `$LOCALE`. Keep a trailing space inside so the text doesn't butt up against the number:
     ```html
     <span class="dryrun-prefix">would be </span>28.6 GB
     ```
     The validator asserts every headline number has a `.dryrun-prefix` sibling; it does not match on vocabulary, so any target-language phrasing works.
   - For real runs, neither the banner nor the prefixes are required.

   **Maintenance note**: if you change a `data-placeholder=...` string or add/remove a region in `assets/report-template.html`, also update `REGIONS` and `_PLACEHOLDER_MARKERS` in `scripts/validate_report.py` so the validator keeps catching unfilled regions.

5. Fill the SVG placeholders. The card is **not** embedded into `report.html` — it's a standalone artifact users can attach to a tweet. Only one file is produced, in `$LOCALE`. `$WORKDIR/share-card.svg` already exists from step 3; Edit it in place, substituting:

   | Placeholder | Value in `$LOCALE` | Examples |
   | --- | --- | --- |
   | `${free_reclaimed}` | bare human-readable number (locale-neutral) | `37.4 GB` |
   | `${mode_label}` | short mode name | EN `Quick Clean` / `Deep Clean`; zh `快速清理` / `深度清理`; ja `クイック清掃` / `ディープ清掃` |
   | `${top_categories}` | up to 3 `source_label`s joined with ` · ` | EN `Xcode DerivedData · node_modules · Docker build cache`; zh 同概念的中文 label |
   | `${label_reclaimed}` | `reclaimed on my Mac` phrase | EN `reclaimed on my Mac`; zh `在我的 Mac 上释放了` |
   | `${label_top}` | `top sources` phrase | EN `top sources`; zh `主要来源` |
   | `${label_by}` | `by` (author credit preposition) | EN `by`; zh `作者` |

   When `$LOCALE` renders labels with wider glyphs (CJK, some Cyrillic), keep each `source_label` in `${top_categories}` to roughly 6 display columns so the three concatenated entries fit the SVG's `t-top` row (28 px at ~1056 px available width). Truncate with an ellipsis if a label runs long.

6. Write the single share-text file `$WORKDIR/share.txt` in `$LOCALE`. **Use `freed_now_bytes` as the headline** (not `reclaimed_bytes`) — share text must reflect bytes that are *actually* off the disk, not bytes still sitting in `~/.Trash`. The region `share` button's `href` URL-encodes this file's contents.

   The content shape is fixed across locales: one line (past-tense credit), one blank line, one line ("biggest wins"), one blank line, hashtags. Translate the prose into `$LOCALE`; leave the brand strings and hashtags untouched.

   **Real-run template (English, canonical form):**
   ```
   I just reclaimed {freed_now} on my Mac with the mac-space-cleanup skill by @heyiamlin.

   Biggest wins: {top3_joined}.

   #macspaceclean #maccleanup #buildinpublic
   ```

   **Dry-run template (English, canonical form)** — the past-tense "reclaimed" misleads when nothing was touched:
   ```
   Previewed with @heyiamlin's mac-space-cleanup skill — it estimates I could reclaim {freed_now} on my Mac.

   Biggest wins in the preview: {top3_joined}.

   #macspaceclean #maccleanup #buildinpublic
   ```

   **Localization guidance:**
   - Translate the natural-language portions of both templates into `$LOCALE`. Example zh renderings: real-run opener "用 @heyiamlin 的 mac-space-cleanup skill 给我的 Mac 清出了 {freed_now} 空间。"; dry-run opener "预演一下：用 @heyiamlin 的 mac-space-cleanup skill，预计能在我的 Mac 上清出 {freed_now} 空间。"; "Biggest wins" → "这次清理的大头"; dry-run "Biggest wins in the preview" → "这次预演的大头".
   - **Hashtags**: always include `#macspaceclean` and `#buildinpublic`. The third hashtag can be swapped for a locale-appropriate synonym of "mac cleanup" (EN uses `#maccleanup`; zh uses `#mac清理`; ja might use `#Mac整理`). Keep the total at three hashtags.
   - **Brand / handles always stay unchanged**: `mac-space-cleanup`, `@heyiamlin`, `macOS`, `skill` (keep the English word across locales — matches how the rest of the brand surface positions it).
   - **Units stay unchanged**: `GB` / `MB` read identically across locales.

   Only substitute: `{freed_now}` (human-readable string from `freed_now_bytes`) and `{top3_joined}` (see shape note below). Same `source_label` taxonomy applies; no paths, usernames, or project names.

   **Shape of `{top3_joined}`**: each entry is `source_label (human_size)`, the three joined by `, `. Concrete example in `$LOCALE=en`: `Xcode DerivedData (6.8 GB), node_modules (3.2 GB), Docker build cache (2.3 GB)`. The per-entry size is the category's `freed_now_bytes` for this run, human-formatted the same way as the headline. For non-English locales, render each `source_label` in `$LOCALE` (the sizes stay numeric with untranslated `GB` / `MB`).

   **Picking the three for resonance**: a tweet that reads `Biggest wins: Xcode DerivedData (6.8 GB), node_modules (3.2 GB), Docker build cache (2.3 GB).` lands for any Mac developer — they've fought those exact folders and the numbers make the scale concrete. One that reads `Biggest wins: Developer caches, Old installers, Generic archives.` reads like a cleanup app's marketing copy, which is the opposite of what we want. When sorting candidates by freed bytes, prefer the specific tool / product name that `source_label` already carries (`Xcode DerivedData`, `node_modules`, `Docker build cache`, `iOS Simulators`, `JetBrains caches`, `Homebrew cache`) over generic category summaries (`Developer caches`, `Package caches`). `references/category-rules.md` already spells source_labels this way for every category; this guidance just says out loud: **copy the specific label, don't paraphrase it up a level of abstraction.** The redaction rules still stand — these names never include personal / project / company info, which is why they're safe to ship.

   **Never ship `orphan` / `Unclassified large item` as a top-3 entry.** That label is an explicit *classifier fallback* surfaced in the report's Observations column for the user's manual review — it is not a real category. Shipping it in share text reads as "the cleanup tool couldn't figure out what it cleaned" and undercuts the whole point of specific source_labels. Two rules:
   - If any of the top 3 candidates (by freed_now_bytes) is `orphan`, **skip it and pick the next-ranked concrete source_label**. Do this even if the skipped orphan bucket is numerically the largest.
   - If orphan legitimately dominates the run (e.g. a clean workstation with no developer footprint), it is a signal that the classifier mis-bucketed items that *should* have matched concrete category rules. Before shipping a `top3_joined` that's padded with orphan, re-examine `confirmed.json` — many project-artifact or dev-cache items get mis-routed to orphan when the agent forgets to consult `references/category-rules.md`'s §10 / §1 taxonomy.

7. **Spawn a redaction reviewer** sub-agent to independently scan `$WORKDIR/report.html` for leaks the deterministic validator cannot catch (project names, company names, made-up names that look like personal data). Use the `Agent` tool with the prompt template in `references/reviewer-prompts.md` (section "Redaction reviewer"), passing the report HTML verbatim. The report is single-locale per run; the reviewer inspects one language's content pass-through — if Stage 6 was driven by `$LOCALE=ja`, reviewer sees Japanese prose and the translated dict.
   - Reviewer returns `{"violations": [...]}`.
   - Empty list → proceed.
   - Non-empty → edit `$WORKDIR/report.html` to remove / abstract each flagged snippet (and, if the leak also appears inside the translated dict, fix it in the `<script id="i18n-dict">` container too), then re-spawn the reviewer with the updated HTML. Cap retries at **2**. After the second failure, stop and tell the user which violations remained — do **not** show the report.

8. **Run the deterministic validator** as a second line of defence. The reviewer is fuzzy (catches semantic leaks); the validator is exact (catches structural problems and a fixed dictionary of forbidden literal substrings). When the run was a `--dry-run`, also pass `--dry-run` so the banner and number prefixes from step 4 are asserted:

   ```bash
   # real run
   python3 scripts/validate_report.py --report "$WORKDIR/report.html"

   # dry-run
   python3 scripts/validate_report.py --report "$WORKDIR/report.html" --dry-run
   ```

   Exit 0 → all good. Exit 1 → stdout JSON's `violations` lists each problem (`missing_region`, `empty_region`, `placeholder_left`, `leaked_fragment`, `dry_run_unmarked`). Fix every violation by editing `$WORKDIR/report.html` and re-run the validator until it returns 0. Do not show the user the report while violations remain.

9. Summarise to the user in one short paragraph that **always reports both numbers**:
   - `freed_now_bytes` — already off the disk (or "would-be freed" on a dry-run).
   - `pending_in_trash_bytes` — waiting in `~/.Trash`; mention that emptying trash converts it to free space (the report's "One last step" section gives the one-line command).
   - `archived_count` if any (archive_source goes into the workdir, point user at it).
   - `deferred_count`.

   Print two locations explicitly, each on its own line:
   - The workdir path itself (the literal expanded value of `$WORKDIR`, e.g. `/Users/alice/.cache/mac-space-cleanup/run-A1B2C3`) — so the user can `cd` there or `open` it in Finder to inspect `actions.jsonl`, `cleanup-result.json`, the share cards, and any other artefacts.
   - The report URL as `file://` + the expanded `$WORKDIR` + `/report.html` — so the user can Cmd+click it in the terminal or click it in a markdown-rendering host to reopen the report.

   Both lines are required. Do not reduce this to "the report is in the workdir".

   Honest framing: never report `reclaimed_bytes` to the user as "freed" — that field is back-compat only.

### Stage 7 · Open the report

Stage 6 ends on the summary paragraph. Before handing the browser window off to the user, run one last gate and then open the report.

1. **Self-check on `share.txt` (no automation backstop).** `validate_report.py` scans `report.html` only; the share-text file is on an unchecked path. Re-read `$WORKDIR/share.txt` and confirm:
   - Verb tense matches the run: real-run → past (`reclaimed` / `清出了` / locale equivalent); dry-run → future-tense template from Stage 6 step 6 (`estimates I could reclaim` / `预计能在我的 Mac 上清出` / locale equivalent).
   - `{top3_joined}` contains only concrete source_labels from `references/category-rules.md` (rendered in `$LOCALE`) — no `orphan` / `Unclassified large item`.
   - Three hashtags present: `#macspaceclean` and `#buildinpublic` mandatory; the third is a locale-appropriate "mac cleanup" synonym (EN `#maccleanup`; zh `#mac清理`).
   - No path / username / project name slipped through (the redaction reviewer sub-agent in Stage 6 step 7 only saw `report.html`).

   If any check fails, edit `$WORKDIR/share.txt` and re-check before proceeding.

2. **Open the report:**

   ```bash
   open "$WORKDIR/report.html"
   ```

This is intentionally a separate stage so (a) the summary paragraph (workdir path, `file://` URL, freed / pending numbers) lands in the terminal *before* the browser window steals focus, and (b) the share-text self-check has its own slot as a gate rather than being buried mid-summary. Do not fold `open` back into Stage 6 or skip it — if any Stage 6 gate (reviewer retry cap, validator violations) aborted the run, you are already blocked upstream and never reach this stage.

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
  - Semantic paths (synthetic, bypass the `_BLOCKED_PATTERNS` + idempotency check): `brew:cleanup-s`, `docker:build-cache | docker:dangling-images | docker:stopped-containers`, `snapshot:<tmutil-name>`, `xcrun:simctl-unavailable`, `ollama:<name>:<tag>` (v0.9+; reference-counting blob delete per §3 Ollama block in `references/category-rules.md`).
  - `action_status`: `success | archive_only_success | failed`
- **Degradation**: see §14-style matrix in `references/safety-policy.md`.
