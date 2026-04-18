#!/usr/bin/env python3
"""validate_report.py — deterministic post-render check for report.html.

Three responsibilities:
  1. Structural: every paired region marker has been replaced with real
     content (no leftover `<p class="hint">` placeholder strings, no
     unfilled markers).
  2. Redaction: scan the rendered HTML for forbidden substrings — full
     paths, the current user's home prefix, common credential hints —
     that would leak data the agent should have abstracted into
     source_label.
  3. i18n integrity: the inline `<script id="i18n-dict">` must carry a
     valid JSON object with matching `en` / `zh` subtree key sets, and
     any `data-locale-show` span must be paired (en/zh counts equal)
     so the runtime toggle cannot reveal one-locale-only content.

This is a deterministic second line of defence behind the agent's own
discipline and the optional reviewer sub-agent. Failures from here mean
the report must be rewritten before being shown to the user.

stdin:  not used.
args:   --report PATH (required), --dry-run (assert dry-run UI marking present).
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

REGIONS = (
    "hero",
    "impact",
    "nextstep",
    "distribution",
    "actions",
    "observations",
    "runmeta",
    "share",
)

# Paired marker for each region, e.g. <!-- region:hero:start --> ... :end -->
_REGION_RE = {
    name: re.compile(
        rf"<!--\s*region:{name}:start\s*-->(.*?)<!--\s*region:{name}:end\s*-->",
        re.DOTALL,
    )
    for name in REGIONS
}

# Strings the template ships with that should never appear in a final
# rendered report (they mean a region was not filled).
_PLACEHOLDER_MARKERS = tuple(
    f'data-placeholder="{name}"' for name in REGIONS
) + ("Agent fills this block",)

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


_DRY_RUN_MARKERS = ("would be", "would-be", "(simulated)", "预计", "模拟")
_DRY_RUN_BANNER_RE = re.compile(
    r'<[^>]+class="[^"]*\bdry-banner\b[^"]*"[^>]*>',
    re.IGNORECASE,
)

_I18N_DICT_RE = re.compile(
    r'<script\b[^>]*\bid="i18n-dict"[^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
# Count data-locale-show="en" vs "zh" spans as a cheap sibling-pair
# sanity check. HTML is not strict XML so we don't try to pair by
# parent; equal totals catch the common "forgot to add the zh twin"
# regression with zero false positives for well-formed reports.
_LOCALE_SHOW_EN_RE = re.compile(r'\bdata-locale-show\s*=\s*"en"')
_LOCALE_SHOW_ZH_RE = re.compile(r'\bdata-locale-show\s*=\s*"zh"')


def _check_i18n_dict(html: str) -> list[dict[str, str]]:
    """Validate the inline i18n dictionary embedded in the report."""
    m = _I18N_DICT_RE.search(html)
    if not m:
        return [{
            "kind": "i18n_dict_malformed",
            "detail": "missing <script id=\"i18n-dict\"> block",
        }]
    body = m.group(1).strip()
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        return [{
            "kind": "i18n_dict_malformed",
            "detail": f"JSON parse error: {e.msg} at line {e.lineno}",
        }]
    if not isinstance(data, dict):
        return [{
            "kind": "i18n_dict_malformed",
            "detail": "top-level i18n dict is not a JSON object",
        }]
    missing = [k for k in ("en", "zh") if k not in data]
    if missing:
        return [{
            "kind": "i18n_dict_malformed",
            "detail": f"missing top-level key(s): {', '.join(missing)}",
        }]
    if not isinstance(data["en"], dict) or not isinstance(data["zh"], dict):
        return [{
            "kind": "i18n_dict_malformed",
            "detail": "'en' and 'zh' subtrees must be JSON objects",
        }]
    en_keys = set(data["en"].keys())
    zh_keys = set(data["zh"].keys())
    if en_keys != zh_keys:
        only_en = sorted(en_keys - zh_keys)
        only_zh = sorted(zh_keys - en_keys)
        detail_parts = []
        if only_en:
            detail_parts.append(f"only in en: {only_en}")
        if only_zh:
            detail_parts.append(f"only in zh: {only_zh}")
        return [{
            "kind": "i18n_dict_malformed",
            "detail": "en/zh key sets differ — " + "; ".join(detail_parts),
        }]
    return []


def _check_locale_pair_balance(html: str) -> list[dict[str, str]]:
    """Require equal counts of data-locale-show="en" and data-locale-show="zh"."""
    en_count = len(_LOCALE_SHOW_EN_RE.findall(html))
    zh_count = len(_LOCALE_SHOW_ZH_RE.findall(html))
    if en_count != zh_count:
        return [{
            "kind": "locale_unpaired",
            "detail": (
                f"data-locale-show en={en_count} zh={zh_count} — each "
                "bilingual node must ship both locales"
            ),
        }]
    return []


def validate(
    report_path: Path,
    expect_dry_run: bool = False,
) -> tuple[bool, list[dict[str, str]]]:
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

    # 4. i18n dict must exist with symmetric en/zh subtrees.
    violations.extend(_check_i18n_dict(html))

    # 5. Bilingual spans must be paired (equal en/zh counts).
    violations.extend(_check_locale_pair_balance(html))

    # 6. Dry-run marking (only when caller asserts the run was a dry-run).
    if expect_dry_run:
        if not _DRY_RUN_BANNER_RE.search(html):
            violations.append({
                "kind": "dry_run_unmarked",
                "detail": "dry-run report missing <... class=\"dry-banner\"> banner",
            })
        lower = html.lower()
        if not any(marker in lower for marker in _DRY_RUN_MARKERS):
            violations.append({
                "kind": "dry_run_unmarked",
                "detail": (
                    "dry-run report missing 'would be' / 'would-be' / "
                    "'(simulated)' marker on numeric headlines"
                ),
            })

    return len(violations) == 0, violations


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="validate a rendered report.html")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="assert that the report visibly marks itself as a dry-run "
             "(banner + 'would be' / '(simulated)' on numbers)",
    )
    args = parser.parse_args(argv)

    try:
        ok, violations = validate(args.report, expect_dry_run=args.dry_run)
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
