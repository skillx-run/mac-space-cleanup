# mac-space-cleanup — Contributor Notes

These notes apply to anyone (human or agent) working on this skill. For the user-facing workflow, read `SKILL.md`; for the safety model, read `references/safety-policy.md`.

## Skill positioning

This is an **agent-first skill**. `SKILL.md` is the main deliverable — it instructs the agent through a six-stage cleanup workflow. Python scripts exist only to do what the agent cannot do safely or efficiently:

- `scripts/safe_delete.py` — unified controlled write path (delete / trash / archive / migrate / defer / skip) with actions.jsonl audit trail.
- `scripts/collect_sizes.py` — parallel `du` with per-path timeout and error isolation.
- `scripts/scan_projects.py` — project-artifact discovery (node_modules, target, .venv…) scoped to `.git`-marked roots.
- `scripts/aggregate_history.py` — cross-run confidence aggregator feeding Stage 5 `HISTORY_BY_LABEL`; also GCs old `run-*` directories.
- `scripts/validate_report.py` — deterministic second-line redaction check on the rendered report.

Do not re-introduce `scan_space.py`, `classify_items.py`, `build_report.py`, or `share_text.py` — those responsibilities belong to the agent (Bash probes, rule-based judgement, HTML/share-text composition).

## Non-negotiable invariants

1. **Agent never writes the filesystem for cleanup purposes.** Every `delete / trash / archive / migrate / defer` against **user-owned paths** must route through `scripts/safe_delete.py`. The only direct agent writes are JSON/HTML files under `$WORKDIR`. Scripts under `scripts/` MAY manage their own workdir-family state directly — see `references/safety-policy.md` §"Operating invariants" #1 + #3 for the cross-run GC carve-out in `aggregate_history.py`.
2. **Redaction is absolute.** Anything that reaches `report.html`, `share-card.svg`, or share text must use `source_label` + `category` only. No paths, basenames, usernames, project names, or company names. See `references/safety-policy.md` §"Privacy redaction rules".
3. **Workdir is per-run**: `~/.cache/mac-space-cleanup/run-XXXXXX` created by `mktemp -d`. Never reuse across runs.
4. **Templates in `assets/` are immutable at runtime.** Agent must `cp` them into `$WORKDIR` before editing.
5. **`actions.jsonl` is append-only and authoritative *within a single run*.** Safe_delete re-runs against the same `$WORKDIR` are idempotent: already-gone paths become `action=skip, status=success, reason="already gone"`. Cross-run preservation is best-effort — `aggregate_history.py` GCs old `run-*` dirs per its `--keep` window. See `references/safety-policy.md` §"Operating invariants" #3.
6. **History-driven UI decisions never cross risk-level or mode boundaries.** `scripts/aggregate_history.py` produces a per-run `history.json` that Stage 5 may consult to collapse per-item prompts into batch prompts. It MUST NOT be used to auto-execute a tag that would otherwise prompt, to up-tier a Quick-mode scan, or to influence Stage 4 grading. See `references/safety-policy.md` §"History-driven UI adjustments" for the authoritative rules.

## Editing the reference docs

`references/*.md` are the agent's knowledge base — updates there change agent behaviour even without touching code. When you edit:

- `cleanup-scope.md`: if you add a new whitelist path, make sure it is not inside any `blacklist` pattern. If you add a Tier E row, decide whether it uses a **CLI probe** (goes on `which -a` in SKILL.md Stage 2) or a **directory probe** (goes on `ls -d` in SKILL.md Stage 2) — and extend the matching line there in the same commit. A Tier E row with no Stage 2 gate will silently never be scanned.
- `safety-policy.md`: the risk-level semantics and the redaction forbid-list are load-bearing. Changes here must be reflected in commit messages or CHANGELOG so agents / reviewers notice the behaviour shift.
- `category-rules.md`: new categories require updating the `category` enum in `scripts/safe_delete.py` and `SKILL.md` "Quick reference" section. Existing tests do not enumerate categories, but new L3 defaults should be cross-checked against `safety-policy.md`.

## Report templates

The report is a single long page — `assets/report-template.html` — that carries eight paired-marker regions: `hero`, `share`, `impact`, `nextstep`, `distribution`, `actions`, `observations`, `runmeta`. CSS lives in `assets/report.css`; `assets/share-card-template.svg` is filled as a workdir artifact but is not embedded in the report.

When you add, remove, or rename a region marker:

- Update `REGIONS` in `scripts/validate_report.py`.
- Update `_PLACEHOLDER_MARKERS` in the same file if the region's `data-placeholder="..."` value changes.
- Update the Stage 6 step 4 region list in `SKILL.md` — the agent fills from those instructions, a silent drift means regions get left as placeholders.
- Update the fixture helper in `tests/test_validate_report.py` if a new region should participate in a happy-path test.

All four must move in the same commit — a region in the template that isn't in `REGIONS` is a silent leak risk (unfilled placeholder never fails validation), and vice-versa a region in `REGIONS` that isn't in the template will always flag missing.

## Testing

All tests are pure-stdlib `unittest`, no external dependencies.

```bash
python3 -m unittest discover -s tests -v
```

The test suite covers only the scripts (76 tests total as of the v0.5 report redesign). Agent behaviour (Stages 1–6) is verified end-to-end through manual dry-runs, not unit tests — rule interpretation is the agent's responsibility and is not mechanically testable without LLM-in-loop harnesses.

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

## Known non-goals (v0.1)

See `plan` history and `SKILL.md`. Summary: no undo stack, no cron, no cloud sync, no SIP-region touches, no application uninstall. Recovery paths are the native trash / archive tars / migrate target volumes.
