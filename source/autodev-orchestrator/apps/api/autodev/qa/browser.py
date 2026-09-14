from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import urlparse

from pydantic import BaseModel, Field


class BrowserAction(BaseModel):
    command: Literal[
        "click",
        "dblclick",
        "fill",
        "type",
        "press",
        "hover",
        "select",
        "check",
        "uncheck",
    ]
    target: str | None = None
    value: str | None = None

    def arguments(self) -> list[str]:
        if self.command in {"type", "press"}:
            if self.value is None:
                raise ValueError(f"browser action {self.command} requires value")
            return [self.command, self.value]
        if self.target is None:
            raise ValueError(f"browser action {self.command} requires target")
        arguments = [self.command, self.target]
        if self.command in {"fill", "select"}:
            if self.value is None:
                raise ValueError(f"browser action {self.command} requires value")
            arguments.append(self.value)
        return arguments


class BrowserFlow(BaseModel):
    url: str
    ready_text: str | None = None
    actions: list[BrowserAction] = Field(default_factory=list)


class CliResult(BaseModel):
    exit_code: int
    output: str = ""


class CliExecutor(Protocol):
    async def run(self, command: list[str], *, cwd: Path) -> CliResult: ...


class SubprocessCliExecutor:
    async def run(self, command: list[str], *, cwd: Path) -> CliResult:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await process.communicate()
        return CliResult(
            exit_code=process.returncode or 0,
            output=stdout.decode(errors="replace")[-64_000:],
        )


class BrowserQaResult(BaseModel):
    passed: bool
    commands_run: list[str]
    console_errors: list[str]
    failed_requests: list[str]
    artifacts: list[str]
    output: str


class PlaywrightCliRunner:
    def __init__(
        self,
        artifact_root: Path,
        *,
        command_prefix: list[str] | None = None,
        executor: CliExecutor | None = None,
    ) -> None:
        self.artifact_root = artifact_root.resolve()
        self.command_prefix = command_prefix or [
            "npx",
            "--yes",
            "--package",
            "@playwright/cli",
            "playwright-cli",
        ]
        self.executor = executor or SubprocessCliExecutor()

    async def run(self, flow: BrowserFlow, *, run_id: str | None = None) -> BrowserQaResult:
        self._validate_url(flow.url)
        safe_run_id = self._safe_run_id(run_id or uuid.uuid4().hex)
        artifact_directory = await asyncio.to_thread(self._prepare_directory, safe_run_id)
        session = f"autodev-{safe_run_id}"
        commands_run: list[str] = []
        outputs: list[str] = []
        failures: list[str] = []

        async def invoke(*arguments: str, required: bool = True) -> CliResult:
            command = [*self.command_prefix, f"-s={session}", *arguments]
            commands_run.append(" ".join(arguments))
            result = await self.executor.run(command, cwd=artifact_directory)
            outputs.append(result.output)
            if required and (result.exit_code != 0 or "### Error" in result.output):
                failures.append(f"{' '.join(arguments)}: exit {result.exit_code}")
            return result

        opened = False
        console_output = ""
        network_output = ""
        try:
            open_result = await invoke("open", flow.url)
            opened = open_result.exit_code == 0 and "### Error" not in open_result.output
            if opened:
                await invoke("tracing-start")
                await invoke("snapshot")
                if flow.ready_text:
                    await invoke("find", flow.ready_text)
                for action in flow.actions:
                    await invoke(*action.arguments())
                    if action.command in {"click", "dblclick", "press", "select"}:
                        await invoke("snapshot")
                console_output = (await invoke("console", "error", required=False)).output
                network_output = (await invoke("requests", required=False)).output
                await invoke("screenshot", required=False)
                await invoke("tracing-stop", required=False)
        finally:
            if opened:
                await invoke("close", required=False)

        console_errors = self._extract_console_errors(console_output)
        failed_requests = self._extract_failed_requests(network_output)
        artifacts = await asyncio.to_thread(self._artifacts, artifact_directory)
        combined_output = "\n".join(outputs)[-64_000:]
        return BrowserQaResult(
            passed=not failures and not console_errors and not failed_requests,
            commands_run=commands_run,
            console_errors=console_errors,
            failed_requests=failed_requests,
            artifacts=artifacts,
            output=combined_output,
        )

    def _prepare_directory(self, run_id: str) -> Path:
        path = (self.artifact_root / run_id).resolve()
        try:
            path.relative_to(self.artifact_root)
        except ValueError as error:
            raise ValueError(f"browser artifact path escapes root: {path}") from error
        path.mkdir(parents=True, exist_ok=False)
        return path

    @staticmethod
    def _artifacts(path: Path) -> list[str]:
        allowed = {".network", ".pdf", ".png", ".trace", ".webm", ".zip"}
        return sorted(str(item) for item in path.rglob("*") if item.suffix.casefold() in allowed)

    @staticmethod
    def _validate_url(value: str) -> None:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("browser flow URL must be absolute HTTP(S)")

    @staticmethod
    def _safe_run_id(value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", value) or ".." in value:
            raise ValueError(f"invalid browser QA run id: {value}")
        return value

    @staticmethod
    def _extract_console_errors(output: str) -> list[str]:
        lowered = output.casefold()
        if not output or "no console messages" in lowered or "total messages: 0" in lowered:
            return []
        return [
            line[:1000]
            for line in output.splitlines()
            if "error" in line.casefold() and not re.search(r"errors?:\s*0\b", line, re.I)
        ]

    @staticmethod
    def _extract_failed_requests(output: str) -> list[str]:
        return [
            line[:1000]
            for line in output.splitlines()
            if "failed" in line.casefold()
            or "net::err_" in line.casefold()
            or re.search(r"\b[45]\d{2}\b", line)
        ]
