# mac-space-clean

An **agent-driven** macOS disk space cleanup workflow, packaged as a Claude Code Skill. Built by [@heyiamlin](https://x.com/heyiamlin).

> The skill instructs the agent through a six-stage cleanup (mode → probe → scan → classify → confirm → report) with **L1–L4 risk grading**, **honest reclaim accounting** (split into `freed_now` / `pending_in_trash` / `archived`), and **multiple safety backstops** (a deterministic blocklist in code, a redaction reviewer sub-agent, and a post-render validator). Zero pip dependencies — pure macOS commands plus Python stdlib.

---

## Demo

> _Sample report and share-card screenshots will be added here once a real end-to-end run is captured._

```
docs/sample-report.png       (placeholder — add screenshot here)
docs/sample-share-card.png   (placeholder — add screenshot here)
```

---

## Install

```bash
git clone git@github.com:skillx-run/mac-space-clean.git
mkdir -p ~/.claude/skills
ln -s "$(pwd)/mac-space-clean" ~/.claude/skills/mac-space-clean
```

Open a **new** Claude Code session so the skill list reloads.

### Recommended optional dependency

```bash
brew install trash
```

`safe_delete.py` will fall back to `mv` into `~/.Trash` (with a `-<timestamp>` suffix) if the `trash` CLI is missing — works, but the suffix looks odd in Finder. The skill itself nudges you about this on first run.

---

## Use

In any Claude Code session, say something like:

| You say… | Skill picks |
| --- | --- |
| "quick clean", "马上腾点空间", "先清一波" | `quick` mode (auto-cleans low-risk items, ~30s) |
| "deep clean", "深度清理", "找大头", "分析空间" | `deep` mode (full audit, asks per-item for risky stuff, ~2–5 min) |
| "clean my Mac", "Mac 空间满了" (ambiguous) | Skill asks you to choose, with time estimates |

To preview without touching the filesystem, add `--dry-run` to your message:

> "深度清理一下我的 Mac，但请用 --dry-run 模式不真的删任何文件"

The report will visibly say `DRY-RUN — no files touched` at the top and prefix every number with `would be`.

---

## What it touches (and never touches)

**Cleans** (with risk grading per `references/category-rules.md`):

- Developer caches: Xcode DerivedData, Docker build cache, Go build cache, Gradle cache.
- Package manager caches: Homebrew, npm, pnpm, yarn, pip, uv, Cargo, CocoaPods.
- iOS/watchOS/tvOS simulator runtimes (via `xcrun simctl delete`, **never `rm -rf`**).
- App caches under `~/Library/Caches/*`, saved application state, the Trash itself.
- Logs, crash reports.
- Old installers in `~/Downloads` (`.dmg / .pkg / .xip / .iso` older than 30 days).
- Time Machine local snapshots (via `tmutil deletelocalsnapshots`).
- **Project build artifacts** (deep mode only, scanned via `scripts/scan_projects.py` for any directory with a `.git` root):
  - L1 delete: `node_modules`, `target`, `build`, `dist`, `out`, `.next`, `.nuxt`, `.svelte-kit`, `.turbo`, `.parcel-cache`, `__pycache__`, `.pytest_cache`, `.tox`, `Pods`, `vendor` (Go projects only).
  - L2 trash: `.venv`, `venv`, `env` (Python venvs — wheel pins may not reproduce, hence the recovery window).
  - System / package-manager directories (`~/Library`, `~/.cache`, `~/.npm`, `~/.cargo`, `~/.cocoapods`, `~/.gradle`, `~/.m2`, `~/.gem`, `~/.bundle`, `~/.local`, `~/.rustup`, `~/.pnpm-store`, `~/.Trash`) are pruned from project discovery.

**Hard backstop — refuses regardless of what `confirmed.json` says** (see `scripts/safe_delete.py` `_BLOCKED_PATTERNS`):

- `.git`, `.ssh`, `.gnupg` directories.
- `~/Library/Keychains`, `~/Library/Mail`, `~/Library/Messages`, `~/Library/Mobile Documents` (iCloud Drive).
- Photos Library, Apple Music library.
- `.env*` files, SSH key files (`id_rsa`, `id_ed25519`, …).

The agent itself reads `references/cleanup-scope.md` for the user-facing whitelist/blacklist — the blocklist above is the runtime-enforced subset.

---

## Architecture (one paragraph)

`SKILL.md` is the workflow contract — agent does the judgement (mode pick, classification, conversation, HTML rendering). Two small Python scripts do the things agent shouldn't: `scripts/safe_delete.py` is the **only** path through which fs writes happen (six dispatched actions: delete / trash / archive / migrate / defer / skip; idempotent; per-item error isolation; append-only `actions.jsonl`); `scripts/collect_sizes.py` runs `du -sk` in parallel with per-path 30s timeout and structured JSON output. Three reference docs (`references/`) are the agent's knowledge base. Three asset templates (`assets/`) are the report skeleton the agent fills in. Two reviewer/validator layers in Stage 6 catch privacy leaks before the user sees the report. Workdir per run lives at `~/.cache/mac-space-clean/run-XXXXXX/`.

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
mac-space-clean/
├── SKILL.md                      # main agent workflow (six stages)
├── scripts/
│   ├── safe_delete.py            # six-action dispatcher + blocklist backstop
│   ├── collect_sizes.py          # parallel du -sk
│   ├── validate_report.py        # post-render check (regions / placeholders / leaks / dry-run marking)
│   ├── smoke.sh                  # real-fs smoke
│   └── dry-e2e.sh                # non-LLM end-to-end harness
├── references/
│   ├── cleanup-scope.md          # whitelist / blacklist (with cross-ref to safe_delete blocklist)
│   ├── safety-policy.md          # L1-L4 grading + redaction + degradation
│   ├── category-rules.md         # 9 categories with patterns + risk_level + action
│   └── reviewer-prompts.md       # prompt template for the redaction sub-agent
├── assets/
│   ├── report-template.html      # six-region HTML skeleton with paired markers
│   ├── report.css
│   └── share-card-template.svg   # 1200×630 X-share card
├── tests/                        # 40 unit tests (pure stdlib unittest)
├── docs/                         # README screenshots
├── CHANGELOG.md
├── CLAUDE.md                     # contributor invariants
└── .github/workflows/ci.yml      # macos-latest: tests + smoke + dry-e2e
```

---

## Limitations & non-goals (v0.4)

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
python3 -m unittest discover -s tests -v   # 40 tests
./scripts/smoke.sh                          # real-fs sanity
./scripts/dry-e2e.sh                        # non-LLM end-to-end
```

CI runs all three on every push / PR via `.github/workflows/ci.yml` on `macos-latest`.

See `CLAUDE.md` for non-negotiable invariants (no direct fs writes from the agent, redaction is mandatory, etc.) and `CHANGELOG.md` for release notes.

---

## License

MIT (see `LICENSE`).

## Credits

Designed and built by [@heyiamlin](https://x.com/heyiamlin). If the skill saved you space, share with the `#macspaceclean` hashtag.
