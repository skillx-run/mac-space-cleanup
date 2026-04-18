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
     valid JSON object (possibly empty for English runs); every dict
     key must appear as a `data-i18n` attribute in the template, and
     every template `data-i18n` key must exist in the canonical
     `assets/i18n/strings.json`.

Dry-run reports additionally require a structural marker: a sticky
`.dry-banner[data-dryrun="true"]` element and at least one
`<span class="dryrun-prefix">` somewhere in the document (typically
siblinging each headline number). Vocabulary is not matched because the
report is single-locale per run and may be written in any language.

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


# Canonical EN label dictionary. Resolved relative to this script so the
# validator works whether invoked from the project root or an absolute
# path. Tests may patch this module-level constant to point at a fixture.
_STRINGS_JSON_PATH = (
    Path(__file__).resolve().parent.parent / "assets" / "i18n" / "strings.json"
)

# Dry-run structural markers.
_DRY_RUN_BANNER_RE = re.compile(
    r'<[^>]+class="[^"]*\bdry-banner\b[^"]*"[^>]*\bdata-dryrun\s*=\s*"true"[^>]*>'
    r'|'
    r'<[^>]+\bdata-dryrun\s*=\s*"true"[^>]*class="[^"]*\bdry-banner\b[^"]*"[^>]*>',
    re.IGNORECASE,
)
_DRYRUN_PREFIX_RE = re.compile(
    r'<span\b[^>]*\bclass="[^"]*\bdryrun-prefix\b[^"]*"[^>]*>',
    re.IGNORECASE,
)

_I18N_DICT_RE = re.compile(
    r'<script\b[^>]*\bid="i18n-dict"[^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
# Pull every data-i18n="..."> key reference out of the rendered HTML.
# This is the set of keys the template asks the dict to fill.
_DATA_I18N_RE = re.compile(r'\bdata-i18n\s*=\s*"([^"]+)"')


def _load_strings_json_keys() -> tuple[set[str] | None, str | None]:
    """Read canonical strings.json. Returns (keys, error_detail).

    A missing or malformed canonical source is reported as a single
    violation so the rest of the validator can still run.
    """
    try:
        body = _STRINGS_JSON_PATH.read_text(encoding="utf-8")
    except OSError as e:
        return None, f"cannot read canonical strings.json: {e}"
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        return None, f"canonical strings.json not valid JSON: {e.msg}"
    if not isinstance(data, dict) or not all(isinstance(v, str) for v in data.values()):
        return None, "canonical strings.json must be a flat {key: string} object"
    return set(data.keys()), None


def _check_i18n_dict(html: str) -> list[dict[str, str]]:
    """Validate the inline i18n dictionary and its key alignment.

    Rules:
      - `<script id="i18n-dict">` must exist.
      - Body must parse as a JSON object mapping string → string. Empty
        `{}` is valid (English runs leave the dict empty).
      - Every key in the dict must correspond to a `data-i18n` attribute
        present in the rendered HTML (no stray keys).
      - Every `data-i18n` key in the rendered HTML must exist in the
        canonical `strings.json` (no template keys without a canonical
        EN source).
    """
    m = _I18N_DICT_RE.search(html)
    if not m:
        return [{
            "kind": "i18n_dict_malformed",
            "detail": 'missing <script id="i18n-dict"> block',
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
    if not all(isinstance(v, str) for v in data.values()):
        return [{
            "kind": "i18n_dict_malformed",
            "detail": "every dict value must be a string",
        }]

    template_keys = set(_DATA_I18N_RE.findall(html))
    violations: list[dict[str, str]] = []

    # Dict keys that the template does not reference → stray / stale.
    dict_keys = set(data.keys())
    stray = sorted(dict_keys - template_keys)
    if stray:
        violations.append({
            "kind": "i18n_dict_malformed",
            "detail": f"dict has keys absent from template data-i18n set: {stray}",
        })

    # Template keys must exist in canonical strings.json.
    canonical_keys, load_err = _load_strings_json_keys()
    if load_err:
        violations.append({
            "kind": "i18n_dict_malformed",
            "detail": load_err,
        })
    elif canonical_keys is not None:
        missing = sorted(template_keys - canonical_keys)
        if missing:
            violations.append({
                "kind": "template_key_missing_from_strings",
                "detail": (
                    "template data-i18n keys not in canonical strings.json: "
                    f"{missing}"
                ),
            })

    return violations


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

    # 4. i18n dict integrity.
    violations.extend(_check_i18n_dict(html))

    # 5. Dry-run structural marking (only when caller asserts a dry-run).
    if expect_dry_run:
        if not _DRY_RUN_BANNER_RE.search(html):
            violations.append({
                "kind": "dry_run_unmarked",
                "detail": (
                    'dry-run report missing .dry-banner[data-dryrun="true"] '
                    "element"
                ),
            })
        if not _DRYRUN_PREFIX_RE.search(html):
            violations.append({
                "kind": "dry_run_unmarked",
                "detail": (
                    'dry-run report missing <span class="dryrun-prefix"> '
                    "sibling on headline numbers"
                ),
            })

    return len(violations) == 0, violations


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="validate a rendered report.html")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="assert that the report visibly marks itself as a dry-run "
             '(.dry-banner[data-dryrun="true"] + .dryrun-prefix on numbers)',
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
