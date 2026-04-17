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

`cleanup-result.json` may contain full paths for local audit. **Anything rendered into `report.html`, `share-card.svg`, or share text must be redacted.**

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
- Brand strings: `mac-space-clean`, `@heyiamlin`, hashtags.
- Mode label: `Quick Clean`, `Deep Clean`.

### Enforcement

- The agent must construct UI strings from `source_label` + `category`, never from `path` or `basename(path)`.
- Before writing share text, mentally scan the string for any forbidden token; if in doubt, drop to a generic label.
- `share-card-template.svg` accepts only the three whitelisted placeholders: `${free_reclaimed}`, `${mode_label}`, `${top_categories}` (a comma-joined list of up to 3 category labels).

## Degradation matrix

| Failure (design doc §14) | Handler | Behaviour |
| --- | --- | --- |
| §14.1 Scan failure (timeout / permission denied for a path) | agent (Stage 3) + `collect_sizes.py` | Record the path in an in-memory `errors[]` list; do not abort. Report surfaces "未扫描完成项". |
| §14.2 Classification failure (agent cannot decide category) | agent (Stage 4) | Assign `category=orphan`, `risk_level=L4`; show in deferred region, never execute. |
| §14.3 Execution failure (single item) | `safe_delete.py` | Per-item try/except, write `status=failed` + `error`, continue the batch. Overall exit 1 if any failures. |
| §14.4 Report render failure | agent (Stage 6) | Keep `cleanup-result.json` on disk; summarise results as plain text to the user. |
| §14.5 Enhancement tool missing (Docker/brew/etc.) | agent (Stage 2) | Skip the corresponding Tier E rows from `cleanup-scope.md`; proceed with whatever is detected. |

## Operating invariants

1. **Agent never writes the filesystem directly for cleanup purposes.** Every `delete / trash / archive / migrate / defer` must go through `scripts/safe_delete.py`. The only direct filesystem writes the agent performs are: (a) writing JSON files to `$WORKDIR`, (b) copying templates into `$WORKDIR` and editing the copies.
2. **Workdir is per-run.** `$WORKDIR = ~/.cache/mac-space-clean/run-XXXXXX` from `mktemp -d`. Never reuse across runs.
3. **`actions.jsonl` is append-only and authoritative.** If the batch is interrupted, re-running with the same `confirmed.json` is safe: already-processed items (paths gone) become `skip` with `reason="already gone"`.
4. **Reclaimed bytes are honest, and split into three buckets.** A single `reclaimed_bytes` number is misleading because trash does not free disk until `~/.Trash` is emptied. `safe_delete.py` therefore reports four fields:
   - `freed_now_bytes` — disk *is already* free (delete + migrate).
   - `pending_in_trash_bytes` — bytes waiting in `~/.Trash` (trash + the originals of fully-successful archive). User must empty trash to convert this to free space.
   - `archived_source_bytes` / `archived_count` — fully-successful archive items.
   - `reclaimed_bytes` (deprecated alias) — `freed_now + pending_in_trash`, kept only for v0.1 consumers.

   The report's headline number and the share text default to `freed_now_bytes`. The "One last step" report region surfaces `pending_in_trash_bytes` and the one-line `osascript` command to empty trash, so users can convert pending into freed without leaving the report. Archive that succeeds without trashing the original (`archive_only_success`) contributes to none of these four — it is surfaced separately in the report's deferred section so the user can recover the partial state manually.
5. **No undo stack.** Recovery paths: `trash` → restore from Finder; `archive` → extract the tar from `workdir/archive/`; `migrate` → browse the target volume. If a user asks to "undo the last cleanup," point them at these artefacts.
