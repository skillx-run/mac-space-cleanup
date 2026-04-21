---
name: release
description: "Cut a new versioned release of the mac-space-cleanup repo: promote CHANGELOG.md's `## Unreleased` section to a dated `## vX.Y.Z — YYYY-MM-DD` header, open a PR against the branch-protected `main`, and after the PR merges, tag the merge commit and publish a GitHub Release. Trigger when the user says `release`, `cut a release`, `ship a new version`, `publish release`, `发版`, `发个版`, `打 tag`, `打个 tag`, `发布新版本`."
version: "0.1.0"
author: "lin"
---

# release

An agent-driven release workflow for this repository. You (the agent) are the decision-maker; the workflow is ~20 shell commands spread across five stages. Two safety rules are load-bearing: `main` is branch-protected (direct push is denied by the harness, not only by GitHub), and the version number is publicly visible once tagged, so it is **always** confirmed by the user via `AskUserQuestion` — never auto-picked.

## When to activate

Activate when the user's intent matches "cut a release", e.g. `release`, `release v0.14`, `cut a release`, `ship a new version`, `publish release`, or Chinese `发版`, `发个版`, `打 tag`, `打个 tag`, `发布新版本`.

Do **not** activate for unrelated phrasings that happen to share the word, e.g. `release this lock`, `release the file handle`, `发布会`.

## Repository assumptions

This skill is pinned to the conventions of `skillx-run/mac-space-cleanup` and will not silently adapt to other shapes:

1. **Default branch** is `main` and is **branch-protected** — direct `git push origin main` is denied by the harness with "bypasses PR review". All changes, including the CHANGELOG bump, go through a PR.
2. **Versioning** is SemVer with `vX.Y.Z` tags. `v0.0.0` and pre-release suffixes are out of scope.
3. **CHANGELOG.md** follows a Keep-a-Changelog variant:
   - Top section is `## Unreleased` (exact string, no date).
   - Released sections are `## vX.Y.Z — YYYY-MM-DD` (em dash, spaces both sides).
   - Newest first.
4. **CLAUDE.md** carries internal-narrative version labels (e.g. `## v0.14 report visualization contract alignment`) that **may be ahead of** the last shipped git tag. These labels are authoritative for the *intended* next version number but require confirmation.
5. **GitHub CLI** (`gh`) is installed and authenticated against the repo.
6. **Working directory** when the skill is invoked is (or contains) the `mac-space-cleanup` repo root.

If any assumption is false — stop and ask the user. Do not attempt to fix the repo.

## What you must NOT do

1. **Never push directly to `main`**, even if the harness doesn't reject. The CHANGELOG edit always lands via PR.
2. **Never force-push**, `git reset --hard`, delete tags on the remote, or delete GitHub Releases without explicit user approval — these are all visible-to-others, hard-to-reverse actions.
3. **Never skip the `AskUserQuestion` version-confirm step.** The proposal is a proposal, not a decision.
4. **Never proceed past Stage 3** (the PR is opened) without the user explicitly confirming the PR is merged. CI may fail, a reviewer may request changes, the commit may need amending — none of that is this skill's concern.
5. **Never tag a commit that is not the tip of `main`** after the release PR merges. If `main` has moved since, stop and surface the divergence.

## Workflow (five stages)

### Stage 1 · Pre-flight

Collect the full state in one go. Every subsequent stage reads from these signals, so run this block verbatim:

```bash
git rev-parse --show-toplevel                           # confirm repo root
git status --porcelain                                  # must be empty
git branch --show-current                               # must equal DEFAULT_BRANCH
git fetch --all --tags --prune
LAST_TAG=$(git tag --list 'v*' --sort=-v:refname | head -1)   # may be empty
DEFAULT_BRANCH=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)
git rev-list --left-right --count "origin/$DEFAULT_BRANCH...HEAD"  # "0\t0" = in sync
gh release list --limit 5                               # baseline for Stage 5 verification
```

**Blockers** — surface to the user, do not auto-fix:

- `git status --porcelain` non-empty → dirty tree; user must commit / stash / discard manually.
- Current branch ≠ `$DEFAULT_BRANCH` → ask before proceeding; releasing from a non-default branch is unusual enough to warrant confirmation.
- `origin/main` ahead or behind HEAD → pull / investigate; never `reset --hard`.
- `gh auth status` fails → user must re-auth; don't prompt them for tokens.

### Stage 2 · Propose version

Gather the evidence the user will see in the confirmation prompt. Run each in the background into memory, not into files:

1. **Last shipped tag**: `$LAST_TAG` from Stage 1.
2. **Existing GitHub Releases**: `gh release list` output. If the list is empty but tags exist, flag it — this repo has tags from internal development but no published Release.
3. **CHANGELOG `## Unreleased` body** — everything between the `## Unreleased` header and the next `## ` header:
   ```bash
   awk '/^## Unreleased[[:space:]]*$/ {on=1; next} /^## / {on=0} on' CHANGELOG.md
   ```
4. **Commits since last tag** — `git log --oneline "$LAST_TAG"..HEAD` if `$LAST_TAG` is set, else `git log --oneline`. Look for Conventional Commits prefixes.
5. **Internal narrative in CLAUDE.md** — does the `## Unreleased` body or any recent CLAUDE.md section reference a specific `vX.Y.Z` label (e.g. "v0.14 report visualization contract alignment")? If yes, that label is the **first candidate** for the proposed version.

Apply these rules **in order** to produce a single proposed version:

| Rule | Proposal |
|------|----------|
| Unreleased body or recent CLAUDE.md entry names an explicit `vX.Y.Z` | That exact version |
| Commits contain `!:` or `BREAKING CHANGE:` | Major bump of `$LAST_TAG` |
| Commits contain any `feat:` / `feat(...):` | Minor bump of `$LAST_TAG` |
| Commits are only `fix:` / `docs:` / `refactor:` / `test:` / `chore:` | Patch bump of `$LAST_TAG` |
| No commits since `$LAST_TAG` | Stop; nothing to release |

**Call `AskUserQuestion`** with three options:

- **Accept the proposal** — `$PROPOSED_VERSION`, with a one-line justification citing which rule fired.
- **Enter a different version** — "Other (free text)". Validate the reply matches `v\d+\.\d+\.\d+` and is strictly newer than `$LAST_TAG` (if set). If invalid, re-ask once.
- **Cancel** — abort the skill cleanly, leave no artefacts.

Persist the confirmed version and today's date for the next stages:

```bash
VERSION=<confirmed>                                     # e.g. v0.14.0
DATE=$(date +%Y-%m-%d)                                  # system date
```

### Stage 3 · CHANGELOG + release branch PR

The edit is mechanical but must match the CHANGELOG's exact conventions.

1. Rewrite `CHANGELOG.md`:
   - Rename the existing `## Unreleased` header to `## $VERSION — $DATE` (ASCII hyphen-minus **will not match**; use em dash `—` U+2014, the same character already used in the file).
   - Insert a fresh `## Unreleased\n\n` block **above** the renamed section. Empty body — do not prepopulate.
   - Do not touch any other section.

   Verify the edit before commit: the file must still parse cleanly and the new `## $VERSION — $DATE` line must appear exactly once.

2. Branch and commit:

   ```bash
   git switch -c "release/$VERSION"
   git add CHANGELOG.md
   git commit -m "release: $VERSION"
   git push -u origin "release/$VERSION"
   ```

3. Open the PR with the extracted CHANGELOG section as the body:

   ```bash
   NOTES=$(awk -v hdr="## $VERSION — $DATE" '
     $0 == hdr {on=1; next}
     /^## / && on {exit}
     on
   ' CHANGELOG.md)

   gh pr create --base "$DEFAULT_BRANCH" --head "release/$VERSION" \
     --title "release: $VERSION" \
     --body "$(cat <<EOF
## Summary
Promote \`## Unreleased\` to \`## $VERSION — $DATE\` ahead of tagging.

## Release notes
$NOTES

## Test plan
- [ ] CI green on this branch.
- [ ] After merge: skill resumes at Stage 4 to tag \`$VERSION\` and publish the GitHub Release.
EOF
)"
   ```

4. Surface the PR URL and **stop**. Tell the user:
   > PR opened at `<url>`. Merge it (after CI and any review), then say "merged" / "已合入" and I'll pick up at Stage 4.

### Stage 4 · Tag + GitHub Release

Only enter this stage after the user confirms the PR is merged.

1. Sync the default branch and drop the local release branch:

   ```bash
   git switch "$DEFAULT_BRANCH"
   git pull --ff-only
   git branch -D "release/$VERSION"                     # local cleanup; merged branch
   ```

2. **Verify the tip carries the CHANGELOG bump** — this is the one check that catches "wrong PR merged" or "main moved again":

   ```bash
   grep -qE "^## $VERSION — $DATE\$" CHANGELOG.md       # must match
   git log --oneline -3                                 # sanity only
   ```

   If the grep fails, stop and surface to the user — do not tag.

3. Create the annotated tag on the current tip of `$DEFAULT_BRANCH` and push it:

   ```bash
   git tag -a "$VERSION" -m "$VERSION"
   git push origin "$VERSION"
   ```

4. Create the GitHub Release. Re-extract notes from `CHANGELOG.md` on `main` (not from the PR body — the PR body may have drifted if edits were made during review):

   ```bash
   NOTES=$(awk -v hdr="## $VERSION — $DATE" '
     $0 == hdr {on=1; next}
     /^## / && on {exit}
     on
   ' CHANGELOG.md)

   gh release create "$VERSION" \
     --title "$VERSION" \
     --notes "$NOTES" \
     --latest
   ```

### Stage 5 · Verify

```bash
gh release view "$VERSION" --json url,tagName,isLatest,publishedAt
gh release list --limit 3
git ls-remote --tags origin | grep "refs/tags/$VERSION\$"
```

Report to the user:

- **Release URL** from `gh release view --json url -q .url`.
- **Tag pushed** — confirmed via `ls-remote`.
- **Latest flag** — should be `true`.
- Reminder: README's `Latest release` shields.io badge will pick up `$VERSION` within a few minutes (shields has its own cache). No further action needed in this repo.

Announcement channels (Slack, Twitter, skillx directory listing, etc.) are explicitly out of scope for this skill.

## Recovery paths

None of the below is invoked automatically — they are here so you can quote them to the user if something goes wrong:

- **Wrong version tagged locally, not yet pushed**: `git tag -d $VERSION`, re-investigate, retry Stage 4.
- **Tag pushed but Release not yet created**: safe state; just run Stage 4 step 4. The tag alone is harmless.
- **Release notes wrong after publishing**: `gh release edit $VERSION --notes "$CORRECTED"`. Notes edit is non-destructive.
- **Wrong version number on a published Release, noticed immediately**: ask the user. A rename is usually better than a delete-and-recreate, because downstream consumers (shields.io, `gh release list`) have already cached the tag.
- **Release published to wrong commit**: `gh release delete $VERSION` + `git push --delete origin $VERSION` is destructive; **always** confirm with the user first.

## What this skill does NOT do

- **No direct push to protected branches.** CHANGELOG edits always PR.
- **No auto-bump without confirmation.** The version number is the one thing the user must sign off on.
- **No artifact uploads.** This repo's releases are source-only. If that changes, extend Stage 4 step 4 with `gh release upload`.
- **No multi-repo or monorepo awareness.** One repo per invocation.
- **No release-notes rewriting.** Whatever is in the CHANGELOG section becomes the Release notes verbatim. Polish the CHANGELOG, not this skill.
