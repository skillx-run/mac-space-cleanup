# Changelog

All notable changes to mac-space-cleanup. Newest first.

## Unreleased

## v0.9.1 — 2026-04-19

### Added
- **VSCode-family non-sandboxed editor cache scanning.** Cleanup-scope.md gets a new Tier C subset for Code / Cursor / Windsurf / Zed whose caches live under `~/Library/Application Support/<editor>/` and so were missed by the generic Tier C sweep (which only walks `~/Library/Caches/*` and `~/Library/Containers/*/Data/Library/Caches/*`). Each editor surfaces only via a **positive whitelist** of specific cache subdirs (`Cache`, `CachedData`, `CachedExtensionVSIXs`, `Crashpad`, `GPUCache`, `Code Cache`, `logs` for VSCode-family; `db/0/blob_store` and `logs` for Zed) — never glob, never descend into `User` / `Backups` / `History` / `db`. Default: L2 trash (Tier C semantics — recovery window for an active editing session). Typical reclaim 1–5 GB for an active developer.
- **`"Editor cache"` source_label** in category-rules.md §4 source_label table so these caches surface under a UI-safe label rather than the generic "System caches" bucket.

### Changed
- **`_BLOCKED_PATTERNS` runtime backstop** in `safe_delete.py` gains a regex matching `~/Library/Application Support/{Code,Cursor,Windsurf}/{User,Backups,History}`. Even if confirmed.json mistakenly targets `User/workspaceStorage` (which holds unsaved edits and git-stash equivalents), `Backups` (unsaved files), or `History` (local edit history), dispatch refuses — never reaching `rm` or `trash`. Third defence layer paired with the Tier C positive whitelist and the User-critical blacklist. Zed is intentionally not in the runtime backstop because a regex blocking `dev.zed.Zed/db` would also block the legitimate `db/0/blob_store` cleanup leaf; doc-level blacklist + agent positive whitelist cover Zed.
- **Cleanup-scope.md cross-reference list** for runtime backstop sync now mentions the VSCode-family patterns.
- **User-critical blacklist** explicitly lists VSCode-family `User` / `Backups` / `History` and Zed's `db/` (with `db/0/blob_store` carve-out) so the agent reads the same protections at the doc layer.

### Tests
- 91 → **93** (`test_safe_delete.py` adds 2: parameterised positive/negative cases over 3 brands × 3 guarded subdirs vs the 5 cache subdirs that must remain cleanable; end-to-end dispatch test verifying disk state is preserved when blocklist fires).

### Known limitation (CI)
- Same as v0.9.0: CI macos-latest does not have Code / Cursor / Windsurf / Zed installed, so the new probes silently skip in CI. CI test coverage relies on the `_BLOCKED_PATTERNS` unit tests; real-path coverage is left to PR submitter dry-runs and user feedback.

## v0.9.0 — 2026-04-19

### Added
- **`brew:cleanup-s` semantic dispatch** in `safe_delete.py`. The skill now surfaces a `brew:cleanup-s` item alongside the existing `$(brew --cache)` directory and on confirmation runs `brew cleanup -s` to drop old Cellar versions and stale downloads (typically 5–30 GB on a long-lived dev Mac). Pinned formulae are preserved automatically by Homebrew. Reclaim is parsed from brew's "freed approximately X" tail line and credited to `freed_now_bytes` rather than relying on a pre-estimate.
- **Three `docker:*` semantic dispatches** in `safe_delete.py`: `docker:build-cache` → `docker builder prune -f`, `docker:dangling-images` → `docker image prune -f`, `docker:stopped-containers` → `docker container prune -f`. Each parses "Total reclaimed space: X" from prune output for accurate freed-bytes accounting. **`docker:unused-volumes` is intentionally NOT in the dispatch table** because volumes contain user data; an unknown suffix fails fast without ever shelling out.
- **7 modern toolchain probes** in `cleanup-scope.md` Tier A/E + matching `category-rules.md` rules: Bun (`~/.bun/install/cache`), Deno (`~/Library/Caches/deno`), Yarn Berry PnP global cache (`~/.yarn/berry/cache`, only when `enableGlobalCache: true`), Swift Package Manager (`~/Library/Caches/org.swift.swiftpm`), Carthage (`~/Library/Caches/org.carthage.CarthageKit`), Xcode Playground (`~/Library/Developer/XCPGDevices`, `~/Library/Developer/XCPGPlaygrounds`), and `~/Library/DiagnosticReports`. Each surfaces under a specific UI-safe `source_label` (`"Bun cache"`, `"Swift PM cache"`, `"Diagnostic reports"`, …) instead of falling into the generic "System caches" bucket.
- `_parse_human_bytes()` helper in `safe_delete.py` for parsing B/KB/MB/GB/TB sizes out of CLI output (shared by brew + docker handlers).

### Changed
- **`large_media` generic du fallback threshold lowered from 10 GB to 2 GB.** The previous threshold meant the catch-all probe only ever fired on truly enormous trees; mid-sized strangers (4–8 GB folders) silently slipped through. To keep Stage 3 budget in check, the probe now uses `du -d 2 ~/` (depth-limited so deeply nested project trees don't push the per-path 30s budget) and the surfaced list is capped at the **top 30 by size** so the deferred section stays scannable. Risk envelope unchanged: still L3 defer + deep-mode-only, never auto-cleaned.
- **Xcode `iOS / watchOS / tvOS DeviceSupport` default action: `delete` → `trash`.** Each per-OS dir is 5–10 GB and rebuilding requires plugging a real device of that OS into Xcode again — a 10+ minute symbol re-pull. Defaulting to L1 delete made them unrecoverable. Match the risk class of pkg_cache nvm/pyenv/rustup per-version entries: L2 trash, same-session recovery via Finder. DerivedData stays L1 delete (fully regenerable from one rebuild).
- **SKILL.md Stage 2 probe lines** extended with `bun deno` (CLI probe) and `~/Library/Caches/{org.swift.swiftpm,org.carthage.CarthageKit}` (directory probe).
- **SKILL.md Stage 3 "semantic / tool entries"** rewritten to spell out that `docker:*` and `brew:cleanup-s` are dispatcher-handled paths whose `size_bytes` may be 0 at scan time — the dispatcher reports the real freed bytes back via `actions.jsonl`. Pre-estimate hints come from `brew cleanup -ns` and `docker system df`.

### Tests
- 86 → **91** (`test_safe_delete.py` adds 5: brew parse-on-success, brew failure-propagates, brew dry-run keeps input, docker parameterised dispatch over three subcommands, docker unknown-suffix fails safe).

### Known limitation (CI)
- The CI macos-latest runner does not have `bun`, `deno`, `docker`, Cursor, etc. installed, so the 7 new Tier E probes silently skip in CI. CI test coverage is limited to the `safe_delete.py` dispatch unit tests (subprocess mocked); real-path coverage relies on PR submitter dry-runs and user feedback.

## v0.8.0 — 2026-04-19

### Changed
- **Workflow bumps from six to seven stages.** The `open "$WORKDIR/report.html"` call and the `share.txt` self-check are pulled out of Stage 6 into a new standalone **Stage 7 · Open the report**. Stage 6 now ends on a pure summary paragraph (old step 10 → new step 9, with the embedded self-check block removed), and Stage 7 runs: (1) `share.txt` self-check gate, (2) `open`. Intent: let the summary (workdir path, `file://` URL, freed / pending numbers) land in the terminal *before* the browser window takes focus; give the share-text self-check its own slot as a gate instead of burying it mid-summary; make "don't skip the open" a harder-to-miss instruction with its own stage header. All 7 translated READMEs mirror the stage-count bump.

### Added
- Translated READMEs in 7 locales (`zh-CN`, `zh-TW`, `ja`, `es`, `fr`, `ar`, `de`). Flat filename-suffix layout at repo root; unified top-of-file language navigation bar with fixed order (EN → zh-CN → zh-TW → ja → es → fr → ar → de). English `README.md` remains the GitHub default.

### Docs
- `CLAUDE.md` gains a "Translated READMEs" section mandating synchronized translation on every substantive `README.md` change, with narrow exemptions for typo / formatting / URL / version-housekeeping edits. "Translation pending" state is not allowed to cross PR boundaries. `SKILL.md` and `references/*.md` remain agent-only and are not translated.
- **"skill" brought forward as a first-class brand token across every user-visible surface.** README H1 now reads `mac-space-cleanup · macOS cleanup skill` — the same English subtitle in all 8 locales, treating "skill" as a universal ecosystem tag like `npm` or `github`. Tagline leads with `A **skill** that cleans up your Mac's disk space — cautious, honest, multi-stage.` (and locale-appropriate three-word triples), `agent-driven` dropped from the headline. Report template: `<title>` → `mac-space-cleanup skill report`, header brand → `mac-space-cleanup · skill`, footer → `Generated by the mac-space-cleanup skill` (baseline + matching `strings.json` values). Share-card SVG brand text → `mac-space-cleanup · skill`. `SKILL.md` share-text dry-run canonical and Chinese examples pick up the word, and the "brand / handles unchanged" list now pins `skill` so it stays English across locales. Motivation: "skill" is the recognised ecosystem term — putting it beside every `mac-space-cleanup` mention lets a cold visitor orient themselves in one glance.

## v0.7.0 — 2026-04-18

### Changed (BREAKING)
- **Report is single-locale per run, in whatever language the conversation is.** The bilingual EN/ZH DOM, the header-corner language toggle, the `data-locale-show` sibling-span pair pattern, the `data-href-en` / `data-href-zh` dual share button, the per-locale `share-card.{en,zh}.svg` / `share.{en,zh}.txt` artefacts, and the pattern-A/B/C triage introduced in v0.6 are all gone. Stage 1's `locale.txt` now holds a BCP-47 primary subtag (`en` / `zh` / `ja` / `es` / `ar` / …, default `en` on ambiguity) and Stage 6 writes every hero caption, action reason, observation recommendation, source_label rendering, and dry-run prose once, in that locale. RTL scripts (`ar` / `he` / `fa` / `ur`) get an explicit `<html dir="rtl">`.
- **`assets/i18n/strings.json` collapses from `{"en": {...}, "zh": {...}}` to a single flat `{key: value}` EN dict**, now the canonical source for every `data-i18n` label. Stage 6 step 3.5 either leaves the `<script id="i18n-dict">` container as `{}` (English runs; baseline renders directly) or batch-translates all ~40 values into `$LOCALE` in one pass and writes the result as a single JSON object.
- **Template runtime script shrinks from ~50 lines (toggle + localStorage + href-swap) to ~10 lines (one hydration pass).** `hero-caption` loses its `min-height: 2.8em` reservation (it existed to prevent layout shift during toggling); `.lang-toggle` and `[data-locale-show]` CSS rules are deleted. Added: minimal `.dryrun-prefix` rule for the structural dry-run marker.
- **`CLAUDE.md` invariant #7** rewritten: static labels still go through `data-i18n`, but the dict is a single flat EN object, translation happens per-run, and the four validator rules are spelled out structurally.

### Added
- **`.dry-banner[data-dryrun="true"]` attribute** and **`<span class="dryrun-prefix">…</span>` sibling** on every dry-run headline number: structural, language-agnostic markers that replace the v0.6 vocabulary match (`would be` / `预计` / `(simulated)` / `模拟`). A dry-run report can now be written entirely in Japanese, Arabic, Spanish, etc., and still pass validation.

### Removed
- `references/category-rules.md` "Source label bilingual naming" appendix (the 41-entry EN→ZH table). With any-language support, the table would need to multiply by every locale the skill is used in, which is neither scalable nor necessary: Stage 6 translates each source_label on the fly from its English canonical form.
- `validate_report.py`: `_check_locale_pair_balance` (data-locale-show en/zh count equality), the `_LOCALE_SHOW_EN_RE` / `_LOCALE_SHOW_ZH_RE` regex pair, and the EN/ZH key-set parity check inside `_check_i18n_dict`. Replaced with: `dict keys ⊆ template data-i18n keys` and `template data-i18n keys ⊆ canonical strings.json keys`.
- Dry-run vocabulary table (`_DRY_RUN_MARKERS` accepted `would be` / `would-be` / `(simulated)` / `预计` / `模拟`) — validation is now by class / attribute presence only.

### Migration notes
- Pre-v0.7 reports already opened on the user's disk (`$WORKDIR/report.html`) are self-contained static HTML and continue to work with the old toggle UI. Only new runs produce the new single-locale shape.
- Contributors: if you added a new static label in a v0.6 branch, drop the `zh` subtree from your `assets/i18n/strings.json` diff — the top-level is now flat. Any new `data-locale-show` pairs must be rewritten as single-locale spans.

### Tests
- 85 → **86** (`test_validate_report.py`): removed 7 bilingual tests (Chinese dry-run vocab, EN/ZH dict subtree parity, locale-pair balance), kept the two shape-level dict tests, added 11 covering the new rules (empty-dict pass, populated-dict with canonical keys, non-string value, dict-key-not-in-template, template-key-not-in-strings, banner-requires-data-dryrun, prefix-required, any-language banner prose, attribute-order-insensitive banner regex).

## v0.6.0 — 2026-04-18

### Added
- **Bilingual report with runtime EN/ZH toggle.** `report.html` now ships both English and Chinese copy in the same DOM and flips between them via a header-corner button. Static labels (section titles, column headers, legends, button text, dry-run banner, nextstep warnings) are driven by `data-i18n` keys backed by the inline `<script id="i18n-dict">`; agent-authored natural language (hero caption, action reasons, observations recommendations, per-category `source_label`) is emitted as sibling `data-locale-show="en"` / `data-locale-show="zh"` spans and toggled by CSS. `localStorage` only records an explicit user toggle, so a fresh report always opens in the locale the agent picked (based on the user's triggering message — CJK → `zh`, otherwise `en`, persisted to `$WORKDIR/locale.txt` in Stage 1).
- **`assets/i18n/strings.json`** as the single source of truth for UI labels (41 keys per locale). Stage 6 step 3.5 copies it into the workdir and inlines it into the report.
- **SVG share card is now emitted per locale** (`share-card.en.svg` + `share-card.zh.svg`) since the SVG has no JS toggle. Template gains three new label placeholders (`${label_reclaimed}` / `${label_top}` / `${label_by}`) filled from a fixed translation table.
- **`references/category-rules.md` "Source label bilingual naming" appendix** mapping every `source_label` to its Chinese rendering, so Stage 6 Pattern C stays consistent across runs.

### Changed
- **`validate_report.py` gains three checks**: `i18n_dict_malformed` (script block present, valid JSON, symmetric en/zh subtrees), `locale_unpaired` (data-locale-show en/zh counts equal), and extended `_DRY_RUN_MARKERS` to accept `预计` / `模拟` alongside the English triplet. Redaction scanning remains locale-agnostic — a leak in either locale is caught by the same literal rules.
- **Redaction reviewer sub-agent prompt** (`references/reviewer-prompts.md`) now instructs reviewers to scan both locale variants and adds a `locale` field to the violation schema; leaks must be scrubbed from both sibling spans in the same fix pass.
- **Share button href** flips to `share.zh.txt` when `LOCALE=zh` (the file already existed as a workdir artifact; it now actually drives the button). `share.en.txt` is still generated for EN users.
- **`CLAUDE.md` invariant #7**: new static labels must land in both i18n subtrees; new agent-authored nodes must ship both `data-locale-show` siblings; new `source_label` entries need a Chinese rendering in the same commit.

### Tests
- 76 → **85** (`test_validate_report.py` adds 9 cases: Chinese dry-run marker, missing / invalid / asymmetric i18n dict variants, balanced and unbalanced `data-locale-show` span counts).

## v0.5.0 — 2026-04-18

### Changed (BREAKING)
- **Report HTML redesigned** as a single long page with eight regions (`hero / share / impact / nextstep / distribution / actions / observations / runmeta`). Old region names (`summary / deferred`) are gone; `summary` split into `hero` + `impact`, `deferred` became the two-column `observations`, and `runmeta` is new. The page uses a bright celebration palette (light ground, mint-teal accent, amber CTA, 80px hero headline) with shape glyphs (● ▲ ■ ✕) carrying the risk encoding alongside colour so hue is not load-bearing.
- **Share block collapsed into a single inline X button.** No more SVG preview, language tabs, or text panes on the page — the button's `href` is `https://x.com/intent/tweet?text=<URL-encoded English share text>` and clicking it takes the user directly to a composed tweet. `share-card.svg`, `share.en.txt`, `share.zh.txt` are still generated as workdir artifacts for users who want to attach an image or post in Chinese.
- **`cleanup-result.json` `host_info` gains `device`** (from `system_profiler SPHardwareDataType`), driving the hero device chip. Stage 6 step 1 falls back to `"Mac"` if the command fails, so older runs without the field render a generic chip.

### Added
- New component classes in `assets/report.css`: `.water-bar` (disk-level before/after), `.stack-bar` (per-category freed breakdown), `.risk-chip` / `.risk-meter` (L1-L4 with shape glyphs), `.cta-card` (trash still-pending), `.dist-card--detailed`, `.actions-row` (four-column grid with a dedicated reason column), `.observations-grid` (two-column defer vs. worth-a-look), `.runmeta-grid` + `.risk-meter` full chart.
- Share card SVG (`assets/share-card-template.svg`) repainted to match the report palette (light ground, `#065f46` headline for contrast, mint accent on mode label / handle), since users still screenshot it to attach to posts.

### Tests
- 74 → **76** (`test_validate_report.py` adds: all-good nextstep scenario does not trigger `placeholder_left`; surviving `data-placeholder="impact"` is flagged under the new region set). Fixtures (`tests/fixtures/sample-fill.html.fragment`) rewritten to exercise every new region and component.

## v0.4.0 — 2026-04-18

### Added
- **`scripts/scan_projects.py`**: identifies project roots (via `.git` directory) under user-specified roots and enumerates conventional artifact subdirectories. Outputs structured JSON with `markers_found` per project so the agent can disambiguate ambiguous subtypes (e.g. `vendor` only when `go.mod` is present, `env` only when a Python marker is present).
  - **Submodule dedup**: nested `.git` inside a recognised project root is skipped; submodules don't show up as separate projects.
  - **System directory prune**: scans skip `~/Library`, `~/.cache`, `~/.npm`, `~/.cargo`, `~/.cocoapods`, `~/.gradle`, `~/.m2`, `~/.gem`, `~/.bundle`, `~/.local`, `~/.rustup`, `~/.pnpm-store`, `~/.Trash` so cached repo checkouts don't masquerade as user projects.
- **New category `project_artifacts`** (rule §10) with two subtypes:
  - **Deletable build outputs** (L1 delete): `node_modules`, `target`, `build`, `dist`, `out`, `.next`, `.nuxt`, `.svelte-kit`, `.turbo`, `.parcel-cache`, `__pycache__`, `.pytest_cache`, `.tox`, `Pods`, `vendor` (Go-only).
  - **Virtual environments** (L2 trash): `.venv`, `venv`, `env` (Python).
  - Quick mode skips this category entirely to avoid clearing freshly installed deps.
- **Confirm-stage exception** in `safety-policy.md`: agent ↔ user dialog at Stage 5 may use project basenames (e.g. `foo-app`) so users can pick between several Node/Python projects when they choose `yes-but-let-me-pick`. Persisted artefacts (`report.html`, share text, `cleanup-result.json`'s `source_label`) remain strict — `validate_report.py` and the redaction reviewer enforce.
- **SKILL.md Stage 3.5** wires project scanning into the deep-mode workflow with a 10–30s nudge before `find` walks `~`.

### Changed
- `cleanup-scope.md` lifts the v1 blanket exclusion of nested project artifacts; carves out an explicit allowlist tied to project-root recognition.
- Stage 5 deep-mode confirmation now groups project artifacts by subtype rather than per-path (e.g. "12 Node projects, 9.2 GB total"); supports `yes-but-let-me-pick` for per-project selection by basename.
- README "What it touches" lists project artifacts; Limitations no longer mentions "no project-aware cleanup", replaced with v0.4 actually-shipping constraints (`.git`-only root identification, no `.gitignore` parsing).

### Tests
- 40 → **55** (new `tests/test_scan_projects.py` with 14 tests + 1 sibling-dedup boundary added in the v0.4 review pass, covering submodule dedup, system-cache prune, markers_found completeness, env/vendor disambiguation surfaces, find timeout isolation, errors schema).

### Renamed (also in v0.4.0)

The skill identifier was changed from `mac-space-clean` to `mac-space-cleanup` for grammatical correctness — "cleanup" is a standard compound noun (cf. `brew cleanup`, Windows Disk Cleanup), "clean" was an awkward dangling adjective in the three-word compound. Workdir path moves from `~/.cache/mac-space-clean/` to `~/.cache/mac-space-cleanup/`; brand strings in `share.{en,zh}.txt`, `share-card.svg`, and `report.html` updated accordingly. v0.4.0 is the first published release, so the legacy in-development name is recorded here for traceability and is no longer in use anywhere in the codebase.

## v0.3.0 — 2026-04-18

### Added
- **Three-tier mode detection** in Stage 1: explicit signal lists for `quick` and `deep`; ambiguous wording (e.g. "clean my Mac" / "Mac 空间满了") triggers `AskUserQuestion` instead of silently defaulting to `deep`.
- **Redaction reviewer sub-agent** in Stage 6 (step 7). Independent fresh-context Agent call scans `report.html` for semantic leaks (project / company / personal-looking names) the deterministic validator cannot know about. Bounded retries (max 2) before escalating to the user. Prompt template lives in `references/reviewer-prompts.md`.
- **`scripts/validate_report.py`**: deterministic post-render check covering region completeness, leftover template placeholders, and a fixed forbidden-fragment dictionary plus runtime-derived `$HOME` / username. Stage 6 step 8 runs it; non-zero exit blocks `open`.
- **Hard blocklist in `safe_delete.py`** (`_BLOCKED_PATTERNS`): regex backstop that refuses any fs-touching action on `.git` / `.ssh` / `.gnupg` / `Library/Keychains` / `Library/Mail` / `Library/Messages` / iCloud Drive mirror / Photos Library / Apple Music / `.env*` / SSH key files — independent of `confirmed.json` content. Last line of defence against agent misjudgement.
- **`trash` CLI probe** in Stage 2; one-shot heads-up before Stage 3 if absent (recommends `brew install trash`, explains the `mv` fallback's `-<ts>` suffix quirk).
- **`scripts/dry-e2e.sh`** + `tests/fixtures/`: end-to-end smoke for the non-LLM pipeline (`collect_sizes` → `safe_delete --dry-run` → simulated agent fill → `validate_report.py`).

### Changed
- `safety-policy.md` invariants list grows item 6 (blocklist backstop is non-negotiable).
- SKILL.md Stage 6 grew from 8 to 10 numbered steps (added reviewer + validator).
- CI now runs `dry-e2e.sh` after `unittest discover` and `smoke.sh`.

### Tests
- 36 → **44** unit tests (`test_safe_delete` + `test_collect_sizes` + new `test_validate_report` 8 tests). Plus the dry-e2e harness.

## v0.2.0 — 2026-04-17

### Added
- **Reclaim metric split** in `safe_delete.py` stdout summary: `freed_now_bytes` (delete + migrate), `pending_in_trash_bytes` (trash + archive originals), `archived_source_bytes`, `archived_count`. `reclaimed_bytes` retained as deprecated back-compat alias.
- **`xcrun simctl` specialised handler** for `category=sim_runtime`. Apple's own tool refuses to delete a booted simulator, giving the safety guarantee a plain `rm -rf` would not.
- **Report "One last step" region** with the one-line `osascript` command to empty `~/.Trash`, the Finder dialog warning, and the macOS 30-day auto-empty hint. Two fill modes: pending > 0 vs pending == 0.

### Changed
- `category-rules.md` §2 (`sim_runtime`): L2 trash → **L1 delete via simctl**.
- `category-rules.md` §6 (`downloads`) split into **6a clear-cut installers** (.dmg/.pkg/.xip/.iso → L1 delete) and **6b generic archives** (.zip/.tgz/etc → L2 trash). Cuts the typical deep-clean trash volume by an order of magnitude.
- Share text headline switched from `reclaimed_bytes` to `freed_now_bytes` so social posts reflect bytes actually off the disk.
- `safety-policy.md` invariant #4 rewritten to document the four-bucket split.

### Tests
- 14 → 24 (added simctl 3 cases + migrate happy path + 6 dry-run/split-metric assertions).

## v0.1.0 — 2026-04-16

### Added
- Initial SKILL.md (six-stage agent workflow, EN+ZH trigger semantics).
- `scripts/safe_delete.py` (six-action dispatcher: delete/trash/archive/migrate/defer/skip; trash CLI + `shutil.move` fallback; tmutil specialisation for `system_snapshots`; idempotent on missing paths; per-item error isolation; `--dry-run`).
- `scripts/collect_sizes.py` (parallel `du -sk` with per-path 30s timeout and structured JSON output).
- `references/cleanup-scope.md` (path whitelist tiers A–E + blacklist).
- `references/safety-policy.md` (L1–L4 grading, default actions, redaction rules, degradation matrix).
- `references/category-rules.md` (9 categories with match patterns + risk_level + action defaults).
- `assets/report-template.html` + `report.css` + `share-card-template.svg`.
- `tests/test_safe_delete.py` (14 tests) + `tests/test_collect_sizes.py` (6 tests).
- `scripts/smoke.sh` end-to-end checker.
- `.github/workflows/ci.yml` (macos-latest unittest + smoke).
- Repo-level `CLAUDE.md`.
