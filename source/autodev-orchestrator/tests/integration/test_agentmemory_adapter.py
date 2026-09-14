from __future__ import annotations

import json

import httpx

from autodev.memory.agentmemory import AgentMemoryHttpProvider
from autodev.memory.base import MemoryQuery, MemoryRecord, MemoryScope


async def test_http_adapter_searches_and_stores_using_public_contract() -> None:
    requests: list[tuple[str, str, dict[str, object] | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        requests.append((request.method, request.url.path, body))
        if request.url.path.endswith("/smart-search"):
            return httpx.Response(
                200,
                json={
                    "mode": "compact",
                    "results": [
                        {
                            "obsId": "obs-1",
                            "title": "Use SKIP LOCKED",
                            "score": 0.9,
                            "sessionId": "session-1",
                        }
                    ],
                },
            )
        return httpx.Response(201, json={"id": "memory-1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = AgentMemoryHttpProvider("http://memory.test", client=client)
        items = await provider.search(
            MemoryQuery(query="durable scheduler", project="autodev", limit=3)
        )
        memory_id = await provider.store(
            MemoryRecord(
                content="Use PostgreSQL SKIP LOCKED for claims.",
                scope=MemoryScope.DECISION,
                project="autodev",
                concepts=["scheduler"],
                files=["apps/api/autodev/orchestration/scheduler.py"],
                memory_type="architecture",
            )
        )

    assert items[0].id == "obs-1"
    assert items[0].content == "Use SKIP LOCKED"
    assert memory_id == "memory-1"
    assert requests[0] == (
        "POST",
        "/agentmemory/smart-search",
        {"query": "durable scheduler", "limit": 3, "project": "autodev"},
    )
    assert requests[1][2] == {
        "content": "Use PostgreSQL SKIP LOCKED for claims.",
        "concepts": ["decision", "scheduler"],
        "type": "architecture",
        "project": "autodev",
        "files": ["apps/api/autodev/orchestration/scheduler.py"],
    }


async def test_http_adapter_health_uses_livez() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/agentmemory/livez"
        return httpx.Response(200, json={"service": "agentmemory", "status": "ok"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await AgentMemoryHttpProvider("http://memory.test", client=client).health()
