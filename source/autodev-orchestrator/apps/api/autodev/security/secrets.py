from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel


class SecretFinding(BaseModel):
    path: str
    line: int | None = None
    kind: str


class SecretScanner:
    _patterns: ClassVar[tuple[tuple[str, re.Pattern[str]], ...]] = (
        ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
        ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
        ("openai-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
        ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
        ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
        (
            "authorization-header",
            re.compile(r"(?i)authorization\s*[:=]\s*bearer\s+[A-Za-z0-9._~+/-]{12,}"),
        ),
        (
            "credential-assignment",
            re.compile(
                r"(?i)(?:api[_-]?key|password|secret|access[_-]?token)\s*[:=]\s*"
                r"['\"]?(?!\$\{|<|placeholder|change-me|example|none|null)[A-Za-z0-9._~+/-]{12,}"
            ),
        ),
    )

    def scan_diff(self, diff: str) -> list[SecretFinding]:
        findings: list[SecretFinding] = []
        current_path = "unknown"
        current_line: int | None = None
        for raw_line in diff.splitlines():
            if raw_line.startswith("+++ b/"):
                current_path = raw_line[6:]
                if Path(current_path).name == ".env":
                    findings.append(SecretFinding(path=current_path, kind="dotenv-file"))
                continue
            if raw_line.startswith("@@"):
                match = re.search(r"\+(\d+)", raw_line)
                current_line = int(match.group(1)) if match else None
                continue
            if not raw_line.startswith("+") or raw_line.startswith("+++"):
                continue
            content = raw_line[1:]
            for kind, pattern in self._patterns:
                if pattern.search(content):
                    findings.append(SecretFinding(path=current_path, line=current_line, kind=kind))
            if current_line is not None:
                current_line += 1
        return findings
