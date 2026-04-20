# mac-space-cleanup — Contributor Notes

These notes apply to anyone (human or agent) working on this skill. For the user-facing workflow, read `SKILL.md`; for the safety model, read `references/safety-policy.md`.

## Skill positioning

This is an **agent-first skill**. `SKILL.md` is the main deliverable — it instructs the agent through a seven-stage cleanup workflow. Python scripts exist only to do what the agent cannot do safely or efficiently:

- `scripts/safe_delete.py` — unified controlled write path (delete / trash / archive / migrate / defer / skip) with actions.jsonl audit trail.
- `scripts/collect_sizes.py` — parallel `du` with per-path timeout and error isolation.
- `scripts/scan_projects.py` — project-artifact discovery (node_modules, target, .venv…) scoped to `.git`-marked roots.
- `scripts/aggregate_history.py` — cross-run confidence aggregator feeding Stage 5 `HISTORY_BY_LABEL`; also GCs old `run-*` directories.
- `scripts/validate_report.py` — deterministic second-line redaction check on the rendered report.

Do not re-introduce `scan_space.py`, `classify_items.py`, `build_report.py`, or `share_text.py` — those responsibilities belong to the agent (Bash probes, rule-based judgement, HTML/share-text composition).

## Non-negotiable invariants

1. **Agent never writes the filesystem for cleanup purposes.** Every `delete / trash / archive / migrate / defer` against **user-owned paths** must route through `scripts/safe_delete.py`. The only direct agent writes are JSON/HTML files under `$WORKDIR`. Scripts under `scripts/` MAY manage their own workdir-family state directly — see `references/safety-policy.md` §"Operating invariants" #1 + #3 for the cross-run GC carve-out in `aggregate_history.py`.
2. **Redaction is absolute.** Anything that reaches `report.html`, `share-card.svg`, or `share.txt` must use `source_label` + `category` only. No paths, basenames, usernames, project names, or company names. See `references/safety-policy.md` §"Privacy redaction rules".
3. **Workdir is per-run**: `~/.cache/mac-space-cleanup/run-XXXXXX` created by `mktemp -d`. Never reuse across runs.
4. **Templates in `assets/` are immutable at runtime.** Agent must `cp` them into `$WORKDIR` before editing.
5. **`actions.jsonl` is append-only and authoritative *within a single run*.** Safe_delete re-runs against the same `$WORKDIR` are idempotent: already-gone paths become `action=skip, status=success, reason="already gone"`. Cross-run preservation is best-effort — `aggregate_history.py` GCs old `run-*` dirs per its `--keep` window. See `references/safety-policy.md` §"Operating invariants" #3.
6. **History-driven UI decisions never cross risk-level or mode boundaries.** `scripts/aggregate_history.py` produces a per-run `history.json` that Stage 5 may consult to collapse per-item prompts into batch prompts. It MUST NOT be used to auto-execute a tag that would otherwise prompt, to up-tier a Quick-mode scan, or to influence Stage 4 grading. See `references/safety-policy.md` §"History-driven UI adjustments" for the authoritative rules.
7. **Localized report — one locale per run, any language.** The template keeps `data-i18n` attributes on every static label with an English baseline inside the span. `assets/i18n/strings.json` is a single flat `{key: value}` EN dictionary — the canonical English copy. For non-English runs, Stage 6 translates every `strings.json` value into the target locale and writes the result as a single JSON object into the `<script id="i18n-dict">` container; a short hydration script in the template replaces each `data-i18n` node's text on first paint. For English runs the dict stays `{}` and the baseline text renders as-is. There is **no runtime language toggle**, no `data-locale-show` sibling-span pair pattern, and no bilingual share artefacts — share card and share text are each a single `$LOCALE` file (`share-card.svg`, `share.txt`). Any agent-authored natural-language node (captions, reasons, recommendations, `source_label` rendering) is emitted once, in `$LOCALE`. `validate_report.py` enforces four structural invariants only: (a) if the dict is non-empty, every dict key appears as a `data-i18n` attribute in the template; (b) every template `data-i18n` key appears in `strings.json`; (c) redaction; (d) placeholder / region fills. See `references/safety-policy.md` for the full redaction policy.

## Editing the reference docs

`references/*.md` are the agent's knowledge base — updates there change agent behaviour even without touching code. When you edit:

- `cleanup-scope.md`: if you add a new whitelist path, make sure it is not inside any `blacklist` pattern. If you add a Tier E row, decide whether it uses a **CLI probe** (goes on `which -a` in SKILL.md Stage 2) or a **directory probe** (goes on `ls -d` in SKILL.md Stage 2) — and extend the matching line there in the same commit. A Tier E row with no Stage 2 gate will silently never be scanned.
- `safety-policy.md`: the risk-level semantics and the redaction forbid-list are load-bearing. Changes here must be reflected in commit messages or CHANGELOG so agents / reviewers notice the behaviour shift.
- `category-rules.md`: new categories require updating the `category` enum in `scripts/safe_delete.py` and `SKILL.md` "Quick reference" section. Existing tests do not enumerate categories, but new L3 defaults should be cross-checked against `safety-policy.md`. `source_label` remains English-canonical — Stage 6 translates it on the fly into `$LOCALE` when needed; no per-locale rendering table is maintained.

## Report templates

The report is a single long page — `assets/report-template.html` — that carries eight paired-marker regions: `hero`, `share`, `impact`, `nextstep`, `distribution`, `actions`, `observations`, `runmeta`. CSS lives in `assets/report.css`; `assets/share-card-template.svg` is filled as a workdir artifact (`$WORKDIR/share-card.svg`, one file in `$LOCALE`) but is not embedded in the report. Static labels in the template carry `data-i18n="<section>.<slot>"` attributes with an English baseline inside the span. `assets/i18n/strings.json` is a single flat EN dict — the canonical source of those labels. Stage 6 either leaves the `<script id="i18n-dict">` container as `{}` (English run → baseline renders directly) or translates `strings.json` into `$LOCALE` and writes the result into the container (non-English run → short hydration script swaps text on load).

When you add, remove, or rename a region marker:

- Update `REGIONS` in `scripts/validate_report.py`.
- Update `_PLACEHOLDER_MARKERS` in the same file if the region's `data-placeholder="..."` value changes.
- Update the Stage 6 step 4 region list in `SKILL.md` — the agent fills from those instructions, a silent drift means regions get left as placeholders.
- Update the fixture helper in `tests/test_validate_report.py` if a new region should participate in a happy-path test.

All four must move in the same commit — a region in the template that isn't in `REGIONS` is a silent leak risk (unfilled placeholder never fails validation), and vice-versa a region in `REGIONS` that isn't in the template will always flag missing.

When you add a new static label to the template:

- Use a `data-i18n="<section>.<slot>"` attribute with the English baseline inside the span.
- Add the key to `assets/i18n/strings.json` (single flat dict); the validator enforces that every template `data-i18n` key appears there, and that any emitted dict entry points back at a real template key.
- No per-locale maintenance is needed — Stage 6 translates the EN value into `$LOCALE` on demand.

## Testing

All tests are pure-stdlib `unittest`, no external dependencies.

```bash
python3 -m unittest discover -s tests -v
```

The test suite covers only the scripts. Agent behaviour (Stages 1–6) is verified end-to-end through manual dry-runs, not unit tests — rule interpretation is the agent's responsibility and is not mechanically testable without LLM-in-loop harnesses.

When you touch `scripts/*.py`, add or update tests in the same commit. Smoke-test the whole pipeline with:

```bash
WORKDIR=$(mktemp -d ~/.cache/mac-space-cleanup/test-XXXXXX)
echo '{"paths":["~/Library/Caches"]}' > "$WORKDIR/paths.json"
python3 scripts/collect_sizes.py < "$WORKDIR/paths.json" > "$WORKDIR/sizes.json"
echo '{"confirmed_items":[]}' | python3 scripts/safe_delete.py --workdir "$WORKDIR" --dry-run
```

## Commit conventions

- One atomic commit per concern. Do not bundle script changes with reference-doc changes.
- Prefixes (Conventional Commits subset):
  - `feat:` — new capability in `scripts/` (or new probes / rules that unlock capability in `references/` without accompanying code).
  - `fix:` — corrects a defect in `scripts/` code or behaviour documented in `references/`. Use when the previous state was wrong, not merely less clear.
  - `refactor:` — restructures code without changing behaviour (rename, extract, dead-code removal, constant rewiring). No user-visible change.
  - `docs:` — SKILL.md / references / CLAUDE.md prose changes. Use for pure clarification, not for behaviour changes (those go under `fix:` or `feat:`).
  - `test:` — additions or changes under `tests/`.
  - `chore:` — scaffold, assets, tooling, release housekeeping.
- Body should explain *why*, not *what*. Paths and function names already carry the *what*.

## Translated READMEs

The repo keeps 7 translated READMEs alongside the English `README.md` at the project root, using the filename-suffix convention: `README.zh-CN.md`, `README.zh-TW.md`, `README.ja.md`, `README.es.md`, `README.fr.md`, `README.ar.md`, `README.de.md`. Every README carries the same top-of-file language navigation bar in a fixed order (EN → zh-CN → zh-TW → ja → es → fr → ar → de); the current locale renders as bold plain text, the others as links.

**Substantive edits to `README.md` must be mirrored into all 7 translations in the same PR** — section additions or removals, paragraph rewrites, trigger-phrase table changes, command-line example updates, and semantic shifts in the Architecture / Honesty contract / Limitations sections. If a single PR is too large to fully translate, you may commit a structural skeleton (section headings and table scaffolds) with a `⚠ Translation pending since commit ABCDEFG` note at the top of the affected section, and land the translation in the immediately following commit. **"Translation pending" state must not cross PR boundaries.**

**Exemptions (English-only edits are OK):** typo fixes, pure Markdown formatting tweaks (blank lines, table alignment, fenced-block language tags), URL updates, credit or version-number housekeeping. The translations catch up naturally on the next substantive change.

**SKILL.md is not translated.** It is the agent's workflow contract and already emits localized report copy at runtime via `$LOCALE` (see §"Operating invariants" #7). `references/*.md` are likewise agent-only and not translated. This multilingual effort covers GitHub-surface documentation only.

Translation drift is the top documentation bug risk in this repo. Reviewers of any substantive `README.md` change must open all 7 translations side-by-side and confirm: structural isomorphism (section count, code-fence count), trigger-phrase table localized to the target language, commands / paths / proper nouns unchanged.

## v0.7 coverage expansion

v0.7 widens Tier E and project-artifact coverage on polyglot developer Macs without changing the L1-L4 risk model, the redaction rules, or the blacklist:

- **Tier E gains seven rows** (all L1 `pkg_cache`, probed via CLI or dir-marker in Stage 2): RubyGems, Bundler, Composer, Poetry, ccache, sccache, Dart pub. Each row lists all candidate paths (Composer, ccache, sccache each ship two defaults on macOS) so whichever location the user's tool writes to is detected.
- **`scan_projects.py` learns five new deletable subtypes** — `.mypy_cache`, `.ruff_cache`, `.dart_tool`, `.nyc_output`, `_build` — plus a new `coverage` kind. `_build/` is gated by a new `mix.exs` marker (Elixir); `coverage/` is gated at Stage 4 by the presence of `package.json` or any Python marker (`pyproject.toml` / `requirements.txt` / `setup.py`) — fall through to `orphan` L4 otherwise. Both are parallel carve-outs to the existing `vendor` / `env` disambiguation, and the authoritative rule lives in `references/category-rules.md` §10c.
- **Stage 3.5 runs the `du -d 2 ~` large-directory probe** that `category-rules.md` §7 has documented since v0.4 but never executed. Output becomes `large_media` L3 `defer` with the generic `source_label="Unclassified large directory"`.

Cross-run history (`history.json`) stays format-compatible: new source_labels are just new tags. `scan_projects.py`'s JSON output adds one new `kind` value (`"coverage"`); consumers that hardcode `kind=="deletable"` skip it silently, which is the back-compat contract.

## v0.8 AI/ML coverage and orphan investigation

v0.8 covers the AI/ML workflow gap on modern Macs and turns Stage 3.5's du-probe orphans from a generic "Unclassified large directory" placeholder into something usefully specific — without changing the L1-L4 risk model, the redaction rules, the blacklist, or any `scripts/*.py` code:

- **Tier E gains four rows** (all `pkg_cache`, dir-probe only in Stage 2; Ollama deliberately skips the CLI probe so a leftover `~/.ollama` after the user uninstalled the CLI still surfaces): HuggingFace (`hub/` and `datasets/` as two aggregate items), PyTorch hub (one aggregate item), Ollama (one aggregate item), LM Studio (one aggregate item from whichever of `~/.cache/lm-studio` / `~/.lmstudio` exists). All four route to L3 `defer` except PyTorch hub which is L2 `trash` (typical pretrained weights are < 1 GB). Per-model granularity is intentionally deferred — the underlying storage is content-addressed, and naive per-manifest `rm` would orphan shared blobs without an `ollama:<model>` semantic dispatcher in `safe_delete.py`. `category-rules.md` §3 carries the matching exception entries and the source_label table grows by five labels (`"HuggingFace model cache"` / `"HuggingFace dataset cache"` / `"PyTorch hub cache"` / `"Ollama model cache"` / `"LM Studio model cache"`).
- **Stage 3.5 grows an investigation step** at the tail. The existing `du -d 2 ~` probe still finds large unclassified directories, but before each one is finalised with the generic `"Unclassified large directory"` label, the agent runs a small read-only investigation (`ls` / `file` / `head` plus marker-file existence checks, capped at 6 commands per candidate) and may refine `category` (∈ §1-§9; **never §10 `project_artifacts`**, which is reserved for `scan_projects.py`) and `source_label` (canonical labels or new ones following the "tool/product name + category descriptor" convention). `risk_level=L3` and `action=defer` stay locked regardless — that lock is what makes it safe to let the agent reclassify in the first place. The authoritative rules live in `references/safety-policy.md` §"Orphan investigation" and Operating invariant #7.
- **No `scripts/*.py` changes.** `safe_delete.py`'s `_BLOCKED_PATTERNS` is unchanged (the four new AI cache paths don't match any existing pattern), no new dispatcher prefix is introduced, and the test suite needs no new cases. `history.json` stays format-compatible: the five new `source_label` values are just new tags. Per-model surfacing for Ollama / LM Studio / HuggingFace, plus the `ollama:<model>` semantic dispatcher and Conda / Stable Diffusion / ComfyUI coverage, are explicitly deferred to a future version.

## v0.9 coverage expansion

v0.9 expands AI/ML and creative-workflow coverage, sharpens the `app_cache` source_label granularity, promotes two long-standing "documented but unimplemented" lookups in `scripts/scan_projects.py` into real code, and introduces the first non-vendor-CLI semantic dispatcher (`ollama:<name>:<tag>`). The L1-L4 risk model, redaction rules, and Stage 4–5 confirmation bars are unchanged; the blacklist grows by exactly one entry (Adobe `Auto-Save`). Landed in three internal milestones rolled up into a single ship PR.

### M1 — Tier E expansion + creative-app labels (rules-heavy)

- **Tier E gains five rows** (all `pkg_cache`, dir-probe in Stage 2): Conda / Mamba / Miniforge envs (per non-`base` env across seven macOS install layouts including miniforge / mambaforge on Apple Silicon, L2 `trash`, `mode_hit_tags=["deep"]`; scope stops at `~/...` to avoid system `/opt/miniconda3/envs`), Playwright (macOS Caches + XDG fallback + driver-binaries, L1 `delete`), Puppeteer (L1 `delete`), OpenAI Whisper (L2 `trash`; Faster-Whisper is explicitly redirected to the HuggingFace row), Weights & Biases global cache (`~/.wandb` + XDG `~/.cache/wandb`, L2 `trash`). `source_label` table grows by five labels.
- **HuggingFace split** (v0.8's merged L3 exception was too conservative for models): `~/.cache/huggingface/hub/**` drops to **L2** `trash` — most snapshots are under 1 GB and `from_pretrained()` will refetch reliably; `~/.cache/huggingface/datasets/**` stays **L3** `defer` because a single dataset can exceed tens of GB and redownload costs hours.
- **Creative-app source_label refinement** — `category-rules.md` §4 gains a refinement table mapping Adobe Media Cache / Peak Files / Final Cut Pro / Logic Pro paths to specific `source_label` values. GarageBand's downloadable instrument libraries are deliberately excluded — user-initiated content, not regenerable cache. Risk grading is unchanged (L2 `trash` via the Tier C-adjacent override); only the UI label becomes specific so the report names the actual workflow rather than `"System caches"`.
- **Adobe Auto-Save blacklist** (defence in depth) — the generic `Adobe/**` sweep must never descend into `Auto-Save/`, which holds unsaved Premiere / After Effects / Photoshop project files. `cleanup-scope.md` blacklist gains an explicit entry; `scripts/safe_delete.py::_BLOCKED_PATTERNS` gains the `/Adobe/[^/]+/Auto-Save(/|$)` regex; `tests/test_safe_delete.py` grows two cases (six Adobe products root + nested depth, and end-to-end unsaved `.prproj` survives the attempted delete).

### M2 — `scan_projects.py` extensions + Xcode active-OS detection

- **`nested_cache` artifact kind** for the "keep parent, drop cache-child" pattern — currently just `.dvc/cache`. Sibling `.dvc/config` is a new nested-path entry in `PROJECT_MARKERS` (marker-gated at Stage 4 per `category-rules.md` §10d); `_detect_markers`'s existing `os.path.join` + `isfile` logic handles flat and nested paths uniformly. Default L2 `trash` (rebuild requires network pull).
- **`version_pins` emission** per project — `_parse_version_pin_file` reads `.python-version` / `.nvmrc` tolerating multi-version pyenv chains (`3.11.4 3.10.8`), comment lines, CRLF, empty files, and unreadable files. SKILL.md Stage 3 takes the union across all scanned projects and appends to the pyenv / nvm exclusion set — replacing the v0.4 "`cd` into each project and run `pyenv local`" choreography that was never wired up.
- **iOS DeviceSupport active-OS downgrade** (references-only; no script change) — Stage 2 collects active iOS versions from `xcrun devicectl list devices --json-output -` (Xcode 15+; physical paired devices) and `xcrun simctl list devices available --json` (all Xcode versions; installed simulator runtimes). The union seeds `environment_profile.active_ios_versions`. Stage 4 normalizes both sides to `major.minor` and, on equal-string match, downgrades the `iOS DeviceSupport/<OS>` entry from L2 `trash` to L3 `defer`. Empty union is a first-class "no hint" state — every entry stays at the L2 default. `watchOS` / `tvOS` DeviceSupport have no equivalent active-OS source and always stay L2.

### M3 — Ollama per-model dispatcher

- **`scripts/safe_delete.py` gains `_handle_ollama_delete`** plus four helpers (`_resolve_ollama_manifest_path`, `_collect_manifest_blobs`, `_digest_to_blob_path`, `_walk_other_manifests`) and a new `OLLAMA_PATH_PREFIX = "ollama:"`. The UI name → manifest-path mapping mirrors the Ollama client's three-tier rule (first-segment `.` → literal host; any `/` but no `.` → default registry + user namespace; plain name → default registry + `library`). For each delete the dispatcher reads the target manifest's `config.digest` + `layers[].digest` set, walks every other manifest in the tree, unions their referenced digests into `still_referenced`, and removes only blobs exclusive to the target. This is the safety net that v0.8 lacked: a naive `rm` on a manifest would have orphaned content-addressed blobs still referenced by a sibling tag.
- **SKILL.md Stage 3 branches on mode** — quick mode surfaces the v0.8 single-aggregate `~/.ollama/models/` L3 defer entry (`mode_hit_tags=["quick"]`); deep mode walks `manifests/<registry>/<namespace>/<name>/<tag>` and emits one `ollama:<name>:<tag>` candidate per leaf with `source_label="Ollama model"` and `mode_hit_tags=["deep"]`. Per-model entries REPLACE the aggregate in deep mode — both would double-count bytes. Aggregate is the deep-mode fallback if the manifest walk fails.
- **`references/safety-policy.md` gains Operating invariant #8** locking Ollama per-model paths at L3 `defer` through Stage 5 — the history-driven UI downgrade may collapse per-item confirm into batch confirm but never bypass the confirm step itself. Symmetric to invariant #7 (orphan investigation L3 lock) and the "Risk-level boundaries are never crossed" history rule.
- **`tests/test_safe_delete_ollama.py` is new** with 9 cases: shared-blob preservation on single delete, cascading cleanup across sequential deletes, dry-run accounting with no disk writes, corrupt-manifest redaction-safe failure (the full manifest path is deliberately kept out of `actions.jsonl`), missing `manifests/` root fails cleanly, three malformed path forms, third-party `hf.co/...` registry mapping, default-registry user-namespace mapping, and an explicit blocklist-bypass smoke. All 123 tests pass (+23 across v0.9 — 2 for Adobe `Auto-Save`, 12 for `scan_projects` nested_cache + version_pins, 9 for this new file).

LM Studio stays on the single aggregate in v0.9 — storage layout is less uniform across versions and a dispatcher has not yet been written. The `"Ollama model"` source_label (singular) is new for per-model entries; `"Ollama model cache"` (plural / aggregate) remains for quick-mode and the fallback path.

### Back-compat & known gaps

- **Cross-run history (`history.json`) stays format-compatible** across M1-M3: new source_labels are just new tags; `version_pins` is a new sibling field that downstream `"X" in markers_found` membership checks never see; `projects.json`'s `kind` enum grows by one value (`nested_cache`), same contract as v0.7's `coverage` addition.
- **Known untested path**: the Xcode 15+ `devicectl` output-schema assumption (`result.devices[].hardwareProperties.productVersion`) has not been end-to-end-verified against a real Mac with a paired iOS device. The schema matches Apple's public CoreDevice framework docs, and the inline script has an `except Exception: sys.exit(0)` bail-out so a schema drift manifests as an empty `active_ios_versions` (i.e. fallback to the L2 default), not as a crash. If a future reader has access to such a setup, confirm the keys and either strike this note or file a fix.

## v0.12 dry-run detection refactor + README "Why this skill" section

v0.12 replaces the keyword-substring approach for dry-run detection with intent-based LLM judgement, and introduces a top-of-README comparison section addressing the most common reader question. No risk-model / redaction / blocklist changes; `scripts/*` unchanged; test suite unaffected.

### SKILL.md — dry-run detection refactored

v0.11.0's substring-match rule (`DRY_RUN=true if triggering message contains any of: --dry-run, dry run, 预演, 模拟, 演练`) had a latent collision: `模拟` is a substring of `模拟器` (simulator), so any Simplified-Chinese user asking to clean iOS Simulator caches — a first-class Tier-B target of this skill — would be silently routed into dry-run mode and nothing would actually be deleted. A mid-PR attempt to expand the list to 19 keywords across 8 locales (covering zh-TW `模擬`, ja `ドライラン` / `予行演習`, es `simulacro` / `prueba en seco`, fr `essai à blanc` / `à blanc`, ar `تجربة جافة`, de `Probelauf` / `Trockenlauf`) surfaced that substring-match is the wrong primitive regardless of list size — `à blanc` collides with `voter à blanc` / `tirer à blanc`, `模擬` repeats the simulator collision for zh-TW, etc.

Stage 1's dry-run detection step now instructs the agent to judge user intent (preview vs real-run) directly from the triggering message, in whatever language the user wrote. Explicit signals — the CLI-style `--dry-run` flag, phrases like "preview only" / "don't actually delete" / "只预演不要真删" / "先不要真的删" / "essai à blanc" / "Probelauf" — count as strong evidence; a substring coincidence with a cleanup target name (`Simulator` / `模拟器`) explicitly does not. When intent is ambiguous, the rule prefers `DRY_RUN=false` and relies on Stage 5's per-item L2+ confirmation prompts as the safety net.

Downstream consumers are unaffected: Stage 5 / Stage 6 still read `$WORKDIR/dry_run.txt` as a bool, `scripts/safe_delete.py --dry-run` is unchanged, `scripts/validate_report.py --dry-run` is unchanged. No new test coverage needed — agent NL understanding is not mechanically testable per `CLAUDE.md` §Testing, and the CLI flag semantics that `safe_delete.py` / `validate_report.py` depend on are unchanged.

### README — "Why this skill" section across all 8 locales

`README.md` and the 7 translations gain a `## Why this skill` section placed **between the intro quote and the Try section**, so the elevator pitch lands before the reader hits the one-click try command. Two short paragraphs, no table. The argument in plain form:

- Traditional cleaners (CleanMyMac, OnyX) work from fixed rules — **they can't judge your situation**. Whether a given `node_modules` is still active, whether a cache folder is live or abandoned — same path, different answer per user.
- An **unguarded agent** ("Claude, clean my Mac") has that judgment, but **no guardrails** — one wrong call and `rm -rf` hits `.git` / `.env` / Keychains.
- This skill combines both: agent judgement in front, `safe_delete.py`'s deterministic blocklist behind. Locale-appropriate punchline closes the section (English: *"Smart decisions where they help, hard rules where they matter."*).

Terminology note: earlier drafts used "LLM" / "raw LLM prompt". Replaced with **"agent" / "unguarded agent"** — the LLM is the reasoning model, but the thing that can actually `rm -rf` your filesystem is the agent loop (tool use + iteration). Getting the term right matters for this section's argument.

Earlier drafts during development included an 8-row comparison table after the paragraphs and placed the section between Demo and Install. Both were removed in favour of the current compact, up-front form so the section reads as a pitch rather than a specification.

Translation note: `redaction` was rendered to each locale's natural equivalent where one exists (`anonymisation` / `anonymisés` for fr, `マスキング` for ja); where a natural equivalent is contextually awkward it's kept as a backticked English technical token. `guardrail` / `blocklist` / `dispatcher` stay English inline.

### Back-compat & known gaps

- **No `scripts/*.py` / `tests/*` changes.** The dry-run flag shape (`$WORKDIR/dry_run.txt` as a bool, `safe_delete.py --dry-run`, `validate_report.py --dry-run`) is unchanged. Agents running against an older SKILL.md with the substring rule continue to work; agents running against the new SKILL.md get better i18n coverage and no substring collisions.
- **Single-commit boundary note.** This release includes a small window where `SKILL.md`'s L80 whitelist was expanded to 19 keywords before being replaced by intent-based detection (commit 1 → commit 6 of the PR series). Only the final state lands on `main`; historical git log carries the traversal.
- **CLAUDE.md gap backfill**: this entry also flags that v0.10 and v0.11.0 are recorded in `CHANGELOG.md` but were never given dedicated sections in this CLAUDE.md file. The pattern since v0.7 had been a section per significant expansion. Backfilling v0.10 and v0.11.0 is out-of-scope for this PR but worth a separate docs pass.

## v0.13 README rewrite (8 locales)

v0.13 is documentation-only. No `scripts/*.py` / `tests/*` / `SKILL.md` / `references/*` changes. The 8-locale README family is rewritten to drop AI-flavored register inherited from earlier drafts and to align headline structure with the actual user-facing pipeline.

### What changed

- **L5 tagline collapse.** Three-adjective tagline (`cautious, honest, multi-stage` and per-locale equivalents) replaced by a single plain sentence. Three-adjective patterns read as marketing copy and add no information beyond what the L7 blockquote already states.
- **L7 blockquote tighten.** Pipeline summary moved from seven stages (`mode → probe → scan → classify → confirm → report → open`) to six. Stage 7 (`open`) is the share-text self-check + `open report.html` — a real Stage in `SKILL.md` because the agent needs the gate, but invisible to the user-facing arc and dilutive when listed alongside the six judgement stages. SKILL.md Stage 7 is unchanged. Bolds on `L1-L4 risk grading` / `honest reclaim accounting` / `multiple safety backstops` removed; the JSON field-name enumeration (`freed_now / pending_in_trash / archived`) removed (those belong to the schema in SKILL.md). The "Trash bytes counted separately, not in the freed total" honesty claim is preserved as a single inline clause.
- **Why section: two paragraphs → three.** Old structure: rule-based-tools-can't-judge / this-skill-combines-both with a bolded mid-sentence punchline. New structure mirrors the actual decision tree the reader is making: (1) why CleanMyMac et al. leave space behind, (2) why a raw "Claude, clean my Mac" prompt is unsafe, (3) why this skill solves both — safety boundary first, then full agent judgement within it. The "raw agent is dangerous" middle paragraph is the load-bearing one — without it readers don't see why this skill exists rather than just typing the prompt themselves.
- **Honesty contract section deleted.** The four-bullet field enumeration (`freed_now_bytes` / `pending_in_trash_bytes` / `archived_source_bytes` / `reclaimed_bytes`) was implementation detail surfaced at README level. SKILL.md's `cleanup-result.json` schema section is the canonical home; the user-facing claim ("Trash isn't free space — counted separately") survives as a clause in the L7 blockquote.
- **Section / header cleanup.** `What it touches (and never touches)` → `Scope`. `Architecture (one paragraph)` → `Architecture`. `Limitations & non-goals (v0.11.0)` → `Limitations` (version pin removed — README is evergreen, version belongs in CHANGELOG). `### Recommended optional dependency` H3 folded into Install body. `### Report language` H3 deleted (its content was already covered three times: L7 blockquote, Demo intro, Use dry-run note); the only unique sentence (RTL `<html dir="rtl">` note) is merged into the Use dry-run paragraph tail.
- **Self-reference paragraph deleted.** The "Agent itself reads `references/cleanup-scope.md`…" trailer at the end of Scope was internal documentation surfaced at README level; readers do not need to know which reference doc the agent reads.
- **Project layout notes synced.** SKILL.md comment changed from "(seven stages)" to "(six stages)". `HTML 骨架` / `squelette HTML` / `HTML-Skelett` etc. → `HTML template` / equivalents. `可清产物` → `可清理产物` for clarity in zh-CN.

### Tone passes per locale

The substantive AI-flavor diagnosis was: bolds used as emphasis crutches mid-sentence, three-adjective taglines, parallel "trigger in EN → EN report; in ZH → ZH report" listings designed to pad with rhythm rather than convey information, parenthetical detail dumps inside Architecture, virtue-signalling section titles (`Honesty contract`, `What it touches (and never touches)`). Each locale was passed through its own natural technical-document register rather than a literal translation of the EN edits — for example zh-CN swapped colloquial verbs (`跑`, `走完`, `配...三道兜底`, `钉死`) for technical ones (`执行`, `经由`, `构成三层护栏`, `锁定`); ja dropped `?` interrogatives and `絶対に` emphasis; es / fr / de / ar dropped marketing punchlines and adversary-comparison openings (`Toda herramienta...`, `Chaque outil...`, `Jedes Speicher-Aufräumtool...`, `كلُّ أداة...`).

User-spoken trigger examples in the Use table (e.g. `"马上腾点空间" / "找大头" / "fais un petit coup de balai"`) deliberately retain a colloquial register — they are documenting how real users phrase requests, not setting the register of the document itself.

### Structural isomorphism

All 8 README files now match line count (191 lines each) and section ordering. Section count: 12 H2s (`Why this skill / Try it with skillx / Demo / Install / Use / Scope / Architecture / Project layout / Limitations / Development / License / Credits`). The `### Recommended optional dependency` and `### Report language` H3s are absent in all locales. Scope-section bullet count and Limitations-section bullet count match across locales. Reviewers of future README changes should run `wc -l README*.md` as a first-pass drift check.

### Back-compat & known gaps

- **No code or behaviour changes.** Skill workflow, scripts, tests, references unchanged. Agent runs against the new READMEs the same way it ran against the old ones — they are not part of its instruction surface (only `SKILL.md` and `references/*` are).
- **Honesty-contract content preservation.** The `freed_now_bytes` / `pending_in_trash_bytes` / `archived_source_bytes` / `reclaimed_bytes` field semantics still need a documented home — they are kept in SKILL.md's `cleanup-result.json` schema section and surface to users via the report's nextstep / observations sections at runtime. Removing them from the README does not orphan them.
- **CHANGELOG.md not updated in this docs-only PR.** The `## Unreleased` line in CHANGELOG.md remains empty. A future release-cut commit can land a v0.13 CHANGELOG entry alongside any accompanying behaviour changes; documentation rewrites alone have not historically warranted release notes in this repo.

## Known non-goals (v0.1)

See `plan` history and `SKILL.md`. Summary: no undo stack, no cron, no cloud sync, no SIP-region touches, no application uninstall. Recovery paths are the native trash / archive tars / migrate target volumes.
