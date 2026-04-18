# Changelog

All notable changes to mac-space-cleanup. Newest first.

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
