from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from autodev.deployment.base import (
    DeploymentError,
    DeploymentRequest,
    DeploymentResult,
    DeploymentVerification,
    VerificationCheck,
)


class CommandResult(BaseModel):
    exit_code: int
    output: str = ""


class ControlledExecutor(Protocol):
    async def run(
        self, command: list[str], *, cwd: Path, environment: dict[str, str]
    ) -> CommandResult: ...


class LocalControlledExecutor:
    async def run(
        self, command: list[str], *, cwd: Path, environment: dict[str, str]
    ) -> CommandResult:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(cwd),
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await process.communicate()
        return CommandResult(
            exit_code=process.returncode or 0,
            output=stdout.decode(errors="replace")[-64_000:],
        )


class DockerComposeDeploymentAdapter:
    name = "docker-compose"

    def __init__(
        self,
        project_path: Path,
        *,
        compose_file: str = "compose.yaml",
        release_env_var: str = "AUTODEV_RELEASE_REF",
        executor: ControlledExecutor,
        base_environment: dict[str, str] | None = None,
    ) -> None:
        self.project_path = project_path.resolve()
        self.compose_file = self._safe_compose_path(compose_file)
        self.release_env_var = release_env_var
        self.executor = executor
        self.base_environment = base_environment or dict(os.environ)

    async def deploy(self, request: DeploymentRequest) -> DeploymentResult:
        result = await self._compose(
            ["up", "-d", "--remove-orphans"], release_ref=request.release_ref
        )
        if result.exit_code:
            raise DeploymentError(f"docker compose deploy failed: {result.output[-4000:]}")
        return DeploymentResult(
            external_id=f"compose:{request.environment}:{request.release_ref}",
            release_ref=request.release_ref,
            previous_release_ref=_metadata_string(request, "previous_release_ref"),
            detail=result.output,
        )

    async def verify(
        self, request: DeploymentRequest, deployment: DeploymentResult
    ) -> DeploymentVerification:
        del request
        result = await self._compose(
            ["ps", "--status", "running", "--services"],
            release_ref=deployment.release_ref,
        )
        return DeploymentVerification(
            checks=[
                VerificationCheck(
                    name="docker-compose-running",
                    passed=result.exit_code == 0 and bool(result.output.strip()),
                    detail=result.output[-4000:],
                )
            ]
        )

    async def rollback(
        self, request: DeploymentRequest, deployment: DeploymentResult
    ) -> DeploymentResult:
        del request
        previous = deployment.previous_release_ref
        if not previous:
            raise DeploymentError("docker compose rollback has no previous release")
        result = await self._compose(["up", "-d", "--remove-orphans"], release_ref=previous)
        if result.exit_code:
            raise DeploymentError(f"docker compose rollback failed: {result.output[-4000:]}")
        return DeploymentResult(
            external_id=f"compose:rollback:{previous}",
            release_ref=previous,
            previous_release_ref=deployment.release_ref,
            detail=result.output,
        )

    async def collect_logs(self, request: DeploymentRequest, deployment: DeploymentResult) -> str:
        del request
        result = await self._compose(
            ["logs", "--no-color", "--tail", "200"],
            release_ref=deployment.release_ref,
        )
        return result.output[-16_000:]

    async def _compose(self, arguments: list[str], *, release_ref: str) -> CommandResult:
        environment = {**self.base_environment, self.release_env_var: release_ref}
        return await self.executor.run(
            ["docker", "compose", "-f", str(self.compose_file), *arguments],
            cwd=self.project_path,
            environment=environment,
        )

    def _safe_compose_path(self, value: str) -> Path:
        path = (self.project_path / value).resolve()
        try:
            path.relative_to(self.project_path)
        except ValueError as error:
            raise ValueError(f"compose file escapes project path: {value}") from error
        return path


def _metadata_string(request: DeploymentRequest, key: str) -> str | None:
    value = request.metadata.get(key)
    return str(value) if value is not None else None
