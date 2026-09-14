from __future__ import annotations

import asyncio
import time
from pathlib import Path

from pydantic import BaseModel

from autodev.security.command_policy import CommandPolicy


class CheckResult(BaseModel):
    command: list[str]
    exit_code: int
    output: str
    duration_seconds: float
    passed: bool


class CheckRunner:
    def __init__(
        self, *, policy: CommandPolicy | None = None, timeout_seconds: float = 600
    ) -> None:
        self._policy = policy or CommandPolicy()
        self._timeout_seconds = timeout_seconds

    async def run(self, repository: Path, commands: list[list[str]]) -> list[CheckResult]:
        results: list[CheckResult] = []
        for command in commands:
            results.append(await self.run_one(repository, command))
            if not results[-1].passed:
                break
        return results

    async def run_one(self, repository: Path, command: list[str]) -> CheckResult:
        if not self._policy.permits_check(command):
            return CheckResult(
                command=command,
                exit_code=126,
                output="command rejected by deterministic check policy",
                duration_seconds=0,
                passed=False,
            )
        started = time.monotonic()
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(repository),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=self._timeout_seconds)
            output = stdout.decode(errors="replace")[-64_000:]
            exit_code = process.returncode or 0
        except TimeoutError:
            if "process" in locals() and process.returncode is None:
                process.kill()
                await process.wait()
            output = f"check timed out after {self._timeout_seconds} seconds"
            exit_code = 124
        except OSError as error:
            output = f"unable to start check: {error}"
            exit_code = 127
        return CheckResult(
            command=command,
            exit_code=exit_code,
            output=output,
            duration_seconds=time.monotonic() - started,
            passed=exit_code == 0,
        )
