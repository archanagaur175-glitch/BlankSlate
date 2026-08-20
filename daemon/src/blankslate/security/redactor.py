"""Secret / PII redaction applied at every persistence boundary."""

from __future__ import annotations

import re

_PATTERNS: list[tuple[str, str]] = [
    (
        "email",
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    ),
    ("phone", r"\b(\+?\d[\d\s().-]{7,})\b"),
    ("ssn", r"\b\d{3}-\d{2}-\d{4}\b"),
    ("credit_card", r"\b(?:\d[ -]*?){13,16}\b"),
    ("ip", r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    ("api_key", r"\b(sk|pk|ghp|AKIA|AIza)[-_A-Za-z0-9]{20,}\b"),
    ("aws_secret", r"(?i)\b[A-Za-z0-9/+=]{40}\b"),
    ("password_field", r"(?i)(password|passwd|secret|token|apikey)\s*[=:]\s*['\"]?[^\s'\"&]+"),
]


class Redactor:
    def __init__(
        self,
        enabled: bool = True,
        extra_patterns: list[str] | None = None,
        placeholder_prefix: str = "redacted",
    ) -> None:
        self.enabled = enabled
        self.placeholder_prefix = placeholder_prefix
        self._compiled: list[tuple[str, re.Pattern[str]]] = []
        for label, pattern in _PATTERNS:
            self._add(label, pattern)
        for i, raw in enumerate(extra_patterns or []):
            try:
                self._add(f"extra_{i}", raw)
            except re.error:
                continue

    def _add(self, label: str, pattern: str) -> None:
        self._compiled.append((label, re.compile(pattern)))

    def redact(self, text: str | None) -> str:
        if not text or not self.enabled:
            return text or ""
        out = text
        for label, pattern in self._compiled:
            out = pattern.sub(f"<{self.placeholder_prefix}_{label}>", out)
        return out

    def redact_dict(self, data: dict | list) -> dict | list:
        if isinstance(data, dict):
            return {key: self._redact_value(value) for key, value in data.items()}
        if isinstance(data, list):
            return [self._redact_value(value) for value in data]
        return data

    def _redact_value(self, value: object) -> object:
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, dict):
            return self.redact_dict(value)
        if isinstance(value, list):
            return self.redact_dict(value)
        return value
