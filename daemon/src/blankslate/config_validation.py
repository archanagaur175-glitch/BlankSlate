"""Startup config validation.

The daemon previously failed silently (e.g. an unparseable hotkey just logged a
warning mid-run). This module checks the values the consuming libraries actually
accept and reports mismatches loudly at launch instead of degrading quietly.

Usage::

    from blankslate.config_validation import validate_config
    issues = validate_config(config)   # list of (level, message)
    for level, msg in issues:
        logging.log(level, "config: %s", msg)
"""
from __future__ import annotations

import logging

from blankslate.config import DaemonConfig
from blankslate.wake.openwakeword_engine import BUILTIN_MODELS

# Levels from the `logging` module so callers can route by severity.
Issue = tuple[int, str]


def validate_config(config: DaemonConfig) -> list[Issue]:
    issues: list[Issue] = []
    issues += _check_hotkey(config.dictation.hotkey)
    issues += _check_wake(config.wake.model)
    return issues


def _check_hotkey(hotkey: str) -> list[Issue]:
    if not hotkey:
        return []  # empty hotkey is allowed (push-to-talk UI still works)
    try:
        import keyboard
    except Exception:  # noqa: BLE001
        # Library missing entirely — that's a different (loud) failure elsewhere.
        return []
    try:
        # `parse_hotkey` validates the exact string the library will register.
        keyboard.parse_hotkey(hotkey)
    except Exception as exc:  # noqa: BLE001
        return [
            (
                logging.ERROR,
                f"Invalid hotkey {hotkey!r}: {exc}. Push-to-talk hotkey will be "
                f"disabled; use e.g. 'ctrl+alt+d'.",
            )
        ]
    return []


def _check_wake(model: str) -> list[Issue]:
    from pathlib import Path

    if model in BUILTIN_MODELS:
        return []
    if Path(model).exists():
        return []
    return [
        (
            logging.ERROR,
            f"Wake model {model!r} is neither a builtin ({', '.join(BUILTIN_MODELS)}) "
            f"nor an existing path; wake word will be disabled.",
        )
    ]


def fail_loudly(config: DaemonConfig) -> None:
    """Log every issue loudly; this is meant to run before the app starts."""
    for level, msg in validate_config(config):
        logging.log(level, "config validation: %s", msg)
