"""Shared test helpers for mac-space-cleanup unit tests.

Each script under scripts/ exposes a `run(argv)` entry point that reads
JSON from stdin (when applicable) and writes JSON to stdout. The helpers
below abstract the stdin/stdout/stderr mock dance so each test only
spells out its inputs and assertions.
"""

from __future__ import annotations

import io
import json
import sys
from typing import Any
from unittest import mock


def run_script(
    script_module: Any,
    argv: list[str],
    stdin_payload: str | None = None,
) -> tuple[int, dict | list, str]:
    """Invoke `script_module.run(argv)` with stdin/stdout/stderr mocked.

    Args:
        script_module: imported module exposing a `run(argv)` callable.
        argv: argument list passed to run().
        stdin_payload: raw string sent to stdin. Pass None for scripts
            that ignore stdin.

    Returns:
        (exit_code, parsed_stdout_object, stderr_text).
        parsed_stdout_object is the JSON-decoded stdout, or
        {"_raw": <text>} if stdout was not valid JSON.
    """
    stdin = io.StringIO(stdin_payload if stdin_payload is not None else "")
    stdout = io.StringIO()
    stderr = io.StringIO()
    with mock.patch.object(sys, "stdin", stdin), \
         mock.patch.object(sys, "stdout", stdout), \
         mock.patch.object(sys, "stderr", stderr):
        exit_code = script_module.run(argv)
    text = stdout.getvalue()
    try:
        obj: dict | list = json.loads(text)
    except json.JSONDecodeError:
        obj = {"_raw": text}
    return exit_code, obj, stderr.getvalue()


def run_script_with_json(
    script_module: Any,
    argv: list[str],
    payload: dict | list,
) -> tuple[int, dict | list, str]:
    """Convenience wrapper: dump payload to JSON and invoke run_script."""
    return run_script(script_module, argv, json.dumps(payload))
