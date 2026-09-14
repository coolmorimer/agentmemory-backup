from __future__ import annotations

import uuid
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field


class CodingTask(BaseModel):
    task_id: uuid.UUID
    key: str
    title: str
    description: str
    repository_path: Path
    acceptance_criteria: list[str] = Field(default_factory=list)
    required_checks: list[list[str]] = Field(default_factory=list)
    context: str = ""
    network_access: Literal["none", "package_registry", "allowlist", "unrestricted"] = "none"
    thread_id: str | None = None


class CommandExecution(BaseModel):
    command: str
    cwd: str
    status: str
    exit_code: int | None = None
    output: str = ""


class CodingResult(BaseModel):
    status: Literal["completed", "failed", "interrupted"]
    summary: str = ""
    changed_files: list[str] = Field(default_factory=list)
    command_executions: list[CommandExecution] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    follow_up_tasks: list[str] = Field(default_factory=list)
    thread_id: str | None = None
    turn_id: str | None = None
    error: str | None = None


class CodingAgent(Protocol):
    async def run_task(self, task: CodingTask) -> CodingResult: ...
