# Category Rules

Match each observed candidate to **one** of the 9 categories. Each rule block gives: path patterns / probe, default `risk_level`, default `recommended_action`, and `mode_hit_tags` (which modes should surface this category).

Matching order: check rules top-to-bottom, first match wins. If none match, fall through to `orphan` (L4).

---

## 1. `dev_cache`

Developer build caches. Fully regenerable by rebuilding.

- `~/Library/Developer/Xcode/DerivedData/**` (directory)
- `~/Library/Developer/Xcode/Archives/**` older than 90 days
- `~/Library/Caches/go-build/**`
- `~/.gradle/caches/**`
- Docker build cache reported by `docker builder du` (semantic path `docker:build-cache`)
- Docker dangling images from `docker images -f dangling=true` (semantic path `docker:dangling-images`)

Defaults: **L1**, `delete`, `mode_hit_tags=["quick","deep"]`.

Exception: Xcode Archives younger than 90 days → treat as `dev_cache` L2 `trash` (might still be needed for App Store upload).

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

- `$(brew --cache)` directory contents older than 30 days
- `$(npm config get cache)/**`
- `$(pnpm store path)` contents
- `~/Library/Caches/Yarn/**`
- `$(pip cache dir)/**`
- `$(uv cache dir)/**`
- `~/.cargo/registry/cache/**`, `~/.cargo/registry/src/**`
- `~/.cocoapods/repos/**` older than 180 days
- `~/Library/Caches/CocoaPods/**`

Defaults: **L1**, `delete`, `mode_hit_tags=["quick","deep"]`.

Exception: `~/.m2/repository/**` — surface size but set **L3** `defer` (Maven has no clean CLI, manual users prefer to keep).

---

## 4. `app_cache`

User-facing application caches (non-developer).

- `~/Library/Caches/*` that do **not** match `dev_cache` or `pkg_cache` rules above
- `~/Library/Saved Application State/**`
- `~/Library/Containers/*/Data/Library/Caches/**`
- `~/.Trash/**` (yes — trash itself is app-cache-like; `delete` empties it)

Defaults: **L1**, `delete`, `mode_hit_tags=["quick","deep"]`.

Exception: if the cache subdir name contains `Mail`, `Keychain`, `iCloud`, or `CloudKit` → **L4** `skip` (surface only; never touch per `cleanup-scope.md` blacklist).

---

## 5. `logs`

Logs and crash reports.

- `~/Library/Logs/**`
- `~/Library/Application Support/CrashReporter/**`
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

Defaults: **L1**, `delete`, `mode_hit_tags=["quick","deep"]`.

### 6b. Generic archives → **L2 `trash`**

The extension does not tell us whether it is a source-code snapshot, a backup, an exported document, or a one-off download. Keep the recovery window via Trash.

- `~/Downloads/*.zip` older than 90 days and size > 100MB
- `~/Downloads/*.tar.gz`, `*.tgz`, `*.tar.bz2` older than 90 days and size > 100MB
- `~/Downloads/*.7z`, `*.rar` older than 90 days and size > 100MB

Defaults: **L2**, `trash`, `mode_hit_tags=["quick","deep"]`.

Agent heuristic: if a filename contains `Xcode_`, `Xcode-`, or matches `*_[0-9]+.[0-9]+*.xip` and size > 5GB → add `reason="old Xcode installer"`. (These already match 6a `.xip` rule and so default to L1 delete — heuristic just enriches the reason string.)

---

## 7. `large_media`

Large user media or backups that should be considered but never auto-cleaned.

- `~/Library/Application Support/MobileSync/Backup/*` older than 180 days (iOS device backups)
- Any file > 2GB in `~/Movies`, `~/Music`, `~/Pictures` **outside** the Photos / Music libraries — surface only
- Generic `du`-detected dirs > 10GB that don't match other rules, under `~/`

Defaults: **L3**, `defer`, `mode_hit_tags=["deep"]`.

Rationale: too risky to auto-trash; user should decide case by case via the deferred region of the report.

---

## 8. `system_snapshots`

APFS local Time Machine snapshots from `tmutil listlocalsnapshots /`.

- Each `com.apple.TimeMachine.YYYY-MM-DD-HHMMSS.local` entry → item with `path="snapshot:<full-snapshot-name>"` and size unknown (macOS does not expose per-snapshot size cheaply; use `0` and annotate `reason="size not exposed by tmutil"`).

Defaults: **L2**, `delete`, `mode_hit_tags=["deep"]`.

Handling: `safe_delete.py` detects `category=="system_snapshots"` and dispatches to `tmutil deletelocalsnapshots <date>`, bypassing `rm`/`trash`. Do not attempt `trash` on these.

---

## 9. `orphan` (fallback)

Anything that did not match rules 1–8.

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
| `dev_cache` | `"Xcode DerivedData"`, `"Xcode Archives"`, `"Go build cache"`, `"Gradle cache"`, `"Docker build cache"` |
| `sim_runtime` | `"Xcode Simulator Runtimes"`, `"Xcode Simulator Devices"` |
| `pkg_cache` | `"Homebrew cache"`, `"npm cache"`, `"pnpm store"`, `"pip cache"`, `"uv cache"`, `"Cargo cache"` |
| `app_cache` | `"System caches"`, `"Saved application state"`, `"Trash"` |
| `logs` | `"User logs"`, `"Crash reports"`, `"System logs"` |
| `downloads` | `"Old installers"`, `"Large archives in Downloads"` |
| `large_media` | `"iOS backups"`, `"Large files in Movies"` |
| `system_snapshots` | `"Time Machine local snapshots"` |
| `orphan` | `"Unclassified large item"` |

Never put a path or basename into `source_label`.
