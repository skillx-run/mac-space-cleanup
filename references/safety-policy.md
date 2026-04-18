# Safety Policy

This document defines the **risk grading, default actions, confirmation bars, redaction rules, and degradation policy** for the skill. Read this alongside `category-rules.md` during Stage 4 (Grading) and Stage 5 (Confirm/Execute). It is the authoritative source for "why not" — when a call is borderline, follow this document, not inference.

## Risk levels

| Level | Semantic | Typical objects |
| --- | --- | --- |
| **L1** | Low-risk. Fully reversible or trivially regenerable. Safe to clean without user-by-user confirmation. | System / user caches, logs, trash, package-manager caches, build caches. |
| **L2** | Medium-risk. Reversible in principle but may inconvenience the user (re-download, re-index, re-login). | Old installers in `~/Downloads`, stale iOS backups, unused simulator runtimes, old Docker images, Time Machine local snapshots. |
| **L3** | High-risk. User-owned data; removal costly or irreversible without explicit artefact (trash / archive / migration target). | User documents, project workspaces, VM images, database dirs, large media, sync-folder local copies. |
| **L4** | Forbidden. Unclear semantics or system-critical. Record-only, no action. | Blacklisted paths in `cleanup-scope.md`, unrecognised top-level system dirs. |

## Default actions per level

| Level | Default `recommended_action` | Rationale |
| --- | --- | --- |
| L1 | `delete` | Regenerable; permanent delete is acceptable and faster than trash for many small files. |
| L2 | `trash` | Reversible via `~/.Trash`; user can recover within the session. |
| L3 | `trash` | Intentional: default to the most reversible option. Users may opt into `archive` or `migrate` during confirmation. `delete` is never the L3 default. |
| L4 | `skip` | Record-only. |

**Why L3 defaults to `trash` (not `archive`)**: trash is a familiar macOS concept and the user can recover from the Finder. Archive keeps a `tar.gz` inside `workdir` which costs disk too and adds a second manual decision later. Trash is the lower-cognitive-load default; users who explicitly want archive/migrate will say so.

## Confirmation bars (per mode)

| Mode | L1 | L2 | L3 | L4 |
| --- | --- | --- | --- | --- |
| **Quick** | Execute without confirmation | Batch confirm by category ("delete these 5 DMGs, 8GB total?") | **Not offered in quick mode**: record as `defer` in `deferred.jsonl` with a note; report's deferred section suggests running deep mode for these | Record-only, hidden from user |
| **Deep** | Show the list, user confirms the batch (default-checked) | Batch confirm by category | **Per-item hard confirmation** + show default action (`trash`) + allow override to `archive / migrate / defer / skip` | Show as record-only, disabled |

## Privacy redaction rules (UI layer)

`cleanup-result.json` may contain full paths for local audit. **Anything rendered into `report.html`, `share-card.{en,zh}.svg`, or share text must be redacted.**

### Forbidden in UI/share output

- Full filesystem paths (e.g., `/Users/alice/Projects/...`).
- File basenames (e.g., `secret-plan.pdf`, `company-report.xlsx`).
- System usernames (e.g., `alice`, `bob`).
- Project names (anything that looks like a repo folder).
- Company / client names.
- Any secret-like substring (`.env`, `id_rsa`, `token`, `password`).

### Allowed in UI/share output

- Category name (`dev_cache`, `downloads`, etc.).
- Source label at app or tool granularity: `"Xcode Simulator Runtimes"`, `"Docker build cache"`, `"Homebrew cache"`, `"Large archive in Downloads"`.
- Aggregate sizes.
- Risk level symbols / labels.
- Brand strings: `mac-space-cleanup`, `@heyiamlin`, hashtags.
- Mode label: `Quick Clean`, `Deep Clean`.

### Enforcement

- The agent must construct UI strings from `source_label` + `category`, never from `path` or `basename(path)`.
- Before writing share text, mentally scan the string for any forbidden token; if in doubt, drop to a generic label.
- `share-card-template.svg` accepts only these whitelisted placeholders: `${free_reclaimed}`, `${mode_label}`, `${top_categories}` (a ` · `-joined list of up to 3 category labels), `${label_reclaimed}`, `${label_top}`, `${label_by}`. The last three are locale strings Stage 6 fills from a fixed translation table, not free-form agent text — they cannot leak user data.

### Localized content redaction

The report is bilingual: agent-authored natural-language copy (hero caption, action reasons, observations recommendations, per-category `source_label`) is emitted twice — once in `<span data-locale-show="en">` and once in `<span data-locale-show="zh">`. Share card and share text also exist per locale (`share-card.{en,zh}.svg`, `share.{en,zh}.txt`).

- **Both locales are held to the same redaction rules.** A Chinese translation of a leaked project or company name is still a leak.
- `validate_report.py` scans the HTML as plain text; it makes no locale distinction and will catch path / username / credential literals wherever they appear.
- The redaction reviewer sub-agent is instructed to scan both locale variants; a leak flagged in one locale must be removed from **both** sibling spans so the user cannot toggle back to a leaked version.
- The confirm-stage basename exception below is unchanged — it still applies only to the live conversation, and both persisted locales must be basename-free.

## Confirm-stage exception (agent ↔ user dialog only)

The redaction rules above apply to **persisted artefacts** rendered to disk: `report.html`, `share-card.svg`, `share.{en,zh}.txt`. Those must use generic `source_label` / `category` only — no paths, basenames, project names, usernames.

The agent ↔ user **conversation during Stage 5 confirmation** is allowed to use the basename of a project root (e.g. `foo-app`, `bar-frontend`) when the user picks `yes-but-let-me-pick` for `project_artifacts` grouping. Without this, the user has no way to choose between several Node projects' `node_modules`.

Strict rules for the exception:

- Only the project root's **basename** — never the absolute path, never any ancestor.
- Only during the live confirm dialog. The moment the agent writes to a file under `$WORKDIR`, the redaction rules above apply again (so basenames in the conversation must NOT leak into `cleanup-result.json`'s `source_label`, into `report.html`, into share text).
- The post-render `validate_report.py` and the redaction reviewer sub-agent will catch leaks regardless — they do not know about this exception, by design. That's the safety net.

## Degradation matrix

| Failure (design doc §14) | Handler | Behaviour |
| --- | --- | --- |
| §14.1 Scan failure (timeout / permission denied for a path) | agent (Stage 3) + `collect_sizes.py` | Record the path in an in-memory `errors[]` list; do not abort. Report surfaces the count as a bilingual Pattern C node (e.g. "2 paths not fully scanned" / "有 2 项未扫描完成"), never the path itself. |
| §14.2 Classification failure (agent cannot decide category) | agent (Stage 4) | Assign `category=orphan`, `risk_level=L4`; show in deferred region, never execute. |
| §14.3 Execution failure (single item) | `safe_delete.py` | Per-item try/except, write `status=failed` + `error`, continue the batch. Overall exit 1 if any failures. |
| §14.4 Report render failure | agent (Stage 6) | Keep `cleanup-result.json` on disk; summarise results as plain text to the user. |
| §14.5 Enhancement tool missing (Docker/brew/etc.) | agent (Stage 2) | Skip the corresponding Tier E rows from `cleanup-scope.md`; proceed with whatever is detected. |

## History-driven UI adjustments (v0.5+)

`scripts/aggregate_history.py` surfaces cross-run confidence into `$WORKDIR/history.json` (see SKILL.md Stage 2.6). Stage 5 may use this data to collapse repetitive per-item confirmation into batch confirmation for `(source_label, category)` tuples the user has approved **≥3 times with 0 rejections**. These constraints are non-negotiable:

1. **Risk-level boundaries are never crossed.** A tag with 100 prior confirmations whose default is L3 stays on L3; history can only move it from "per-item confirm" to "batch confirm", never to "auto-execute". L4 never becomes interactive. The mapping in SKILL.md Stage 5 is the authoritative allow-list of downgrades.
2. **Mode boundaries are never crossed.** A tag whose `mode_hit_tags` excludes the current mode must not surface in that mode regardless of how strong the history is. History influences *how we ask*, not *what we surface*.
3. **One decline resets.** If `declined > 0` for a tag, treat it as if history were empty. The user expressed doubt once; the next session re-asks at the default bar. Confidence must be unbroken to earn the downgrade.
4. **Blocklist is supreme.** The `_BLOCKED_PATTERNS` regex set in `scripts/safe_delete.py` refuses any fs-touching action regardless of history. A repeatedly-approved path that subsequently drifts into blocklist territory is still refused.
5. **Dry-run and failed actions never count.** `aggregate_history.py` already excludes `dry_run=true` and `status=failed` records; do not build a workaround that uses them as a confidence signal.
6. **History only influences Stage 5 presentation.** Never use it to change Stage 4 grading, scope selection, or source_label emission. The classifier must produce the same output as a first-run classifier would, given the same filesystem.

## Operating invariants

1. **Agent never writes the filesystem directly for cleanup purposes.** Every `delete / trash / archive / migrate / defer` against **user-owned paths** must go through `scripts/safe_delete.py`. The only direct filesystem writes the agent performs are: (a) writing JSON files to `$WORKDIR`, (b) copying templates into `$WORKDIR` and editing the copies. Scripts under `scripts/` MAY manage their own workdir-family state directly (see the carve-out at invariant #3); `scripts/safe_delete.py` is the gate for user paths, not for our own scratch space.
2. **Workdir is per-run.** `$WORKDIR = ~/.cache/mac-space-cleanup/run-XXXXXX` from `mktemp -d`. Never reuse across runs.
3. **`actions.jsonl` is append-only and authoritative *within a single run*.** Re-running `safe_delete.py` against the same `$WORKDIR` with the same `confirmed.json` is safe: already-processed items (paths gone) become `skip` with `reason="already gone"`. **Cross-run preservation is best-effort, not authoritative.** `scripts/aggregate_history.py` GCs `run-*` dirs beyond the most-recent 20 (configurable with `--keep`), which removes their `actions.jsonl` along with the rest of the dir. This is an explicit carve-out from invariant #1 because (a) the data being deleted is scratch produced by this skill, not user-owned paths, and (b) within each surviving run the file remains append-only and authoritative for that run's audit trail. Stage 6 reports must read `actions.jsonl` from the current run only; retrospective analytics that need older runs should read them via `aggregate_history.py`'s redacted output before the GC window closes.
4. **Reclaimed bytes are honest, and split into three buckets.** A single `reclaimed_bytes` number is misleading because trash does not free disk until `~/.Trash` is emptied. `safe_delete.py` therefore reports four fields:
   - `freed_now_bytes` — disk *is already* free (delete + migrate).
   - `pending_in_trash_bytes` — bytes waiting in `~/.Trash` (trash + the originals of fully-successful archive). User must empty trash to convert this to free space.
   - `archived_source_bytes` / `archived_count` — fully-successful archive items.
   - `reclaimed_bytes` (deprecated alias) — `freed_now + pending_in_trash`, kept only for v0.1 consumers.

   The report's headline number and the share text default to `freed_now_bytes`. The "One last step" report region surfaces `pending_in_trash_bytes` and the one-line `osascript` command to empty trash, so users can convert pending into freed without leaving the report. Archive that succeeds without trashing the original (`archive_only_success`) contributes to none of these four — it is surfaced separately in the report's deferred section so the user can recover the partial state manually.
5. **No undo stack.** Recovery paths: `trash` → restore from Finder; `archive` → extract the tar from `workdir/archive/`; `migrate` → browse the target volume. If a user asks to "undo the last cleanup," point them at these artefacts.
6. **Blocklist backstop is non-negotiable.** `safe_delete.py` carries an in-code regex set (`_BLOCKED_PATTERNS`) that refuses any fs-touching action on paths matching `.git/`, `.ssh/`, `.gnupg/`, `Library/Keychains/`, `Library/Mail/`, `Library/Messages/`, `Library/Mobile Documents/`, `Photos Library.photoslibrary/`, `Music/Music/`, `.env*`, and SSH key files — independent of risk_level, category, or what `confirmed.json` says. This is a last-line-of-defence against agent misjudgement and a malformed `confirmed.json`. To remove a pattern you must change the code AND justify it in the commit message.
