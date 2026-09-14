from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


class Redactor:
    _patterns = (
        re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+"),
        re.compile(r"(?i)((?:api[_-]?key|token|password|secret)\s*[:=]\s*)[^\s,;]+"),
        re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
        re.compile(r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\b"),
    )

    def __init__(self, secret_values: Iterable[str] = ()) -> None:
        self._secret_values = tuple(
            sorted({value for value in secret_values if len(value) >= 4}, key=len, reverse=True)
        )

    def text(self, value: str) -> str:
        redacted = value
        for secret in self._secret_values:
            redacted = redacted.replace(secret, "[REDACTED]")
        for pattern in self._patterns:
            redacted = pattern.sub(self._replacement, redacted)
        return redacted

    def data(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            return {
                key: "[REDACTED]" if self._sensitive_key(str(key)) else self.data(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.data(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.data(item) for item in value)
        return value

    @staticmethod
    def _sensitive_key(key: str) -> bool:
        normalized = key.casefold().replace("-", "_")
        return any(
            marker in normalized
            for marker in ("authorization", "api_key", "token", "password", "secret")
        )

    @staticmethod
    def _replacement(match: re.Match[str]) -> str:
        prefix = match.group(1) if match.lastindex else ""
        return f"{prefix}[REDACTED]"
