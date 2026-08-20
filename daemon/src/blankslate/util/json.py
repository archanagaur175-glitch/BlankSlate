"""Small JSON helpers for tolerating imperfect LLM output."""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json(text: str) -> Any | None:
    """Extract the first balanced JSON value (object or array) from ``text``.

    Small local models frequently wrap JSON in prose or code fences; this
    scans for the outermost ``{...}`` or ``[...]`` and parses it.
    """
    if not text:
        return None
    for start_ch, end_ch in (("{", "}"), ("[", "]")):
        start = _find_open(text, start_ch)
        if start < 0:
            continue
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == start_ch:
                depth += 1
            elif ch == end_ch:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        return None
    return None


def _find_open(text: str, target: str) -> int:
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == target:
            return i
    return -1


def extract_json_object(text: str) -> dict | None:
    parsed = extract_json(text)
    return parsed if isinstance(parsed, dict) else None


def strip_code_fences(text: str) -> str:
    return re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text.strip()).strip()
