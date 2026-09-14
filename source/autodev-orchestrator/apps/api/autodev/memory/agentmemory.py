from __future__ import annotations

import os
from typing import Any, Protocol

import httpx

from autodev.memory.base import MemoryItem, MemoryQuery, MemoryRecord


class MemoryProviderError(RuntimeError):
    pass


class AgentMemoryHttpProvider:
    """AgentMemory REST adapter; core code does not depend on the npm package."""

    def __init__(
        self,
        base_url: str,
        *,
        secret_env: str = "AGENTMEMORY_SECRET",
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 15,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._secret_env = secret_env
        self._client = client
        self._timeout = timeout_seconds

    async def health(self) -> bool:
        try:
            response = await self._request("GET", "/agentmemory/livez")
            body = response.json()
            return response.status_code == 200 and body.get("status") == "ok"
        except (httpx.HTTPError, ValueError, MemoryProviderError):
            return False

    async def search(self, query: MemoryQuery) -> list[MemoryItem]:
        body: dict[str, Any] = {"query": query.query, "limit": query.limit}
        if query.project:
            body["project"] = query.project
        response = await self._request("POST", "/agentmemory/smart-search", json=body)
        self._ensure_success(response)
        payload = response.json()
        results = payload.get("results", [])
        return [self._to_item(result) for result in results if isinstance(result, dict)]

    async def store(self, item: MemoryRecord) -> str:
        concepts = list(dict.fromkeys([item.scope.value.casefold(), *item.concepts]))
        body: dict[str, Any] = {
            "content": item.content,
            "concepts": concepts,
            "type": item.memory_type,
        }
        if item.project:
            body["project"] = item.project
        if item.files:
            body["files"] = item.files
        response = await self._request("POST", "/agentmemory/remember", json=body)
        self._ensure_success(response, expected={200, 201})
        payload = response.json()
        memory_id = payload.get("id") or payload.get("memoryId") or payload.get("obsId")
        if not memory_id:
            raise MemoryProviderError("AgentMemory remember response did not include an id")
        return str(memory_id)

    async def _request(
        self, method: str, path: str, *, json: dict[str, Any] | None = None
    ) -> httpx.Response:
        headers: dict[str, str] = {}
        secret = os.getenv(self._secret_env)
        if secret:
            headers["authorization"] = f"Bearer {secret}"
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns_client = self._client is None
        try:
            return await client.request(
                method, f"{self._base_url}{path}", json=json, headers=headers
            )
        except httpx.HTTPError as error:
            raise MemoryProviderError(
                f"AgentMemory transport failed: {type(error).__name__}"
            ) from error
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    def _ensure_success(response: httpx.Response, *, expected: set[int] | None = None) -> None:
        allowed = expected or {200}
        if response.status_code not in allowed:
            raise MemoryProviderError(
                f"AgentMemory returned HTTP {response.status_code}: {response.text[-1000:]}"
            )

    @staticmethod
    def _to_item(value: dict[str, Any]) -> MemoryItem:
        memory_id = value.get("obsId") or value.get("id") or value.get("memoryId")
        if not memory_id:
            raise MemoryProviderError("AgentMemory search result did not include an id")
        content = value.get("content") or value.get("title") or ""
        known = {"obsId", "id", "memoryId", "content", "title", "score", "sessionId"}
        return MemoryItem(
            id=str(memory_id),
            content=str(content),
            score=float(value["score"]) if value.get("score") is not None else None,
            session_id=str(value["sessionId"]) if value.get("sessionId") else None,
            metadata={key: item for key, item in value.items() if key not in known},
        )


class McpTransport(Protocol):
    async def call(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class McpMemoryProvider:
    """MCP bridge for hosts that expose AgentMemory tools directly."""

    def __init__(self, transport: McpTransport) -> None:
        self._transport = transport

    async def search(self, query: MemoryQuery) -> list[MemoryItem]:
        result = await self._transport.call(
            "memory_smart_search", {"query": query.query, "limit": query.limit}
        )
        values = result.get("results", [])
        return [
            AgentMemoryHttpProvider._to_item(value) for value in values if isinstance(value, dict)
        ]

    async def store(self, item: MemoryRecord) -> str:
        arguments: dict[str, Any] = {
            "content": item.content,
            "concepts": ",".join([item.scope.value.casefold(), *item.concepts]),
            "type": item.memory_type,
        }
        if item.project:
            arguments["project"] = item.project
        if item.files:
            arguments["files"] = ",".join(item.files)
        result = await self._transport.call("memory_save", arguments)
        memory_id = result.get("id") or result.get("memoryId") or result.get("obsId")
        if not memory_id:
            raise MemoryProviderError("AgentMemory MCP save response did not include an id")
        return str(memory_id)
