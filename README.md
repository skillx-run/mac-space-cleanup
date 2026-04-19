# mac-space-cleanup · macOS cleanup skill

**English** · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md) · [العربية](README.ar.md) · [Deutsch](README.de.md)

A **skill** that cleans up your Mac's disk space — cautious, honest, multi-stage.

> The skill instructs the agent through a seven-stage cleanup (mode → probe → scan → classify → confirm → report → open) with **L1–L4 risk grading**, **honest reclaim accounting** (split into `freed_now` / `pending_in_trash` / `archived`), and **multiple safety backstops** (a deterministic blocklist in code, a redaction reviewer sub-agent, and a post-render validator). Zero pip dependencies — pure macOS commands plus Python stdlib.

---

## Demo

The report is **localized** to whichever language you triggered the skill with — one locale per run, no runtime toggle. Trigger in English → English report; in Chinese → Chinese report; in Japanese, Spanish, French, etc. → that language. Below: first-screen impression (EN left, ZH right, both from separate runs), followed by links to the full-page captures.

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

Any agent harness that loads skills can use this. The snippet below uses the `~/.claude/skills/` convention; adapt the target path to your harness's skills directory.

```bash
git clone git@github.com:skillx-run/mac-space-cleanup.git
mkdir -p ~/.claude/skills
ln -s "$(pwd)/mac-space-cleanup" ~/.claude/skills/mac-space-cleanup
```

Reload your harness so the skill list picks up the new entry (in most harnesses: open a new session).

### Recommended optional dependency

```bash
brew install trash
```

`safe_delete.py` will fall back to `mv` into `~/.Trash` (with a `-<timestamp>` suffix) if the `trash` CLI is missing — works, but the suffix looks odd in Finder. The skill itself nudges you about this on first run.

---

## Use

In your agent conversation, say something like:

| You say… | Skill picks |
| --- | --- |
| "quick clean", "马上腾点空间", "先清一波" | `quick` mode (auto-cleans low-risk items, ~30s) |
| "deep clean", "深度清理", "找大头", "分析空间" | `deep` mode (full audit, asks per-item for risky stuff, ~2–5 min) |
| "clean my Mac", "Mac 空间满了" (ambiguous) | Skill asks you to choose, with time estimates |

To preview without touching the filesystem, add `--dry-run` to your message:

> "深度清理一下我的 Mac，但请用 --dry-run 模式不真的删任何文件"

The report will visibly say `DRY-RUN — no files touched` at the top (localized into whatever language you triggered in) and prefix every number with the target-language equivalent of `would be`.

### Report language

The HTML report is **single-locale per run**, produced in whatever language you triggered the skill with. The agent detects your conversation language from the triggering message, writes its value (a BCP-47 subtag like `en`, `zh`, `ja`, `es`, `ar`) to the workdir, then writes every natural-language node — hero caption, action reasons, observations, source_label renderings, dry-run prose — directly in that language. Static labels (section titles, button text, column headers) ship with English baselines in the template; for non-English runs the agent translates them once into an embedded dictionary that hydrates on page load. No runtime toggle, no bilingual DOM — the conversation language wins.

Right-to-left scripts (Arabic, Hebrew, Persian) get `<html dir="rtl">`; basic direction flipping works, fine-tuned RTL CSS is a known limitation.

---

## What it touches (and never touches)

**Cleans** (with risk grading per `references/category-rules.md`):

- Developer caches: Xcode DerivedData, Docker build cache, Go build cache, Gradle cache, ccache, sccache.
- Package manager caches: Homebrew, npm, pnpm, yarn, pip, uv, Cargo, CocoaPods, RubyGems, Bundler, Composer, Poetry, Dart pub.
- iOS/watchOS/tvOS simulator runtimes (via `xcrun simctl delete`, **never `rm -rf`**).
- App caches under `~/Library/Caches/*`, saved application state, the Trash itself.
- Logs, crash reports.
- Old installers in `~/Downloads` (`.dmg / .pkg / .xip / .iso` older than 30 days).
- Time Machine local snapshots (via `tmutil deletelocalsnapshots`).
- **Project build artifacts** (deep mode only, scanned via `scripts/scan_projects.py` for any directory with a `.git` root):
  - L1 delete: `node_modules`, `target`, `build`, `dist`, `out`, `.next`, `.nuxt`, `.svelte-kit`, `.turbo`, `.parcel-cache`, `__pycache__`, `.pytest_cache`, `.tox`, `.mypy_cache`, `.ruff_cache`, `.dart_tool`, `.nyc_output`, `_build` (Elixir projects only), `Pods`, `vendor` (Go projects only).
  - L2 trash: `.venv`, `venv`, `env` (Python venvs — wheel pins may not reproduce, hence the recovery window); `coverage` (test-coverage reports, gated by `package.json` or a Python marker).
  - System / package-manager directories (`~/Library`, `~/.cache`, `~/.npm`, `~/.cargo`, `~/.cocoapods`, `~/.gradle`, `~/.m2`, `~/.gem`, `~/.bundle`, `~/.composer`, `~/.pub-cache`, `~/.local`, `~/.rustup`, `~/.pnpm-store`, `~/.Trash`) are pruned from project discovery.
- **Deep mode also surfaces `~`-wide directories ≥ 2 GiB that no other rule matched** (L3 defer, `source_label="Unclassified large directory"`) so genuinely orphan disk hogs become visible for manual review.

**Hard backstop — refuses regardless of what `confirmed.json` says** (see `scripts/safe_delete.py` `_BLOCKED_PATTERNS`):

- `.git`, `.ssh`, `.gnupg` directories.
- `~/Library/Keychains`, `~/Library/Mail`, `~/Library/Messages`, `~/Library/Mobile Documents` (iCloud Drive).
- Photos Library, Apple Music library.
- `.env*` files, SSH key files (`id_rsa`, `id_ed25519`, …).

The agent itself reads `references/cleanup-scope.md` for the user-facing whitelist/blacklist — the blocklist above is the runtime-enforced subset.

---

## Architecture (one paragraph)

`SKILL.md` is the workflow contract — agent does the judgement (mode pick, classification, conversation, HTML rendering). Two small Python scripts do the things agent shouldn't: `scripts/safe_delete.py` is the **only** path through which fs writes happen (six dispatched actions: delete / trash / archive / migrate / defer / skip; idempotent; per-item error isolation; append-only `actions.jsonl`); `scripts/collect_sizes.py` runs `du -sk` in parallel with per-path 30s timeout and structured JSON output. Three reference docs (`references/`) are the agent's knowledge base. Three asset templates (`assets/`) are the report skeleton the agent fills in. Two reviewer/validator layers in Stage 6 catch privacy leaks before the user sees the report. Workdir per run lives at `~/.cache/mac-space-cleanup/run-XXXXXX/`.

---

## Honesty contract

Every disk-cleanup tool inflates its "freed N GB" number by counting what it pushed to the Trash. macOS doesn't free that disk until you empty `~/.Trash`. This skill splits the metric:

- `freed_now_bytes` — really off the disk (delete + migrate to another volume).
- `pending_in_trash_bytes` — sitting in `~/.Trash`; surfaces a one-line `osascript` to empty it.
- `archived_source_bytes` / `archived_count` — bytes wrapped into a tar in the workdir.
- `reclaimed_bytes` — back-compat alias = `freed_now + pending_in_trash`. The share text and the report headline use `freed_now_bytes`, not this.

---

## Project layout

```
mac-space-cleanup/
├── SKILL.md                      # main agent workflow (seven stages)
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
│   ├── report-template.html      # six-region HTML skeleton with paired markers
│   ├── report.css
│   └── share-card-template.svg   # 1200×630 X-share card
├── tests/                        # pure-stdlib unittest suite
├── CHANGELOG.md
├── CLAUDE.md                     # contributor invariants
└── .github/workflows/ci.yml      # macos-latest: tests + smoke + dry-e2e
```

---

## Limitations & non-goals (v0.9.4)

- **No undo stack.** Recovery paths are the native Trash, the workdir's `archive/` tars, and the migrate target volume.
- **No cron / no background runs.** Every run is user-triggered.
- **No cloud / no telemetry.** Workdir stays local.
- **No SIP-protected paths**, no `/Applications/*.app` uninstall.
- **Project root identification uses `.git` only.** Bare git checkouts are recognised; project workspaces without a `.git` directory are not. Nested git submodules are deduplicated (do not appear as separate projects).
- **Project artifact discovery does not respect `.gitignore`** — scans for fixed conventional subdirectory names (`node_modules`, `target`, …). May surface a directory ignored by git, may miss a directory the project creates outside convention.
- **Single-machine validation.** Built and tested on macOS 25.x / 26.x with a developer toolchain. Patterns not yet validated across Apple Silicon vs Intel, nor across older macOS versions.

---

## Development

```bash
python3 -m unittest discover -s tests -v
./scripts/smoke.sh                          # real-fs sanity
./scripts/dry-e2e.sh                        # non-LLM end-to-end
```

CI runs all three on every push / PR via `.github/workflows/ci.yml` on `macos-latest`.

See `CLAUDE.md` for non-negotiable invariants (no direct fs writes from the agent, redaction is mandatory, etc.) and `CHANGELOG.md` for release notes.

---

## License

Apache-2.0 (see `LICENSE` and `NOTICE`).

## Credits

Designed and built by [@heyiamlin](https://x.com/heyiamlin). If the skill saved you space, share with the `#macspaceclean` hashtag.
