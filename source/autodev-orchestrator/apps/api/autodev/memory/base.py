from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field


class MemoryScope(StrEnum):
    GLOBAL = "GLOBAL"
    PROJECT = "PROJECT"
    DECISION = "DECISION"
    EXPERIENCE = "EXPERIENCE"
    INCIDENT = "INCIDENT"


class MemoryQuery(BaseModel):
    query: str = Field(min_length=1)
    project: str | None = None
    limit: int = Field(default=5, ge=1, le=50)


class MemoryRecord(BaseModel):
    content: str = Field(min_length=1, max_length=50_000)
    scope: MemoryScope
    concepts: list[str] = Field(default_factory=list)
    project: str | None = None
    files: list[str] = Field(default_factory=list)
    memory_type: str = "fact"


class MemoryItem(BaseModel):
    id: str
    content: str
    score: float | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryProvider(Protocol):
    async def search(self, query: MemoryQuery) -> list[MemoryItem]: ...

    async def store(self, item: MemoryRecord) -> str: ...
