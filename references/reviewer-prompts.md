# Reviewer Sub-agent Prompts

When the SKILL.md workflow says "spawn a reviewer", use the `Agent` tool (or whatever sub-agent invocation the host runtime provides) with one of the prompts below. Reviewer sub-agents run in a **fresh context**: they do not see your conversation. The prompt must be self-contained.

Two principles for every reviewer call:

1. **Independence**: pass the artefact verbatim, not your interpretation of it. The reviewer's job is to disagree with you when you missed something.
2. **Bounded retries**: if the reviewer rejects your output, fix the specific items it called out and re-spawn. Cap at **2 retries**. After the second failure, escalate to the user — do not loop or quietly ship the bad output.

## Redaction reviewer (Stage 6)

Used after the agent has filled `$WORKDIR/report.html`. Goal: catch any leak of paths, basenames, usernames, project names, company names, or credential-like substrings.

**Inputs to the sub-agent**: the contents of `$WORKDIR/report.html`.

**Prompt template** (substitute `{html_contents}`):

```
You are a privacy reviewer for a macOS cleanup report. The agent that produced
this HTML was instructed to render only category names ("Xcode DerivedData",
"Docker build cache", etc.) and aggregate sizes — never filesystem paths,
basenames, system usernames, project names, company names, or strings that
look like credentials (.env, id_rsa, BEGIN PRIVATE KEY, etc.).

Your job is to scan the HTML below and report every leak you find. You are
adversarial — assume the agent missed things. Look at every text node, every
attribute value, every comment.

Return a single JSON object with this shape:
{
  "violations": [
    {
      "kind": "path" | "username" | "project" | "company" | "credential" | "other",
      "snippet": "<the exact offending substring, ≤80 chars>",
      "where": "<short hint where in the document, e.g. 'distribution card #2'>",
      "why": "<one sentence explaining the leak>"
    }
  ]
}

Empty list = clean. Do not include fields you did not find. Do not editorialise
in prose; the JSON is the entire response.

HTML to review:
---
{html_contents}
---
```

**Acceptance**: parse the response as JSON. If `violations` is empty list, the report passes. Otherwise:

- For each violation, edit `$WORKDIR/report.html` to remove or abstract the leaked content (replace the snippet with a generic source_label or drop it).
- Re-run the redaction reviewer (with the updated HTML).
- After 2 failed retries, stop and tell the user which violations remained — do not show or share the report.

**Why also keep `validate_report.py`**: the validator is deterministic — it catches `/Users/`, the running user's home prefix, and a fixed credential dictionary. The reviewer is fuzzy — it catches things like "Acme Corp" or "secret-plan-2026" that no static rule can know about. Both run; both must pass.

## Future reviewers (placeholder, not yet wired)

- **Classification reviewer (Stage 4)** — would re-derive risk_level/category for each item from `references/category-rules.md` and flag mismatches with the agent's draft. Postponed; the deterministic blocklist in `safe_delete.py` (`_BLOCKED_PATTERNS`) is the current safety net for misclassification.
