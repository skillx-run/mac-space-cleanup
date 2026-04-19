# Category Rules

Match each observed candidate to **one** of the 10 categories. Each rule block gives: path patterns / probe, default `risk_level`, default `recommended_action`, and `mode_hit_tags` (which modes should surface this category).

Matching order: check rules top-to-bottom, first match wins. Note that §10 `project_artifacts` items only ever come from `scripts/scan_projects.py`, so other rules never compete for them. If no rule matches, fall through to `orphan` (L4).

---

## 1. `dev_cache`

Developer build caches. Fully regenerable by rebuilding.

- `~/Library/Developer/Xcode/DerivedData/**` (directory)
- `~/Library/Developer/Xcode/Archives/**` older than 90 days
- `~/Library/Developer/Xcode/iOS DeviceSupport/**` (per-entry: one item per OS-version subdir; mtime exposes when Xcode last mounted a device of that OS)
- `~/Library/Developer/Xcode/watchOS DeviceSupport/**` (same granularity)
- `~/Library/Developer/Xcode/tvOS DeviceSupport/**` (same granularity)
- `~/Library/Caches/go-build/**`
- `~/.gradle/caches/**`
- `~/Library/Caches/JetBrains/**` (per-IDE: IntelliJIdea, PyCharm, WebStorm, GoLand, RubyMine, CLion, DataGrip, AndroidStudio, RustRover — each subdir is one item)
- `~/Library/Logs/JetBrains/**`
- `~/.flutter/**`, `~/Library/Caches/Flutter/**`, `~/Library/Caches/com.google.FlutterSdk/**`
- `~/Library/Developer/XCPGDevices/**`, `~/Library/Developer/XCPGPlaygrounds/**` (Xcode Playground per-device snapshots)
- Docker build cache reported by `docker builder du` (semantic path `docker:build-cache`)
- Docker dangling images from `docker images -f dangling=true` (semantic path `docker:dangling-images`)
- Docker stopped containers from `docker ps -a --filter status=exited --filter status=created` (semantic path `docker:stopped-containers`; running containers are not touched)

Defaults: **L1**, `delete`, `mode_hit_tags=["quick","deep"]`.

Exceptions (all override defaults — exception always wins on a tied match):
- Xcode Archives younger than 90 days → `dev_cache` L2 `trash` (might still be needed for App Store upload). The default L1 delete only applies to Archives mtime ≥ 90 days; never both at once for the same item.
- iOS / watchOS / tvOS `DeviceSupport` entries default to **L2 `trash`** (not delete) because each per-OS subdir is 5–10 GB and rebuilding the symbol cache requires plugging in a device of that OS again — re-pull takes 10+ minutes the next time the user debugs against that OS. Trash gives a same-session recovery window. (DerivedData stays L1 `delete` — fully regenerable from a single project rebuild.)
- iOS DeviceSupport for the OS version currently installed on a paired device (not knowable without `xcrun devicectl list` — agent should skip this check; surface per-OS so user can uncheck active ones in deep mode).

---

## 2. `sim_runtime`

iOS / watchOS / tvOS simulators and unavailable runtimes.

- `~/Library/Developer/CoreSimulator/Devices/**` for devices not in `xcrun simctl list devices available`
- Output of `xcrun simctl delete unavailable` (semantic path `xcrun:simctl-unavailable`)
- Simulator caches under `~/Library/Developer/CoreSimulator/Caches/**`

Defaults: **L1**, `delete` (**via `xcrun simctl`, never `rm`**), `mode_hit_tags=["quick","deep"]`.

Rationale: aligns with Apple's own `xcrun simctl delete unavailable`, which removes simulator data outright rather than via Trash; runtimes and devices are fully rebuildable from Xcode. Routing through `simctl` keeps the user safe — `simctl delete` refuses to remove a *booted* simulator, so an in-flight debugging session is protected. `safe_delete.py` recognises `category=="sim_runtime"` and dispatches to the `_handle_simctl_delete` branch instead of `rm -rf` (parallel to how `system_snapshots` is dispatched to `tmutil deletelocalsnapshots`).

---

## 3. `pkg_cache`

Language / package manager caches.

- `$(brew --cache)` — files within the directory whose **mtime is older than 30 days**; the directory itself is never deleted, only its files (`find $(brew --cache) -type f -mtime +30`)
- Old Homebrew Cellar versions and stale downloads via `brew cleanup -s` (semantic path `brew:cleanup-s`; pinned formulae are preserved automatically)
- `$(npm config get cache)/**`
- `$(pnpm store path)` contents
- `~/Library/Caches/Yarn/**`
- `~/.yarn/berry/cache/**` (Yarn Berry global PnP cache, only present when `enableGlobalCache: true`)
- `~/.bun/install/cache/**`, `~/Library/Caches/com.oven.bun/**`
- `~/Library/Caches/deno/**`
- `$(pip cache dir)/**`
- `$(uv cache dir)/**`
- `~/.cargo/registry/cache/**`, `~/.cargo/registry/src/**`
- `~/.cocoapods/repos/**` older than 180 days
- `~/Library/Caches/CocoaPods/**`
- `~/Library/Caches/org.swift.swiftpm/**`, `~/Library/org.swift.swiftpm/repositories/**` (SwiftPM clones every transitive dep as a git working copy)
- `~/Library/Caches/org.carthage.CarthageKit/**`
- `~/Library/Android/sdk/system-images/*` where the entry's mtime is older than 180 days (each API-level/arch subdir is one item; active development keeps the dir fresh)
- `~/Library/Android/sdk/.temp/**`, `~/Library/Android/sdk/emulator/skins/**`
- `~/.nvm/versions/node/*` excluding the `~/.nvm/alias/default` target and any version dir touched in the last 90 days (one item per kept-out version)
- `~/Library/Application Support/fnm/node-versions/*` excluding the result of `fnm current`
- `~/Library/Caches/fnm_multishells/**` (shell-session caches, always disposable)
- `~/.pyenv/versions/*` excluding `pyenv version --bare` and any pin discovered via `pyenv local` in scanned projects
- `~/.rustup/toolchains/*` excluding the `rustup default` toolchain and any `rustup override list` pin

Defaults: **L1**, `delete`, `mode_hit_tags=["quick","deep"]`.

Exceptions:
- `~/.m2/repository/**` — surface size but set **L3** `defer` (Maven has no clean CLI, manual users prefer to keep).
- Node/Python/Rust per-version entries above default to **L2** `trash` (not delete) because reinstalling a specific point-release can fail — PyPI yanks, ABI drift, private registries. `mode_hit_tags=["deep"]` — quick mode skips these to avoid surprise removal of a runtime in active use.
- Android `system-images` entries default to **L2** `trash` for the same re-download-friction reason: the SDK Manager GUI can restore them, but it is a multi-click flow.

---

## 4. `app_cache`

User-facing application caches (non-developer).

- `~/Library/Caches/*` that do **not** match `dev_cache` or `pkg_cache` rules above
- `~/Library/Saved Application State/**`
- `~/Library/Containers/*/Data/Library/Caches/**`
- `~/Library/Group Containers/*/Library/Caches/**` (one level deep; shared Apple-app caches)
- `~/Library/Containers/*/Data/Library/Application Support/Cache*` (case-insensitive; some Electron apps stash cache outside the `Caches` tree)
- `~/Library/Application Support/{Code,Cursor,Windsurf}/{Cache,CachedData,CachedExtensionVSIXs,Crashpad,GPUCache,Code Cache,logs}/**` (VSCode-family non-sandboxed editor caches — see cleanup-scope.md Tier C subset)
- `~/Library/Application Support/dev.zed.Zed/{db/0/blob_store,logs}/**` (Zed editor cache; `db/` itself is project state and is in the blacklist)
- `~/.Trash/**` (yes — trash itself is app-cache-like; `delete` empties it)

Defaults: **L1**, `delete`, `mode_hit_tags=["quick","deep"]`.

Exceptions:
- If the cache subdir / container identifier contains `Mail`, `Keychain`, `iCloud`, or `CloudKit` → **L4** `skip` (surface only; never touch per `cleanup-scope.md` blacklist).
- If the path matches a **Tier C** entry in `cleanup-scope.md` (browser or messaging-app cache — Safari/Chrome/Firefox/Brave/Edge/Arc, WeChat/Discord/Slack/Teams/Telegram/Lark/Signal; **or the non-sandboxed editor subset — Code/Cursor/Windsurf/Zed**), override to **L2** `trash`. Rationale: these caches re-populate on the next app launch, but a trash recovery window avoids nuking an active chat session, a signed-in browser profile, or an open editor's just-warmed extension cache.
- `~/Library/Group Containers/*` and in-Container `Application Support/Cache*` sweeps also inherit the L2 trash exception when their identifier matches a Tier C browser/messaging app (the generic sweep pattern is Tier C-adjacent by design).

---

## 5. `logs`

Logs and crash reports.

- `~/Library/Logs/**`
- `~/Library/Application Support/CrashReporter/**`
- `~/Library/DiagnosticReports/**` (per-user crash / hang / spin reports; `.ips`, `.crash`, `.diag`)
- `/private/var/log/**` older than 30 days (L4 if file is currently open by a system process — check `lsof`; otherwise L1)

Defaults: **L1**, `delete`, `mode_hit_tags=["quick","deep"]`.

---

## 6. `downloads`

User-downloaded installers and archives. Split by naming-convention strength:

### 6a. Clear-cut installers → **L1 `delete`**

The extension carries unambiguous semantic meaning (Apple/macOS distribution formats, ISO images). Users keep these almost never; reinstall is the recovery path.

- `~/Downloads/*.dmg` older than 30 days
- `~/Downloads/*.pkg` older than 30 days
- `~/Downloads/*.xip` older than 30 days
- `~/Downloads/*.iso` older than 30 days
- `~/Downloads/*.appimage` older than 30 days (Linux app installer accidentally landed on macOS)
- `~/Downloads/*.deb` older than 30 days (Debian package; not usable on macOS)
- `~/Downloads/*.rpm` older than 30 days (RPM package; not usable on macOS)
- `~/Downloads/*.msi` older than 30 days (Windows installer; not usable on macOS)

Defaults: **L1**, `delete`, `mode_hit_tags=["quick","deep"]`.

### 6b. Generic archives → **L2 `trash`**

The extension does not tell us whether it is a source-code snapshot, a backup, an exported document, or a one-off download. Keep the recovery window via Trash.

- `~/Downloads/*.zip` older than 90 days and size > 100MB
- `~/Downloads/*.tar.gz`, `*.tgz`, `*.tar.bz2` older than 90 days and size > 100MB
- `~/Downloads/*.7z`, `*.rar` older than 90 days and size > 100MB

Defaults: **L2**, `trash`, `mode_hit_tags=["quick","deep"]`.

Agent heuristic: if a filename contains `Xcode_`, `Xcode-`, or matches `*_[0-9]+.[0-9]+*.xip` and size > 5GB → add `reason="old Xcode installer"`. (These already match 6a `.xip` rule and so default to L1 delete — heuristic just enriches the reason string.)

### 6c. Pulled-out applications in Downloads → **L3 `defer`**

`*.app` bundles in `~/Downloads` are usually one of: (a) freshly extracted from a `.dmg` and not yet dragged into `/Applications`, (b) extracted long ago and forgotten, (c) a portable app the user runs in place. (a) and (c) must not be touched; (b) is the cleanup target. The agent can't reliably distinguish them, so surface as defer and let the user decide.

- `~/Downloads/*.app` (directory bundle) older than 90 days **and** size > 100MB

Defaults: **L3**, `defer`, `mode_hit_tags=["deep"]`.

Rationale: 90 days + 100MB filter rules out small portable utilities the user may still run; the user picks per-item via the deferred section. `quick` mode skips entirely so a fresh DMG extraction never even appears.

---

## 7. `large_media`

Large user media or backups that should be considered but never auto-cleaned.

- `~/Library/Application Support/MobileSync/Backup/*` older than 180 days (iOS device backups)
- Any file > 2GB in `~/Movies`, `~/Music`, `~/Pictures` **outside** the Photos / Music libraries — surface only
- Generic `du`-detected dirs > 2GB that don't match other rules, under `~/`. **Probe via `du -d 2 ~/`** (depth-limited so deep filesystem trees don't blow past the 30s per-path budget); post-filter the output to entries ≥ 2 GiB and **cap the surfaced list at the top 30 by size** so the deferred section stays scannable.

Defaults: **L3**, `defer`, `mode_hit_tags=["deep"]`.

Rationale: too risky to auto-trash; user should decide case by case via the deferred region of the report.

---

## 8. `system_snapshots`

APFS local Time Machine snapshots from `tmutil listlocalsnapshots /`.

- Each `com.apple.TimeMachine.YYYY-MM-DD-HHMMSS.local` entry → item with `path="snapshot:<full-snapshot-name>"` and size unknown (macOS does not expose per-snapshot size cheaply; use `0` and annotate `reason="size not exposed by tmutil"`).

Defaults: **L2**, `delete`, `mode_hit_tags=["deep"]`.

Handling: `safe_delete.py` detects `category=="system_snapshots"` and dispatches to `tmutil deletelocalsnapshots <date>`, bypassing `rm`/`trash`. Do not attempt `trash` on these.

---

## 10. `project_artifacts`

Build outputs and virtual environments inside user project workspaces (recognised by `.git` directory at root). Surface only via `scripts/scan_projects.py` — never via free-form `find` on `~/Downloads` or similar.

Two subtypes (returned by `scan_projects.py` as the `kind` field):

### 10a. Deletable build / install outputs → **L1 `delete`**

Subtypes: `node_modules`, `target`, `build`, `dist`, `out`, `.next`, `.nuxt`, `.svelte-kit`, `.turbo`, `.parcel-cache`, `__pycache__`, `.pytest_cache`, `.tox`, `.mypy_cache`, `.ruff_cache`, `.dart_tool`, `.nyc_output`, `_build` (Elixir only), `Pods`, `vendor` (Go only).

Defaults: **L1**, `delete`, `mode_hit_tags=["deep"]` (quick mode skips project artifacts to avoid clearing fresh installs).

Rationale: by convention these are 100% reproducible by re-running the install/build command. Same risk class as `pkg_cache` (homebrew/npm cache), just per-project rather than global.

**Vendor disambiguation**: `scan_projects.py` always returns `vendor/` if it exists, but only `vendor/` in projects with `go.mod` in `markers_found` should be classified as `project_artifacts`. For non-Go `vendor/` (e.g. Composer's vendor in PHP, or Bundler's), classify as `orphan` L4 instead — the agent must check `markers_found` before assigning the rule here.

**`_build` disambiguation**: `_build/` belongs to Elixir / Phoenix — the agent must verify `markers_found` contains `mix.exs` before classifying as `project_artifacts`. Without the marker, classify as `orphan` L4. `scan_projects.py::PROJECT_MARKERS` includes `mix.exs` specifically so this check works; keep the two in sync.

### 10b. Virtual environments → **L2 `trash`**

Subtypes: `.venv`, `venv`, `env`.

Defaults: **L2**, `trash`, `mode_hit_tags=["deep"]`.

Rationale: virtual environments often contain wheel versions specific to one moment in time (PyPI may have yanked, dependency may pin to a no-longer-buildable version). Trash gives a recovery window. The user can `python -m venv .venv && pip install -r requirements.txt` to reconstruct, but it might fail.

**Env disambiguation**: `env/` is too generic a name. The agent must check `markers_found` for at least one Python marker (`pyproject.toml`, `requirements.txt`, `setup.py`) before treating `env/` as a `project_artifacts` venv. Otherwise classify as `orphan` L4.

### 10c. Coverage reports → **L2 `trash`**

Subtype: `coverage` (returned by `scan_projects.py` with `kind="coverage"`).

Defaults: **L2**, `trash`, `mode_hit_tags=["deep"]`.

Rationale: pytest-cov, nyc, istanbul, jest and similar test-coverage tools all default to writing their HTML / XML reports to a top-level `coverage/` directory. Reports are fully regenerable by re-running the test suite, but the name `coverage/` is generic enough that a session-level trash window is the right safety net — it protects the minority of users who manually curate a directory named `coverage` for unrelated purposes.

**Marker gate**: the agent must verify `markers_found` contains `package.json` or any Python marker (`pyproject.toml`, `requirements.txt`, `setup.py`) before treating `coverage/` as `project_artifacts`. Without a matching marker, classify as `orphan` L4. This is analogous to the `env/` and `_build/` carve-outs above — `scan_projects.py` surfaces the directory unconditionally, classification-time disambiguation happens here.

### Source label

`source_label` for both subtypes: `"Project <subtype>"` (e.g. `"Project node_modules"`, `"Project .venv"`). **Never include the project name or path in source_label** — that would leak through to report.html / share text. The agent ↔ user confirm dialog at Stage 5 may use project basenames per the `safety-policy.md` confirm-stage exception, but those basenames must not propagate to persisted artefacts.

`mode_hit_tags=["deep"]` only — quick mode does NOT scan project artifacts. Reason: quick mode runs without per-item review, and a fresh `node_modules` deleted right after `npm install` is a bad UX even if technically harmless.

### Match order

When the agent classifies an item, the match order is: rules 1–8 → rule 10 → rule 9 (orphan fallback). In practice `project_artifacts` paths only ever come from `scan_projects.py` and other rules don't compete, so this is implicit; explicit only for the disambiguation cases above.

---

## 9. `orphan` (fallback)

Anything that did not match rules 1–8 or rule 10.

Defaults: **L4**, `skip`, `mode_hit_tags=["deep"]`.

Reason field should be `"no matching rule"`. Surface in the deferred region for manual review.

---

## Output contract per item

Stage 4 produces in-memory items with these fields (matches `cleanup-result.json` schema):

```
{
  "id": "<sha1(path)[:12]>",
  "path": "<real path or semantic entry>",
  "category": "<one of the 9 above>",
  "size_bytes": <int>,
  "mtime": <unix_ts or null>,
  "risk_level": "L1|L2|L3|L4",
  "recommended_action": "<per the rule, may be overridden>",
  "source_label": "<human label for UI, e.g. 'Xcode DerivedData'>",
  "mode_hit_tags": ["quick"] | ["deep"] | ["quick","deep"],
  "reversible": <bool, true for trash/archive/migrate targets>,
  "reason": "<which rule matched, one sentence>"
}
```

`source_label` guide (UI-safe, redaction-compliant):

| Category | Typical source_label values |
| --- | --- |
| `dev_cache` | `"Xcode DerivedData"`, `"Xcode Archives"`, `"iOS DeviceSupport"`, `"watchOS DeviceSupport"`, `"tvOS DeviceSupport"`, `"Xcode Playground cache"`, `"Go build cache"`, `"Gradle cache"`, `"Docker build cache"`, `"Docker dangling images"`, `"Docker stopped containers"`, `"JetBrains cache"`, `"Flutter SDK cache"` |
| `sim_runtime` | `"Xcode Simulator Runtimes"`, `"Xcode Simulator Devices"` |
| `pkg_cache` | `"Homebrew cache"`, `"Homebrew Cellar cleanup"`, `"npm cache"`, `"pnpm store"`, `"Yarn Berry cache"`, `"Bun cache"`, `"Deno cache"`, `"pip cache"`, `"uv cache"`, `"Cargo cache"`, `"Swift PM cache"`, `"Carthage cache"`, `"Android SDK image"`, `"Node version manager"`, `"Python version manager"`, `"Rust toolchain"` |
| `app_cache` | `"System caches"`, `"Saved application state"`, `"Trash"`, `"Browser cache"`, `"Messaging cache"`, `"Editor cache"` |
| `logs` | `"User logs"`, `"Crash reports"`, `"Diagnostic reports"`, `"System logs"` |
| `downloads` | `"Old installers"`, `"Large archives in Downloads"` |
| `large_media` | `"iOS backups"`, `"Large files in Movies"` |
| `system_snapshots` | `"Time Machine local snapshots"` |
| `project_artifacts` | `"Project node_modules"`, `"Project target"`, `"Project build"`, `"Project .venv"`, `"Project coverage"`, … (subtype only, never path or project basename) |
| `orphan` | `"Unclassified large item"` |

Never put a path or basename into `source_label`.

The English labels above are the canonical form. When `$LOCALE != en`, Stage 6 translates each label once into the target language as it fills the report — no pre-baked per-locale table is maintained. Proper nouns (`node_modules`, `npm`, `Docker`, IDE / SDK names) stay in ASCII across locales both for length economy and because developers read them as-is. For share-card SVG width (≤~6 display columns per label inside `${top_categories}`), truncate with `…` if a translated label overflows.
