# mac-space-cleanup skill

**English** · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md) · [العربية](README.ar.md) · [Deutsch](README.de.md)

A skill that cleans up your Mac's disk space.

> Six-stage workflow: mode selection, environment probe, scan, classification, confirmation, report. Every candidate is graded L1-L4; all filesystem writes route through `safe_delete.py`, which carries an internal blocklist and pairs with a privacy-redaction reviewer sub-agent and a post-render validator, forming three layers of guardrail. Bytes awaiting emptying in Trash are counted separately and not included in the "freed" total. Zero pip dependencies — pure macOS commands and the Python standard library.

---

## Why this skill

Rule-based cleaners (CleanMyMac, OnyX) only handle entries their rules can name: whether a given `node_modules` is still in use, which directories under `~/Library/Caches` correspond to active user preferences versus leftover residue — these are beyond rule-based judgment, so such tools skip them conservatively and leave substantial recoverable space behind.

Delegating cleanup to an agent directly ("Claude, clean up my Mac") can cover those gray zones, but without hard boundaries a single misjudgment may reach `.git` / `.env` / Keychains.

This skill establishes the safety boundary first: `safe_delete.py`'s blocklist, the privacy reviewer, and the post-render validator form three guardrails that refuse the paths above at runtime. Within that envelope, judgment is delegated fully to the agent, covering the gray zones that rule-based tools cannot reach.

---

<!-- skillx:begin:setup-skillx -->
## Try it with skillx

[![Run with skillx](https://img.shields.io/badge/Run%20with-skillx-F97316)](https://skillx.run)

Run this skill without installing anything:

```bash
skillx run --skip-scan --auto https://github.com/skillx-run/mac-space-cleanup "Clean up my Mac."
```

To preview rather than actually execute, add `--dry-run` to the trigger. The skill still runs all six stages, but `safe_delete.py` writes nothing to the filesystem (only the workdir's `actions.jsonl`).

```bash
skillx run --skip-scan --auto https://github.com/skillx-run/mac-space-cleanup "Clean up my Mac with --dry-run, preview only."
```

Powered by [skillx](https://skillx.run) — one command to fetch, scan, inject, and run any agent skill.
<!-- skillx:end:setup-skillx -->

---

## Demo

Report language is determined by the conversation language used to trigger the skill — one locale per run. Below: first-screen impression, English on the left, Chinese on the right, from separate runs.

<table>
<tr>
<td width="50%"><img src="assets/mac-space-cleanup.en.png" alt="mac-space-cleanup report, first screen, English" /></td>
<td width="50%"><img src="assets/mac-space-cleanup.zh.png" alt="mac-space-cleanup 报告首屏，中文" /></td>
</tr>
</table>

Full report (Impact Summary · Breakdown · Detailed Log · Observations · Run Details · L1–L4 risk distribution):
[English full page](assets/mac-space-cleanup.full.en.png) · [中文整页](assets/mac-space-cleanup.full.zh.png)

---

## Install

Persistent installation goes through skillx. If you don't have the skillx CLI yet:

```bash
curl -fsSL https://skillx.run/install.sh | sh
```

Then install this skill into the skills directory of any agent harness skillx recognizes (Claude Code's `~/.claude/skills/`, etc.):

```bash
skillx install https://github.com/skillx-run/mac-space-cleanup
```

Start a new agent session to refresh the skill list. To update or remove later: `skillx update mac-space-cleanup` / `skillx uninstall mac-space-cleanup`.

Installing `trash` alongside is recommended (`brew install trash`). Without it, `safe_delete.py` falls back to `mv` into `~/.Trash`, and the moved filenames carry a timestamp suffix.

---

## Use

In your agent conversation, use a trigger phrase such as:

| Trigger | Skill picks |
| --- | --- |
| "quick clean", "马上腾点空间", "先清一波" | `quick` mode (auto-cleans low-risk items, ~30s) |
| "deep clean", "深度清理", "找大头", "分析空间" | `deep` mode (full audit, per-item confirmation for risky items, ~2–5 min) |
| "clean my Mac", "Mac 空间满了" (ambiguous) | Skill asks you to choose, with time estimates |

To preview without touching the filesystem, add `--dry-run` to your message:

> "Clean up my Mac with --dry-run, preview only."

The report marks dry-run state at the top and prefixes each figure with a "would" qualifier. RTL languages (Arabic, Hebrew, Persian) receive `<html dir="rtl">` automatically; fine-tuned RTL styling is a known limitation.

---

## Scope

Cleans (risk grades per `references/category-rules.md`):

- Developer caches: Xcode DerivedData, Docker build cache, Go build cache, Gradle cache, ccache, sccache, JetBrains, Flutter SDK, VSCode-family editor caches (Code / Cursor / Windsurf / Zed `blob_store`).
- Package manager caches: Homebrew, npm, pnpm, yarn, pip, uv, Cargo, CocoaPods, RubyGems, Bundler, Composer, Poetry, Dart pub, Bun, Deno, Swift PM, Carthage. Version managers (nvm / fnm / pyenv / rustup) surface non-active per-version entries; active pins are excluded automatically via each project's `.python-version` / `.nvmrc`.
- AI/ML model caches: HuggingFace (`hub/` L2 trash, `datasets/` L3 defer), PyTorch hub, Ollama (L3 defer; deep mode dispatches per-model `ollama:<name>:<tag>` with blob reference counting so layers shared across tags survive the delete of a sibling tag), LM Studio, OpenAI Whisper, Weights & Biases global cache. Conda / Mamba / Miniforge non-`base` envs across seven common macOS install layouts.
- Frontend tooling: Playwright browsers + driver, Puppeteer bundled browsers.
- iOS/watchOS/tvOS simulator runtimes (via `xcrun simctl delete`, not `rm -rf`). iOS `DeviceSupport/<OS>` entries whose major.minor matches a currently paired device or available simulator runtime are automatically downgraded to L3 defer.
- App caches under `~/Library/Caches/*`, saved application state, and the Trash itself. Creative-app caches (Adobe Media Cache / Peak Files, Final Cut Pro, Logic Pro) use specific labels rather than the generic `"System caches"`.
- Logs, crash reports.
- Old installers in `~/Downloads` (`.dmg / .pkg / .xip / .iso` older than 30 days).
- Time Machine local snapshots (via `tmutil deletelocalsnapshots`).
- Project build artifacts (deep mode only; scanned via `scripts/scan_projects.py` for any directory with a `.git` root):
  - L1 delete: `node_modules`, `target`, `build`, `dist`, `out`, `.next`, `.nuxt`, `.svelte-kit`, `.turbo`, `.parcel-cache`, `__pycache__`, `.pytest_cache`, `.tox`, `.mypy_cache`, `.ruff_cache`, `.dart_tool`, `.nyc_output`, `_build` (Elixir projects only), `Pods`, `vendor` (Go projects only).
  - L2 trash: `.venv`, `venv`, `env` (Python venvs — wheel pins may not reproduce, so a recovery window is preserved); `coverage` (test coverage reports, gated by `package.json` or a Python marker); `.dvc/cache` (DVC content-addressed cache, gated by a sibling `.dvc/config` marker; the parent `.dvc/` holds user state and is preserved).
  - System / package-manager directories (`~/Library`, `~/.cache`, `~/.npm`, `~/.cargo`, `~/.cocoapods`, `~/.gradle`, `~/.m2`, `~/.gem`, `~/.bundle`, `~/.composer`, `~/.pub-cache`, `~/.local`, `~/.rustup`, `~/.pnpm-store`, `~/.Trash`) are pruned during project discovery.
- Orphan large-directory scan (deep mode only): directories under `~` ≥ 2 GiB that no other rule matched are marked L3 defer (`source_label="Unclassified large directory"`). Before finalization the agent performs a brief read-only investigation (up to 6 commands per candidate) to refine `category` and `source_label`; the L3 defer grade remains locked regardless of the result.

Hard backstop — refuses regardless of what `confirmed.json` contains; see `_BLOCKED_PATTERNS` in `scripts/safe_delete.py`:

- `.git`, `.ssh`, `.gnupg` directories.
- `~/Library/Keychains`, `~/Library/Mail`, `~/Library/Messages`, `~/Library/Mobile Documents` (iCloud Drive).
- Photos Library, Apple Music library.
- `.env*` files, SSH key files (`id_rsa`, `id_ed25519`, …).
- VSCode-family editor state: `{Code, Cursor, Windsurf}/{User, Backups, History}` (unsaved edits, git-stash equivalents, local edit history).
- Adobe creative-app `Auto-Save` folders — unsaved Premiere / After Effects / Photoshop project files.

---

## Architecture

`SKILL.md` is the agent's workflow contract: mode selection, classification, conversation, and HTML rendering are performed by the agent. Two Python scripts handle responsibilities unsuited to the agent — `scripts/safe_delete.py` is the sole entry point for filesystem writes, providing six dispatched actions, idempotency, and per-item error isolation; `scripts/collect_sizes.py` runs `du -sk` in parallel using the standard library. `references/` is the agent's knowledge base, `assets/` holds report templates. Stage 6 runs a two-layer reviewer / validator that intercepts privacy leaks before the user sees the report. The per-run working directory lives at `~/.cache/mac-space-cleanup/run-XXXXXX/`.

---

## Project layout

```
mac-space-cleanup/
├── SKILL.md                      # agent workflow (six stages)
├── scripts/
│   ├── safe_delete.py            # six-action dispatcher + blocklist backstop
│   ├── collect_sizes.py          # parallel du -sk
│   ├── scan_projects.py          # find .git-rooted projects + enumerate cleanable artifacts
│   ├── aggregate_history.py      # cross-run confidence aggregator (Stage 5 HISTORY_BY_LABEL) + run-* GC
│   ├── validate_report.py        # post-render check (regions / placeholders / leaks / dry-run marking)
│   ├── smoke.sh                  # real-fs smoke
│   └── dry-e2e.sh                # non-LLM end-to-end harness
├── references/
│   ├── cleanup-scope.md          # whitelist / blacklist (with cross-ref to safe_delete blocklist)
│   ├── safety-policy.md          # L1-L4 grading + redaction + degradation
│   ├── category-rules.md         # 10 categories with patterns + risk_level + action
│   └── reviewer-prompts.md       # prompt template for the redaction sub-agent
├── assets/
│   ├── report-template.html      # HTML template with paired region markers
│   ├── report.css
│   └── share-card-template.svg   # 1200×630 X-share card
├── tests/                        # pure-stdlib unittest suite
├── CHANGELOG.md
├── CLAUDE.md                     # contributor invariants
└── .github/workflows/ci.yml      # macos-latest: tests + smoke + dry-e2e
```

---

## Limitations

- **No undo stack.** Recovery paths are the native Trash, the workdir's `archive/` tars, and the migrate target volume.
- **No cron, no background runs.** Every run is user-triggered.
- **No cloud, no telemetry.** The workdir stays local.
- **No SIP-protected paths**, no `/Applications/*.app` uninstall.
- **Project root identification uses `.git` only.** Standard git checkouts are recognized; workspaces without a `.git` directory are not. Nested git submodules are deduplicated and do not appear as separate projects.
- **Project artifact discovery does not honor `.gitignore`** — scans are keyed on fixed conventional subdirectory names (`node_modules`, `target`, …). May include directories ignored by git, may miss directories a project creates outside convention.
- **Single-machine validation.** Built and tested on macOS 25.x / 26.x with a developer toolchain. Not yet cross-validated across Apple Silicon vs Intel, nor across earlier macOS versions.

---

## Development

```bash
python3 -m unittest discover -s tests -v
./scripts/smoke.sh                          # real-fs sanity
./scripts/dry-e2e.sh                        # non-LLM end-to-end
```

CI runs all three on every push / PR via `.github/workflows/ci.yml` on `macos-latest`.

Non-negotiable invariants (the agent never writes to the filesystem directly, privacy redaction is mandatory, etc.) are documented in `CLAUDE.md`; release notes are in `CHANGELOG.md`.

---

## License

Apache-2.0 (see `LICENSE` and `NOTICE`).

## Credits

Designed and built by [@heyiamlin](https://x.com/heyiamlin). If the skill saved you space, share with the `#macspaceclean` hashtag.
