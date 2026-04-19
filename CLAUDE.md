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

## v0.9 coverage expansion (in progress)

v0.9 expands AI/ML and creative-workflow coverage and sharpens the `app_cache` source_label granularity without changing the L1-L4 risk model, the redaction rules, or any Stage 4–5 confirmation bar. Milestone M1 (references + SKILL.md changes plus one defensive `_BLOCKED_PATTERNS` regex in `scripts/safe_delete.py`; no `scripts/scan_projects.py` changes) lands first:

- **Tier E gains five rows** (all `pkg_cache`, dir-probe in Stage 2): Conda / Mamba / Miniforge envs (per non-`base` env across seven macOS install layouts including miniforge / mambaforge on Apple Silicon, L2 `trash`, `mode_hit_tags=["deep"]`; scope stops at `~/...` to avoid system `/opt/miniconda3/envs`), Playwright (macOS Caches + XDG fallback + driver-binaries, L1 `delete`), Puppeteer (L1 `delete`), OpenAI Whisper (L2 `trash`; Faster-Whisper is explicitly redirected to the HuggingFace row), Weights & Biases global cache (`~/.wandb` + XDG `~/.cache/wandb`, L2 `trash`). `source_label` table grows by five labels (`"Conda environment"` / `"Playwright browsers"` / `"Puppeteer browsers"` / `"Whisper model cache"` / `"Weights & Biases cache"`).
- **HuggingFace split** (v0.8's merged L3 exception was too conservative for models): `~/.cache/huggingface/hub/**` drops to **L2** `trash` — most snapshots are under 1 GB and `from_pretrained()` will refetch reliably; `~/.cache/huggingface/datasets/**` stays **L3** `defer` because a single dataset can exceed tens of GB and redownload costs hours.
- **Creative-app source_label refinement.** `category-rules.md` §4 gains a refinement table mapping Adobe Media Cache / Peak Files / Final Cut Pro / Logic Pro paths to specific `source_label` values. GarageBand's downloadable instrument libraries are deliberately excluded — they are user-initiated content downloads, not regenerable cache. Risk grading is unchanged (L2 `trash` via the Tier C-adjacent override); only the UI label becomes specific so the report names the actual workflow rather than `"System caches"`.
- **Adobe Auto-Save blacklist** (defence in depth). The generic `Adobe/**` sweep must never descend into `Auto-Save/` — those paths hold unsaved Premiere / After Effects / Photoshop project files, i.e. user work in progress. `cleanup-scope.md` blacklist gains an explicit entry, the cross-reference note mentions the new `_BLOCKED_PATTERNS` regex (`/Adobe/[^/]+/Auto-Save(/|$)`) in `safe_delete.py`, and `tests/test_safe_delete.py` grows two cases: positive (six Adobe products, root + nested depth) and end-to-end via dispatch (unsaved `.prproj` survives the attempted delete). Legitimate Media Cache / Peak Files paths remain reachable — the negative assertions guard the refinement's reclaim.

Cross-run history (`history.json`) stays format-compatible: new source_labels are just new tags. The M2 (Xcode DeviceSupport active-OS detection, `scan_projects.py` learning a `nested_cache` subtype for `.dvc/cache`, and version_pins emission for pyenv / nvm) and M3 (`ollama:<name>:<tag>` semantic dispatcher with blob refcounting) milestones land in follow-up commits and are rolled up into a single v0.9 ship PR alongside the README translations.

## Known non-goals (v0.1)

See `plan` history and `SKILL.md`. Summary: no undo stack, no cron, no cloud sync, no SIP-region touches, no application uninstall. Recovery paths are the native trash / archive tars / migrate target volumes.
