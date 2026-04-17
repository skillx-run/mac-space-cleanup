#!/usr/bin/env python3
"""validate_report.py — deterministic post-render check for report.html.

Two responsibilities:
  1. Structural: every paired region marker has been replaced with real
     content (no leftover `<p class="hint">` placeholder strings, no
     unfilled markers).
  2. Redaction: scan the rendered HTML for forbidden substrings — full
     paths, the current user's home prefix, common credential hints — that
     would leak data the agent should have abstracted into source_label.

This is a deterministic second line of defence behind the agent's own
discipline and the optional reviewer sub-agent. Failures from here mean
the report must be rewritten before being shown to the user.

stdin:  not used.
args:   --report PATH (required).
stdout: {"ok": bool, "violations": [...], "summary": "..."}
exit:   0 = ok, 1 = violations, 2 = bad input.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
from pathlib import Path

REGIONS = ("summary", "distribution", "actions", "deferred", "nextstep", "share")

# Paired marker for each region, e.g. <!-- region:summary:start --> ... :end -->
_REGION_RE = {
    name: re.compile(
        rf"<!--\s*region:{name}:start\s*-->(.*?)<!--\s*region:{name}:end\s*-->",
        re.DOTALL,
    )
    for name in REGIONS
}

# Strings the template ships with that should never appear in a final
# rendered report (they mean a region was not filled).
_PLACEHOLDER_MARKERS = (
    'data-placeholder="summary"',
    'data-placeholder="distribution"',
    'data-placeholder="actions"',
    'data-placeholder="deferred"',
    'data-placeholder="nextstep"',
    'data-placeholder="share"',
    "Agent fills this block",
)

# Forbidden substrings (exact case-sensitive match) — paths, secrets.
# Username and absolute home prefix are added at runtime from $HOME.
_FORBIDDEN_LITERAL_FRAGMENTS = (
    "/Users/",
    "/Volumes/",
    "/private/var/",
    ".env",
    "id_rsa",
    "id_ed25519",
    "BEGIN PRIVATE KEY",
    "BEGIN OPENSSH PRIVATE KEY",
)


def _runtime_forbidden() -> list[str]:
    """User-specific forbidden strings derived from the current environment."""
    out: list[str] = []
    home = os.path.expanduser("~")
    if home and home != "/":
        out.append(home)
    try:
        username = getpass.getuser()
    except Exception:
        username = ""
    if username and len(username) >= 3:
        out.append(username)
    return out


def validate(report_path: Path) -> tuple[bool, list[dict[str, str]]]:
    if not report_path.exists():
        return False, [{"kind": "missing_file", "detail": str(report_path)}]

    html = report_path.read_text(encoding="utf-8", errors="replace")
    violations: list[dict[str, str]] = []

    # 1. Each region must be present and non-empty.
    for name, regex in _REGION_RE.items():
        m = regex.search(html)
        if not m:
            violations.append({"kind": "missing_region", "region": name,
                               "detail": "paired markers not found"})
            continue
        body = m.group(1).strip()
        if not body:
            violations.append({"kind": "empty_region", "region": name,
                               "detail": "between markers is empty"})

    # 2. No template placeholders survive.
    for marker in _PLACEHOLDER_MARKERS:
        if marker in html:
            violations.append({"kind": "placeholder_left",
                               "detail": f"contains: {marker!r}"})

    # 3. Redaction: literal forbidden fragments.
    forbidden = list(_FORBIDDEN_LITERAL_FRAGMENTS) + _runtime_forbidden()
    for fragment in forbidden:
        if fragment and fragment in html:
            violations.append({"kind": "leaked_fragment",
                               "detail": f"contains: {fragment!r}"})

    return len(violations) == 0, violations


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="validate a rendered report.html")
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        ok, violations = validate(args.report)
    except OSError as e:
        print(json.dumps({"ok": False, "violations": [],
                          "summary": f"could not read: {e}"}))
        return 2

    summary = "ok" if ok else f"{len(violations)} violation(s)"
    out = {"ok": ok, "violations": violations, "summary": summary}
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())
