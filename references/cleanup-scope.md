# Cleanup Scope

This document defines **where the agent may look** (whitelist) and **where the agent must never touch** (blacklist) during scanning and cleanup. Read this before Stage 3 (Scan).

## Whitelist — safe to scan

### Tier A · System & user temporary data (always scan)

| Path | Notes | Default category |
| --- | --- | --- |
| `~/.Trash` | User trash. | `app_cache` |
| `~/Library/Caches` | User application caches. | `app_cache` |
| `~/Library/Logs` | User-facing logs. | `logs` |
| `/private/var/log` | System logs (read-only probe; do not clean unless L1 rule matches). | `logs` |
| `~/Library/Application Support/CrashReporter` | Crash dumps. | `logs` |
| `~/Library/Saved Application State` | Per-app saved UI state (often large, safe to trash). | `app_cache` |

### Tier B · Time Machine local snapshots

| Entry point | Notes | Default category |
| --- | --- | --- |
| `tmutil listlocalsnapshots /` | Enumerate local APFS snapshots. Each entry becomes an item with `path="snapshot:<name>"`. | `system_snapshots` |

### Tier C · Browser & messaging caches (probe, trash only)

| Path | Notes |
| --- | --- |
| `~/Library/Caches/com.apple.Safari` | Safari cache. |
| `~/Library/Caches/Google/Chrome` | Chrome cache. |
| `~/Library/Caches/Firefox` | Firefox cache. |
| `~/Library/Containers/com.tencent.xinWeChat/Data/Library/Caches` | WeChat media cache (if present). |
| `~/Library/Containers/com.hnc.Discord/Data/Library/Caches` | Discord cache (if present). |

Only touch **caches** subtrees. Never touch profile databases, cookies, or history files.

### Tier D · User download & archive staging

| Path | Notes | Default category |
| --- | --- | --- |
| `~/Downloads` | Scan for large `.dmg / .pkg / .xip / .zip / .tar.gz / .iso` older than 30 days. | `downloads` |
| `~/Library/Application Support/MobileSync/Backup` | iOS device backups. Only surface entries older than 180 days. | `large_media` |

### Tier E · Developer ecosystem (scan only when tool detected)

Presence is probed in Stage 2 via `which -a`. Skip the row silently if the tool is missing.

| Tool detected | Entry point / path | Default category |
| --- | --- | --- |
| `xcrun simctl` | `~/Library/Developer/Xcode/DerivedData` | `dev_cache` |
| `xcrun simctl` | `~/Library/Developer/Xcode/Archives` | `dev_cache` |
| `xcrun simctl` | `~/Library/Developer/CoreSimulator/Devices` | `sim_runtime` |
| `xcrun simctl` | `xcrun simctl delete unavailable` (semantic entry) | `sim_runtime` |
| `docker` | `docker system df` output (images / containers / volumes / build cache) | `dev_cache` |
| `brew` | `brew --cache` directory | `pkg_cache` |
| `npm` | `npm config get cache` directory | `pkg_cache` |
| `pnpm` | `pnpm store path` directory | `pkg_cache` |
| `yarn` | `~/Library/Caches/Yarn` | `pkg_cache` |
| `pip` | `pip cache dir` output | `pkg_cache` |
| `uv` | `uv cache dir` output | `pkg_cache` |
| `cargo` | `~/.cargo/registry/cache`, `~/.cargo/registry/src` | `pkg_cache` |
| `go` | `~/Library/Caches/go-build` | `pkg_cache` |
| `gradle` | `~/.gradle/caches` | `pkg_cache` |
| `mvn` / `~/.m2` present | `~/.m2/repository` (surface size only, do not auto-clean) | `pkg_cache` |
| CocoaPods (`~/.cocoapods` present) | `~/.cocoapods/repos`, `~/Library/Caches/CocoaPods` | `pkg_cache` |

## Blacklist — never touch

These directories are off-limits regardless of size or age. If a scan result somehow points into one of these, classify as L4 and record-only.

> **Cross-reference**: a subset of these (`.git`, `.ssh`, `.gnupg`, `Library/Keychains`, `Library/Mail`, `Library/Messages`, `Library/Mobile Documents`, `Photos Library`, `Music/Music`, `.env*`, SSH key files) is also enforced **at runtime** by `scripts/safe_delete.py`'s `_BLOCKED_PATTERNS` regex set. The agent reads this document; the script enforces a hard backstop. Keep them in sync — when adding/removing entries from one, update the other.

### Hard forbid (SIP or system-critical)

- `/System/**`
- `/Library/**` (top-level system library; not `~/Library`)
- `/bin`, `/sbin`, `/usr/bin`, `/usr/sbin`, `/usr/libexec`, `/usr/local/bin`
- `/private/etc`, `/private/var/db`, `/private/var/root`
- `/Applications/**` (applications themselves; their caches live under `~/Library/Caches`)
- `/opt/homebrew/**` except `$(brew --cache)`

### User-critical (never auto-clean)

- `~/Library/Mail` / `~/Library/Mail Downloads`
- `~/Library/Keychains`
- `~/Library/Application Support/AddressBook`
- `~/Library/Calendars`
- `~/Library/Messages`
- `~/Library/Safari` (bookmarks, history — different from `~/Library/Caches/com.apple.Safari`)
- `~/Library/Mobile Documents` (iCloud Drive mirror)
- `~/Dropbox`, `~/Google Drive`, `~/OneDrive` and any sync-client local copy
- `~/Pictures/Photos Library.photoslibrary`
- `~/Music/Music` (Apple Music library)
- Any path under a user project workspace (root has `.git`) **except** the conventional artifact subdirectories listed in §"Project artifacts allowlist" below. Project source files, configs, and `.git` itself remain off-limits.
- Virtual machine images: `*.vmdk`, `*.qcow2`, `*.vdi`, `~/Parallels`, `~/VirtualBox VMs`, `~/Library/Containers/com.docker.docker/Data/vms` (surface size only, record as L3 defer)
- Database data directories: `~/Library/Application Support/Postgres*`, `~/Library/Application Support/MongoDB`, `/usr/local/var/mysql`, `/opt/homebrew/var/postgres*`

## Project artifacts allowlist (v0.4+)

Inside any directory recognised as a project root (has `.git`), the following conventional subdirectories ARE allowed to be cleaned. Everything else inside the project — source files, configs, `.git` itself — remains off-limits.

Discovery is via `scripts/scan_projects.py`, never via free-form `find` on `~/Downloads` or similar. The agent reads `references/category-rules.md` §10 for risk grading.

**Deletable build / install outputs** (default L1 delete via `category=project_artifacts`, kind=`deletable`):

- `node_modules` (Node)
- `target` (Rust / Java / Scala)
- `build`, `dist`, `out` (generic)
- `.next`, `.nuxt`, `.svelte-kit`, `.turbo`, `.parcel-cache` (web framework caches)
- `__pycache__`, `.pytest_cache`, `.tox` (Python tooling caches)
- `Pods` (CocoaPods)
- `vendor` (Go modules vendored deps; **only when project root has `go.mod`** — agent must verify via `markers_found`)

**Virtual environments** (default L2 trash via `category=project_artifacts`, kind=`venv`):

- `.venv`, `venv`, `env` (Python)
  - **Heads-up for `env`**: this name is too generic; agent must skip if project root has no Python marker (`pyproject.toml` / `requirements.txt` / `setup.py`) in `markers_found`.

Project root identification: presence of a `.git` directory. Other markers (`package.json`, `Cargo.toml`, `pyproject.toml`, `go.mod`, etc.) are **not** treated as project roots in v0.4 — `.git` covers ~all real project workspaces and avoids double-counting nested submodules. Bare git checkouts without any language marker are still recognised; markers only inform per-subtype decisions.

System / package-manager directories under `~/Library`, `~/.cache`, `~/.npm`, `~/.cargo`, `~/.cocoapods`, `~/.gradle`, `~/.m2`, `~/.gem`, `~/.bundle`, `~/.local`, `~/.rustup`, `~/.pnpm-store`, `~/.Trash` are pruned from project discovery (they may contain cloned repos with `.git` that are not user projects).

## Scope-probe contract

When enumerating candidates:

1. Expand `~` to `$HOME` before passing to `scripts/collect_sizes.py`.
2. For each whitelist entry, check existence first (`os.path.exists`); skip silently if missing.
3. For each blacklist entry, never write it into `paths.json`. If a user explicitly asks to clean a blacklisted path, refuse and cite this document.
4. Tier E rows only appear in `paths.json` when Stage 2 confirmed the tool is installed.
