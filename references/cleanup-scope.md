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
| `~/Library/DiagnosticReports` | Per-user diagnostic reports (.ips / .crash / .diag). | `logs` |
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
| `~/Library/Caches/BraveSoftware` | Brave browser cache (if present). |
| `~/Library/Caches/Microsoft Edge` | Edge cache (if present). |
| `~/Library/Caches/company.thebrowser.Browser` | Arc browser cache (if present). |
| `~/Library/Containers/com.tencent.xinWeChat/Data/Library/Caches` | WeChat media cache (if present). |
| `~/Library/Containers/com.hnc.Discord/Data/Library/Caches` | Discord cache (if present). |
| `~/Library/Containers/com.tinyspeck.slackmacgap/Data/Library/Caches` | Slack cache (if present). |
| `~/Library/Containers/com.microsoft.teams2/Data/Library/Caches` | Microsoft Teams cache (if present). |
| `~/Library/Containers/ru.keepcoder.Telegram/Data/Library/Caches` | Telegram Desktop cache (if present). |
| `~/Library/Containers/com.electron.lark/Data/Library/Caches` | Feishu/Lark cache (if present; also match `com.bytedance.lark`). |
| `~/Library/Application Support/Signal/cache` | Signal desktop cache (non-sandboxed; if present). |
| `~/Library/Group Containers/*/Library/Caches` | Generic Group Container cache sweep — matches shared-cache subtrees for Apple apps + other sandboxed apps. Only descend one level; exclude any container whose identifier contains `Mail`, `Messages`, `CloudKit`, `iCloud` (promote to L4). |
| `~/Library/Containers/*/Data/Library/Application Support/Cache*` | Generic in-Container Application-Support cache sweep (case-insensitive `Cache*` prefix). Same exclusion list as Group Containers. |

Only touch **caches** subtrees. Never touch profile databases, cookies, history files, chat attachments that live outside a `Cache*` subtree, or the app's `Application Support/*.db` stores.

#### Tier C subset — Non-sandboxed editor caches (probe by existence, trash only)

VSCode and its forks (Cursor, Windsurf) plus Zed are **not sandboxed**, so their caches live under `~/Library/Application Support/<editor>/` rather than `~/Library/Caches/`. The generic Tier C sweep does not catch them. Surface each app root if it exists and descend **only** into the precise whitelist subdirs below — these are pure caches that the editor regenerates on next launch. **Never** descend into anything else; the User-critical blacklist guards the dangerous siblings (`User/workspaceStorage`, `Backups`, `History` — see below).

| App root (probe by existence) | Cleanable subdirs (positive whitelist, never glob) | Default category |
| --- | --- | --- |
| `~/Library/Application Support/Code` | `Cache`, `CachedData`, `CachedExtensionVSIXs`, `Crashpad`, `GPUCache`, `Code Cache`, `logs` | `app_cache` |
| `~/Library/Application Support/Cursor` | (same six subdirs as Code) | `app_cache` |
| `~/Library/Application Support/Windsurf` | (same six subdirs as Code) | `app_cache` |
| `~/Library/Application Support/dev.zed.Zed` | `db/0/blob_store`, `logs` | `app_cache` |

`category-rules.md` §4 routes these as L2 `trash` (Tier C semantics: re-populate on next launch but give a recovery window for an active editing session).

### Tier D · User download & archive staging

| Path | Notes | Default category |
| --- | --- | --- |
| `~/Downloads` | Scan for installers older than 30 days (`.dmg / .pkg / .xip / .iso / .appimage / .deb / .rpm / .msi`), generic archives older than 90 days (`.zip / .tar.gz / .tgz / .tar.bz2 / .7z / .rar`, size > 100MB), and pulled-out `.app` bundles older than 90 days (size > 100MB, deep mode only — surface as L3 defer because the user may still want to install). | `downloads` |
| `~/Desktop` | Scan **only** for macOS-auto-named screen artefacts older than 30 days: `Screenshot *.png`, `Screen Shot *.png`, `Screen Recording *.mov`. Do NOT glob for other files — users curate the Desktop. | `downloads` |
| `~/Library/Application Support/MobileSync/Backup` | iOS device backups. Only surface per-device subdirs whose **mtime is older than 180 days** (probe with `find ~/Library/Application\ Support/MobileSync/Backup -mindepth 1 -maxdepth 1 -type d -mtime +180`). | `large_media` |

### Tier E · Developer ecosystem (scan only when tool detected)

Presence is probed in Stage 2. Two probe kinds — agent picks one per row:

- **CLI probe**: `which -a <tool>` returns a non-empty path (e.g. `docker`, `brew`, `pnpm`).
- **Directory probe**: the marker directory exists (e.g. `[ -d ~/.m2 ]`, `[ -d ~/.cocoapods ]`). Used when the tool has no standalone CLI or the CLI is inside the marker dir itself (Android SDK, JetBrains).

Skip the row silently if the probe fails.

| Tool detected | Entry point / path | Default category |
| --- | --- | --- |
| `xcrun simctl` | `~/Library/Developer/Xcode/DerivedData` | `dev_cache` |
| `xcrun simctl` | `~/Library/Developer/Xcode/Archives` | `dev_cache` |
| `xcrun simctl` | `~/Library/Developer/CoreSimulator/Devices` | `sim_runtime` |
| `xcrun simctl` | `xcrun simctl delete unavailable` (semantic entry) | `sim_runtime` |
| `xcrun simctl` | `~/Library/Developer/Xcode/iOS DeviceSupport` (entries older than matching Xcode-supported OS — surface all, let user pick) | `dev_cache` |
| `xcrun simctl` | `~/Library/Developer/Xcode/watchOS DeviceSupport` | `dev_cache` |
| `xcrun simctl` | `~/Library/Developer/Xcode/tvOS DeviceSupport` | `dev_cache` |
| `xcrun simctl` | `~/Library/Developer/XCPGDevices`, `~/Library/Developer/XCPGPlaygrounds` (Playground devices and snapshots — used once and rarely revisited) | `dev_cache` |
| `docker` | `docker system df` output (images / containers / volumes / build cache) — surface the four semantic entries `docker:build-cache`, `docker:dangling-images`, `docker:stopped-containers` (each dispatched by `safe_delete.py`); **`docker:unused-volumes` is intentionally excluded** because volumes contain user data | `dev_cache` |
| `brew` | `brew --cache` directory **and** the semantic entry `brew:cleanup-s` (dispatches `brew cleanup -s` to remove old Cellar versions and stale downloads — pinned formulae are preserved automatically by Homebrew) | `pkg_cache` |
| `npm` | `npm config get cache` directory | `pkg_cache` |
| `pnpm` | `pnpm store path` directory | `pkg_cache` |
| `yarn` | `~/Library/Caches/Yarn`, `~/.yarn/berry/cache` (Yarn Berry PnP global cache, only present when `enableGlobalCache: true`) | `pkg_cache` |
| `bun` (CLI probe) | `~/.bun/install/cache`, `~/Library/Caches/com.oven.bun` | `pkg_cache` |
| `deno` (CLI probe) | `~/Library/Caches/deno` (i.e. `$DENO_DIR` default) | `pkg_cache` |
| `pip` | `pip cache dir` output | `pkg_cache` |
| `uv` | `uv cache dir` output | `pkg_cache` |
| `cargo` | `~/.cargo/registry/cache`, `~/.cargo/registry/src` | `pkg_cache` |
| `go` | `~/Library/Caches/go-build` | `pkg_cache` |
| `gradle` | `~/.gradle/caches` | `pkg_cache` |
| `mvn` / `~/.m2` present | `~/.m2/repository` (surface size only, do not auto-clean) | `pkg_cache` |
| CocoaPods (`~/.cocoapods` present, dir probe) | `~/.cocoapods/repos`, `~/Library/Caches/CocoaPods` | `pkg_cache` |
| Swift Package Manager (`~/Library/Caches/org.swift.swiftpm` present, dir probe) | `~/Library/Caches/org.swift.swiftpm`, `~/Library/org.swift.swiftpm/repositories` | `pkg_cache` |
| Carthage (`~/Library/Caches/org.carthage.CarthageKit` present, dir probe) | `~/Library/Caches/org.carthage.CarthageKit` | `pkg_cache` |
| Android SDK (`~/Library/Android/sdk` present, dir probe) | `~/Library/Android/sdk/system-images` (surface **entries older than 180 days**; current API-level images are large but in active use), `~/Library/Android/sdk/.temp`, `~/Library/Android/sdk/emulator/skins` | `pkg_cache` |
| `flutter` (CLI probe) | `~/.flutter`, `~/Library/Caches/Flutter`, `~/Library/Caches/com.google.FlutterSdk` | `pkg_cache` |
| `nvm` (`~/.nvm` present, dir probe — NVM is a shell function, no CLI on PATH) | `~/.nvm/versions/node/*` **except** the version matching `~/.nvm/alias/default` and any version used in the last 90 days (mtime on the version dir). Surface as individual items, one per non-default/stale version. | `pkg_cache` |
| `fnm` (CLI probe) | `~/Library/Application Support/fnm/node-versions/*` **except** the current one from `fnm current`, `~/Library/Caches/fnm_multishells` | `pkg_cache` |
| `pyenv` (CLI probe) | `~/.pyenv/versions/*` **except** (a) the global default from `pyenv version --bare` (run once, no cwd needed) and (b) any per-project pin from `pyenv local` — to collect (b) the agent must `cd` into each project root from `paths-projects.json` and run `pyenv local 2>/dev/null`; collect the union of every non-empty result. Surface per-version. | `pkg_cache` |
| `rustup` (CLI probe) | `~/.rustup/toolchains/*` **except** the default from `rustup default` and any pinned via `rustup override list`. Surface per-toolchain. | `pkg_cache` |
| JetBrains (`~/Library/Caches/JetBrains` present, dir probe) | `~/Library/Caches/JetBrains/*` (per-IDE cache: IntelliJIdea, PyCharm, WebStorm, GoLand, RubyMine, CLion, DataGrip, AndroidStudio, RustRover), `~/Library/Logs/JetBrains/*` | `dev_cache` |
| `gem` (CLI probe) or `~/.gem` present (dir probe) | `~/.gem/ruby/*/cache/`, `~/.gem/specs/` | `pkg_cache` |
| `bundle` (CLI probe) or `~/.bundle` present (dir probe) | `~/.bundle/cache/` (modern Bundler 2 nests `compact_index/` here; whole dir can be cleared) | `pkg_cache` |
| `composer` (CLI probe) or `~/.composer` / `~/Library/Caches/composer` present (dir probe) | `~/.composer/cache/` (Composer 1 / non-XDG), `~/Library/Caches/composer/` (Composer 2 XDG default on macOS) — probe both, include any that exist | `pkg_cache` |
| `poetry` (CLI probe) or `~/Library/Caches/pypoetry` present (dir probe) | `~/Library/Caches/pypoetry/` | `pkg_cache` |
| `ccache` (CLI probe) or `~/.ccache` / `~/Library/Caches/ccache` present (dir probe) | `~/.ccache/` (legacy default), `~/Library/Caches/ccache/` (XDG-style default used by newer ccache) — probe both | `pkg_cache` |
| `sccache` (CLI probe) or `~/Library/Caches/Mozilla.sccache` / `~/.cache/sccache` present (dir probe) | `~/Library/Caches/Mozilla.sccache/` (macOS default), `~/.cache/sccache/` (XDG fallback) — probe both | `pkg_cache` |
| `dart` (CLI probe) or `~/.pub-cache` present (dir probe) | `~/.pub-cache/hosted/`, `~/.pub-cache/git/` (Flutter's own `~/.flutter` cache is covered by the `flutter` row above; this is the standalone Dart pub cache) | `pkg_cache` |

## Blacklist — never touch

These directories are off-limits regardless of size or age. If a scan result somehow points into one of these, classify as L4 and record-only.

> **Cross-reference**: a subset of these (`.git`, `.ssh`, `.gnupg`, `Library/Keychains`, `Library/Mail`, `Library/Messages`, `Library/Mobile Documents`, `Photos Library`, `Music/Music`, `.env*`, SSH key files, **VSCode-family `User`/`Backups`/`History`**) is also enforced **at runtime** by `scripts/safe_delete.py`'s `_BLOCKED_PATTERNS` regex set. The agent reads this document; the script enforces a hard backstop. Keep them in sync — when adding/removing entries from one, update the other.

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
- VSCode-family editor user data: `~/Library/Application Support/{Code,Cursor,Windsurf}/User`, `.../Backups`, `.../History` (workspaceStorage holds unsaved edits and git-stash equivalents; Backups holds unsaved files; History is the local edit history).
- Zed editor state: `~/Library/Application Support/dev.zed.Zed/db` **except** `db/0/blob_store` (the blob_store is regenerable cache; the rest of `db/` is project state).
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
- `__pycache__`, `.pytest_cache`, `.tox`, `.mypy_cache`, `.ruff_cache` (Python tooling caches)
- `.dart_tool` (Dart / Flutter)
- `.nyc_output` (JS / nyc coverage intermediate)
- `_build` (Elixir / Phoenix; **only when project root has `mix.exs`** — agent must verify via `markers_found`)
- `Pods` (CocoaPods)
- `vendor` (Go modules vendored deps; **only when project root has `go.mod`** — agent must verify via `markers_found`)

**Virtual environments** (default L2 trash via `category=project_artifacts`, kind=`venv`):

- `.venv`, `venv`, `env` (Python)
  - **Heads-up for `env`**: this name is too generic; agent must skip if project root has no Python marker (`pyproject.toml` / `requirements.txt` / `setup.py`) in `markers_found`.

**Coverage reports** (default L2 trash via `category=project_artifacts`, kind=`coverage`):

- `coverage` (pytest-cov / nyc / istanbul / jest output)
  - **Marker gate**: agent must verify `markers_found` contains `package.json` or any Python marker (`pyproject.toml` / `requirements.txt` / `setup.py`) before treating this as `project_artifacts`. Without a matching marker, classify as `orphan` L4 — the name is too generic to trust unconditionally. See `category-rules.md` §10c.

Project root identification: presence of a `.git` directory. Other markers are **not** treated as project roots in v0.4 — `.git` covers ~all real project workspaces and avoids double-counting nested submodules. Bare git checkouts without any language marker are still recognised; markers only inform per-subtype decisions (see `category-rules.md` §10 for `vendor` / `env` / `_build` / `coverage` carve-outs).

The full set of language markers detected at each project root (mirrored to `markers_found` in the scan output) is:

`go.mod`, `package.json`, `Cargo.toml`, `pyproject.toml`, `requirements.txt`, `setup.py`, `Package.swift`, `Gemfile`, `composer.json`, `pubspec.yaml`, `mix.exs`.

> **Keep in sync** with `PROJECT_MARKERS` in `scripts/scan_projects.py` — adding a marker requires updating both this list and the script.

System / package-manager directories under `~/Library`, `~/.cache`, `~/.npm`, `~/.cargo`, `~/.cocoapods`, `~/.gradle`, `~/.m2`, `~/.gem`, `~/.bundle`, `~/.composer`, `~/.pub-cache`, `~/.local`, `~/.rustup`, `~/.pnpm-store`, `~/.Trash` are pruned from project discovery (they may contain cloned repos with `.git` that are not user projects).

## Scope-probe contract

When enumerating candidates:

1. Expand `~` to `$HOME` before passing to `scripts/collect_sizes.py`.
2. For each whitelist entry, check existence first (`os.path.exists`); skip silently if missing.
3. For each blacklist entry, never write it into `paths.json`. If a user explicitly asks to clean a blacklisted path, refuse and cite this document.
4. Tier E rows only appear in `paths.json` when Stage 2 confirmed the tool (CLI or directory marker, per row) is present.
5. For Tier E rows that require a per-entry exclusion (Node version managers, pyenv, rustup, Android SDK age gate), the agent first queries the tool for its "active" / "default" pins, then emits one item per non-active entry. Do not emit a single coarse item for the whole versions root — users need per-version granularity to pick what to keep.
6. For Tier C Group Containers and in-Container Application-Support cache sweeps, descend **only one level** and filter out any container identifier matching `Mail`, `Messages`, `CloudKit`, `iCloud` (promote those to L4 record-only).
