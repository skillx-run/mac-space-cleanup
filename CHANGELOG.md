# Changelog

All notable changes to mac-space-cleanup. Newest first.

## Unreleased

### Changed — v0.14 report visualization contract alignment

- **`assets/report.css`**: thicken `.risk-meter` from 8 px to 32 px; fix `.risk-meter span` → `> span` so inner `.glyph` / `.seg-text` don't inherit full height; refactor `.dist-card--detailed` into a two-row `.dist-header` + `.dist-inline-bar` layout (with media query retarget); add `.legend-chip` / `.stack-legend .swatch.seg-1..5` / `.cta-card .pending-size` / `.group-meta .count` / tabular-nums on metric values.
- **`SKILL.md` Stage 6 Step 4**: prose replaced with pinned HTML snippets for impact / distribution / actions / observations / runmeta regions; opens with a "class vocabulary is closed" clause. Substantive rule changes: stack-bar uses `.seg-1..5` palette (no inline colours); distribution metric labels are per-run `$LOCALE` prose (not i18n-dict-routed); actions uses `.act.*` (not `.badge.*`) and forbids column-header rows; observations is `<ul class="observations-list"><li>`; risk-meter segments carry glyph + `.seg-text`, with a `<5%` agent-side collapse rule and a bare-byte `title` (no `L1:` prefix).
- **`scripts/validate_report.py`**: new `_check_class_allowlist` step. Parses `assets/report.css` (comments + quoted literals stripped) to derive allowed class names, diffs against every `class="..."` token in the rendered HTML, emits one `undefined_class` violation per offender. CSS read failure yields a single `css_load_failed`. `_CLASS_WHITELIST` carries the six `<section>` region anchors.
- **`assets/i18n/strings.json`**: remove `actions.col.{cat,size,act,reason}` — orphaned by the no-column-header rule.
- **`tests/test_validate_report.py`**: new `TestClassAllowlist` class with 12 cases (HTML-side recognition + CSS parser boundaries). Suite grows from 123 to 135 tests.

Per `CLAUDE.md` §"Translated READMEs" Exemptions, the 7-language README family is not synced in this release.

## v0.11.0 — 2026-04-20

This release bundles two internal milestone families that accumulated on `main` since v0.10.0. CLAUDE.md's "v0.8 AI/ML coverage and orphan investigation" and "v0.9 coverage expansion" sections map to this single CHANGELOG entry — the internal narrative labels lag the released numbering by historical drift, kept for readability in the contributor doc.

### Added — AI/ML foundation (CLAUDE.md "v0.8")

- **Four AI/ML Tier E rows** in `references/cleanup-scope.md` + `category-rules.md` §3: HuggingFace (`hub/` + `datasets/`, two aggregate items), PyTorch hub (one aggregate), Ollama (one aggregate), LM Studio (one aggregate from whichever of `~/.cache/lm-studio` / `~/.lmstudio` exists). All four default to **L3 `defer`** except PyTorch hub (**L2 `trash`**, typical weights < 1 GB). Ollama deliberately skips the CLI probe so a leftover `~/.ollama` after the user uninstalled the `ollama` CLI still surfaces.
- **Stage 3.5 orphan-investigation step** at the tail of the `du -d 2 ~` probe. Before each unclassified large directory is finalised with the generic `"Unclassified large directory"` label, the agent runs a read-only investigation (`ls` / `file` / `head` + marker-file existence checks, capped at 6 commands per candidate) and may refine `category` (∈ §1-§9; never §10 `project_artifacts`) and `source_label`. `risk_level=L3` and `action=defer` stay locked regardless — per `references/safety-policy.md` §"Orphan investigation" and new Operating invariant #7.

### Added — Coverage expansion M1 (CLAUDE.md "v0.9" first slice)

- **Five new Tier E `pkg_cache` rows** (dir-probe in Stage 2):
  - **Conda / Mamba / Miniforge** envs across seven macOS install layouts (`~/miniconda3/envs`, `~/anaconda3/envs`, `~/opt/miniconda3/envs`, `~/opt/anaconda3/envs`, `~/miniforge3/envs`, `~/mambaforge/envs`, `~/.mamba/envs`) — per non-`base` env, **L2 `trash`**, `mode_hit_tags=["deep"]`. Scope stops at `~/...` to avoid system `/opt/miniconda3/envs`.
  - **Playwright** (`~/Library/Caches/ms-playwright` + XDG fallback + `ms-playwright-driver`) — one aggregate, **L1 `delete`**.
  - **Puppeteer** (`~/.cache/puppeteer`) — **L1 `delete`**.
  - **OpenAI Whisper** (`~/.cache/whisper` + `~/.cache/openai-whisper`) — one aggregate, **L2 `trash`**. Faster-Whisper (SYSTRAN) explicitly redirected to the HuggingFace row.
  - **Weights & Biases global cache** (`~/.wandb` + XDG `~/.cache/wandb`) — one aggregate, **L2 `trash`**. Per-project `./wandb/` dirs not swept.
- **Creative-app source_label refinement** in `category-rules.md` §4: Adobe Media Cache / Peak Files, Final Cut Pro, Logic Pro paths get specific labels instead of the generic `"System caches"`. Risk grading unchanged (L2 `trash` via the Tier C-adjacent override); only the UI label becomes specific so the report names the actual workflow. GarageBand's instrument libraries explicitly excluded — user-initiated content, not cache.

### Added — `scan_projects.py` extensions M2 (CLAUDE.md "v0.9" middle slice)

- **New `kind="nested_cache"` artifact** for "keep parent, drop cache-child" pairs. Currently just `.dvc/cache` — the sibling `.dvc/config` is a new nested-path entry in `PROJECT_MARKERS`; `_detect_markers`'s existing `os.path.join` + `isfile` logic handles flat and nested paths uniformly. Default **L2 `trash`** (rebuild requires network pull from the DVC remote). Marker-gated at Stage 4 per `category-rules.md` §10d — without `.dvc/config`, fall through to `orphan` L4.
- **`version_pins` field per project** — `_parse_version_pin_file` reads `.python-version` / `.nvmrc` tolerating multi-version pyenv chains (`3.11.4 3.10.8`), `#` comment lines, CRLF line endings, empty files, and unreadable files. `SKILL.md` Stage 3 now takes the union across all scanned projects and appends to the pyenv / nvm exclusion sets — replacing the documented-but-unimplemented v0.4 "`cd` into each project and run `pyenv local`" choreography.
- **iOS DeviceSupport active-OS downgrade** (no script change; Stage 2 + category-rules only). Stage 2 collects active iOS versions from `xcrun devicectl list devices --json-output -` (Xcode 15+; physical paired devices) and `xcrun simctl list devices available --json` (all Xcode versions; simulator runtimes). Stage 4 normalizes both sides to `major.minor` and on equal-string match downgrades the `iOS DeviceSupport/<OS>` entry from L2 `trash` to L3 `defer`. Empty union is a first-class "no hint" state. `watchOS` / `tvOS` stay L2 (no equivalent active-OS source in v0.11).

### Added — Ollama per-model dispatcher M3 (CLAUDE.md "v0.9" last slice)

- **`ollama:<name>:<tag>` semantic dispatcher** in `scripts/safe_delete.py` (`_handle_ollama_delete` + four helpers: `_resolve_ollama_manifest_path`, `_collect_manifest_blobs`, `_digest_to_blob_path`, `_walk_other_manifests`). The UI name → manifest-path mapping mirrors the Ollama client's three-tier rule: first-segment `.` → literal `<host>/<rest>`; any `/` but no `.` in first segment → default registry + user namespace; plain name → default registry + `library` namespace. For each delete the dispatcher reads the target manifest's `config.digest` + `layers[].digest` set, walks every other manifest in the tree, unions their referenced digests into `still_referenced`, and removes only blobs exclusive to the target. Shared layers between e.g. `llama3:8b` and `llama3:70b` survive the delete of one sibling tag — the safety net v0.11 adds that earlier releases lacked.
- **SKILL.md Stage 3 mode branch** for Ollama. Quick mode keeps the single-aggregate `~/.ollama/models/` L3 defer entry (`mode_hit_tags=["quick"]`); deep mode walks `manifests/<registry>/<namespace>/<name>/<tag>` and emits one `ollama:<name>:<tag>` candidate per leaf (`source_label="Ollama model"`, `mode_hit_tags=["deep"]`). Per-model entries REPLACE the aggregate in deep mode; the aggregate is the deep-mode fallback if the manifest walk fails.
- **Operating invariant #8** in `references/safety-policy.md` locking Ollama per-model paths at L3 `defer` through Stage 5 — the history-driven UI downgrade may collapse per-item confirm into batch confirm but never bypass the confirm step itself. Symmetric to invariant #7 (orphan investigation L3 lock) and the "Risk-level boundaries are never crossed" history rule.

### Changed

- **HuggingFace split** — v0.8's merged L3 exception was too conservative for models: `~/.cache/huggingface/hub/**` drops to **L2 `trash`** (most snapshots under 1 GB, `from_pretrained()` will refetch), while `~/.cache/huggingface/datasets/**` stays **L3 `defer`** (a single dataset can exceed tens of GB, redownload costs hours). Split the merged exception into two independent rules so the cost/benefit asymmetry is explicit.
- **`references/cleanup-scope.md` Tier E Ollama row** rewritten to describe the v0.11 reality (quick mode = aggregate; deep mode = per-model via dispatcher; aggregate as deep-mode fallback) instead of the stale "per-model granularity is gated on a future dispatcher" note.
- **`references/category-rules.md` §3 Ollama exception** split into three distinct bullets (aggregate / per-model / LM Studio) so the `mode_hit_tags` differences are unambiguous.

### Fixed — Defence in depth

- **Adobe `Auto-Save` blacklist** added to `cleanup-scope.md` + `scripts/safe_delete.py::_BLOCKED_PATTERNS` (`/Adobe/[^/]+/Auto-Save(/|$)`). The generic `Adobe/**` sweep must never descend into `Auto-Save/` — those paths hold unsaved Premiere / After Effects / Photoshop project files, i.e. user work in progress. Creative-app source-label refinement (new in this release) was the motivating change; the blacklist is the defence-in-depth counterweight.

### Back-compat

- **`history.json` format unchanged** — every new `source_label` is just a new tag alongside existing ones. No schema migration.
- **`scan_projects.py`'s JSON output** adds one new `kind` value (`"nested_cache"`); consumers that hardcode `kind=="deletable"` skip it silently — same back-compat contract as v0.10.0's `coverage` addition.
- **`version_pins`** is a new sibling field on each project. Consumers that do `"X" in markers_found` membership checks (the existing pattern) simply never see it.
- **`PROJECT_MARKERS`** gains `.dvc/config` — a nested-path marker. Existing projects without it keep the same `markers_found` output.
- **`_BLOCKED_PATTERNS`** gains the Adobe `Auto-Save` regex additively; no existing pattern removed or tightened.

### Tests

- 100 → **123** (+23):
  - `tests/test_safe_delete.py`: **+2** for the Adobe `Auto-Save` blacklist (six-product positive matrix with root + nested depth, plus an end-to-end dispatch case asserting an unsaved `.prproj` survives the attempted delete).
  - `tests/test_scan_projects.py`: **+12** across two families — 4 for the `nested_cache` kind and `.dvc/config` marker (kind returned, surfacing even without the marker so Stage 4 can demote, silent when `.dvc/cache` is absent, marker presence in `PROJECT_MARKERS`), and 8 for `version_pins` edge cases (missing → `{}`, single Python version, multi-version pyenv chain, nvmrc, both langs, empty-or-whitespace omits key, comments + CRLF, missing-vs-present coexistence).
  - `tests/test_safe_delete_ollama.py` (new file): **+9** covering blob reference counting (shared-blob preserved on single delete, cascading reclaim across sequential deletes), dry-run parity without disk writes, corrupt-manifest redaction-safe failure, missing `manifests/` root fails cleanly, three malformed path forms, third-party `hf.co/...` registry mapping, default-registry user-namespace mapping, and an explicit blocklist-bypass smoke.

### Known limitation

- The Xcode 15+ `devicectl` output-schema assumption (`result.devices[].hardwareProperties.productVersion`) has not been end-to-end-verified against a real Mac with a paired iOS device. The schema matches Apple's public CoreDevice framework docs, and the inline script has an `except Exception: sys.exit(0)` bail-out so a schema drift manifests as an empty `active_ios_versions` (i.e. fallback to the L2 default), not as a crash.

## v0.10.0 — 2026-04-19

### Added
- **Seven new Tier E developer-tool rows** in `references/cleanup-scope.md` and `references/category-rules.md` §3 — RubyGems, Bundler, Composer, Poetry, ccache, sccache, Dart pub. Each row lists every candidate cache path (Composer / ccache / sccache ship two defaults on macOS) so Stage 2 probes the one the user's tool actually writes to. All L1 `pkg_cache` with generic tool-name `source_label`s so redaction holds. `SKILL.md` Stage 2 `which -a` and `ls -d` probe lines extended to match.
- **Five new `scan_projects.py` deletable subtypes** — `.mypy_cache`, `.ruff_cache`, `.dart_tool`, `.nyc_output`, `_build` — wired into `references/category-rules.md` §10a. `_build` is gated by a new `mix.exs` marker in `PROJECT_MARKERS` so it only surfaces in Elixir projects. The previous "unambiguous dotfile names don't need a marker" rule carries `.mypy_cache` / `.ruff_cache` / `.dart_tool` / `.nyc_output`.
- **New `coverage` artifact kind** in `scan_projects.py` + `references/category-rules.md` §10c. Default L2 `trash` (session recovery window) and marker-gated at Stage 4: the agent treats `coverage/` as `project_artifacts` only when `markers_found` contains `package.json` or any Python marker; otherwise `orphan` L4. Parallel carve-out to the existing `env` / `vendor` / `_build` disambiguation.
- **Stage 3.5 now runs the large-directory probe** that `references/category-rules.md` §7 has documented since v0.4 but never actually executed. `timeout 45 du -k -d 2 ~` post-filtered to ≥ 2 GiB, top 30 by size; agent normalises paths before deduping against existing Stage 3 / Stage 3.5 candidates. Classifies as `large_media` L3 `defer` with the generic `source_label="Unclassified large directory"`. Surface-only — never auto-acts; always goes through Stage 5 per-item review.

### Back-compat
- `aggregate_history.py`'s `history.json` format is unchanged; the new `source_label`s are just new tags alongside existing ones.
- `scan_projects.py`'s JSON output adds one new `kind` value (`"coverage"`). Consumers that hardcode `kind=="deletable"` skip it silently — that's the back-compat contract.
- `PROJECT_MARKERS` gains `mix.exs`; existing projects without it keep the same `markers_found` output.

### Tests
- 95 → **100** (`test_scan_projects.py` adds five cases: new deletable subtypes, `_build` + `mix.exs` gating, `coverage` kind, `mix.exs` membership in `PROJECT_MARKERS`; `test_safe_delete.py` adds a v0.7 Tier E cache-path regression asserting `_BLOCKED_PATTERNS` does not accidentally catch `~/.gem`, `~/.composer`, `~/.pub-cache`, etc.).

## v0.9.4 — 2026-04-19

### Fixed
- **Docker prune reclaim bytes are no longer over-reported by ~7%.** The shared `_parse_human_bytes` helper added in v0.9.0 was hard-coded to base-1024 (binary). Brew prints reclaim via Ruby's `Utils::Bytes` (binary, traditional `KB/MB/GB` labels) — base-1024 is correct there. Docker prints reclaim via Go's `units.HumanSize` (decimal, lowercase `kB`) — base-1024 over-counts by ~7% at GB scale, ~10% at TB. Bad fit for the project's "honest reclaim accounting" contract. Split into `_BINARY_UNIT_FACTORS` (brew) and `_DECIMAL_UNIT_FACTORS` (docker); `_parse_human_bytes` now takes a factors arg.
- **brew / docker dispatch failures now surface stderr in `actions.jsonl`.** Previously the handlers caught `CalledProcessError` and only stringified it, giving "Command [...] returned non-zero exit status 1." — useless for diagnosis. Extract a `_format_subprocess_error` helper that pulls `.stderr` when present (CalledProcessError + TimeoutExpired) and falls back gracefully for OSError / FileNotFoundError. First stderr line is truncated to 200 chars so each `actions.jsonl` record stays single-line.

### Tests
- 93 → **95** (`test_safe_delete.py` adds: docker failure stderr propagation; OSError formatter no-attr branch; existing brew failure test extended to assert stderr surfacing and trailing-line truncation).

## v0.9.3 — 2026-04-19

### Docs
- **Tighten 4 per-item filter rules in `references/*.md` for LLM agent execution.** Per-item filters are interpreted by the agent at Stage 3, not by deterministic code, so ambiguous wording can cause silent misclassification:
  - iOS Backup `~/Library/Application Support/MobileSync/Backup`: "older than 180 days" → "mtime older than 180 days" with explicit `find ... -mtime +180` probe.
  - pyenv `pyenv local` collection: previously "any pin discovered via `pyenv local` in scanned projects" left *how to discover* unspecified (`pyenv local` only returns the cwd's pin); now spells out that the agent must `cd` into each project root from `paths-projects.json` and run `pyenv local`, taking the union of non-empty results.
  - Xcode Archives exception: clarify that L2 trash for `<90d` wins on a tied match; not both rules at once.
  - Homebrew cache: "contents older than 30 days" → "files within the directory whose mtime is older than 30 days; the directory itself is never deleted, only its files" with explicit `find` probe — avoids an over-eager agent rm'ing `$(brew --cache)` itself.

### Tests
- 93 (unchanged — pure doc clarity tweaks).

## v0.9.2 — 2026-04-19

### Added
- **§6a clear-cut installers gains four cross-platform extensions** in `category-rules.md`: `.appimage` (Linux), `.deb` (Debian), `.rpm` (RPM), `.msi` (Windows). Same 30-day threshold + L1 delete as the existing macOS-native `.dmg` / `.pkg` / `.xip` / `.iso` — these are unusable on macOS and almost always one-off downloads the user forgot about.
- **New §6c "Pulled-out applications in Downloads"** surfaces `~/Downloads/*.app` bundles older than 90 days with size > 100MB as **L3 defer** (deep mode only). The agent can't reliably distinguish a freshly extracted DMG awaiting drag-to-Applications from a forgotten extraction or a portable app run in place, so it surfaces in deferred and the user picks. Quick mode skips entirely so a fresh extraction never appears.

### Changed
- **`cleanup-scope.md` Tier D `~/Downloads` row** rewritten to enumerate the v0.9.2 extension set and the new `.app` rule for parity with `category-rules.md`.

### Tests
- 93 (no change). The new rules are pure pattern additions; no new dispatch path or behavior change.

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
