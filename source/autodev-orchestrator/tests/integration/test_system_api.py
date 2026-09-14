from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from autodev.db.models import ProviderConfigRecord
from autodev.db.session import Database
from autodev.memory.base import MemoryItem, MemoryQuery
from autodev.providers.ollama import OllamaProvider


async def test_system_catalog_and_audit_endpoints(client: AsyncClient) -> None:
    created = await client.post(
        "/api/projects",
        json={"name": "system-api", "repository_path": "C:/system-api"},
    )
    project_id = created.json()["id"]

    providers = await client.get("/api/providers")
    models = await client.get("/api/models")
    health = await client.get("/api/providers/health")
    usage = await client.get("/api/model-usage")
    audit = await client.get("/api/audit", params={"project_id": project_id})

    assert providers.status_code == 200
    assert {"codex", "ollama", "openrouter"} <= {
        provider["name"] for provider in providers.json()
    }
    assert all("encrypted_api_key" not in provider for provider in providers.json())
    assert models.status_code == 200
    assert "codex/app-server" in {model["id"] for model in models.json()}
    assert health.status_code == 200
    assert usage.status_code == 200
    assert audit.status_code == 200
    assert audit.json()[0]["event"] == "project.created"


async def test_provider_key_is_encrypted_and_never_returned(
    client: AsyncClient, database: Database
) -> None:
    secret = "placeholder-fixture-key"
    response = await client.put(
        "/api/providers/openrouter",
        json={
            "kind": "openai_compatible",
            "enabled": True,
            "base_url": "https://openrouter.ai/api/v1",
            "api_key_env": "OPENROUTER_API_KEY",
            "api_key": secret,
            "billing_mode": "free",
            "accepts_private_code": False,
            "timeout_seconds": 60,
        },
    )

    assert response.status_code == 200
    assert response.json()["credential_configured"] is True
    assert secret not in response.text
    async with database.session() as session:
        record = await session.scalar(
            select(ProviderConfigRecord).where(ProviderConfigRecord.name == "openrouter")
        )
        assert record is not None
        assert record.encrypted_api_key
        assert record.encrypted_api_key != secret

    cleared = await client.delete("/api/providers/openrouter/credential")
    providers = await client.get("/api/providers")

    assert cleared.status_code == 204
    openrouter = next(item for item in providers.json() if item["name"] == "openrouter")
    assert openrouter["credential_configured"] is False


async def test_ollama_discovery_enables_real_model_selection(
    client: AsyncClient, monkeypatch: Any
) -> None:
    async def list_models(_provider: OllamaProvider) -> set[str]:
        return {"qwen2.5-coder:7b", "qwen3-embedding:0.6b"}

    monkeypatch.setattr(OllamaProvider, "list_models", list_models)
    discovered = await client.post("/api/models/discover", params={"provider": "ollama"})
    selected = await client.put(
        "/api/model-selection/implementation",
        json={"model_id": "ollama/qwen2.5-coder:7b"},
    )
    embedding_selected = await client.put(
        "/api/model-selection/embedding",
        json={"model_id": "ollama/qwen3-embedding:0.6b"},
    )
    models = await client.get("/api/models")

    assert discovered.status_code == 200
    assert "ollama/qwen2.5-coder:7b" in discovered.json()["models"]
    assert selected.status_code == 200
    assert selected.json() == {
        "role": "implementation",
        "model_id": "ollama/qwen2.5-coder:7b",
    }
    assert embedding_selected.status_code == 200
    coder = next(item for item in models.json() if item["id"] == "ollama/qwen2.5-coder:7b")
    embedding = next(
        item for item in models.json() if item["id"] == "ollama/qwen3-embedding:0.6b"
    )
    assert coder["installed"] is True
    assert coder["selected_for"] == ["implementation"]
    assert embedding["roles"] == ["embedding"]
    assert embedding["selected_for"] == ["embedding"]


async def test_missing_local_model_cannot_be_selected(client: AsyncClient) -> None:
    response = await client.put(
        "/api/model-selection/implementation",
        json={"model_id": "ollama/qwen2.5-coder:14b"},
    )

    assert response.status_code == 409


async def test_memory_search_endpoint_uses_configured_read_only_adapter(
    client: AsyncClient, monkeypatch: Any
) -> None:
    class FakeMemory:
        def __init__(self, base_url: str) -> None:
            assert base_url == "http://localhost:3111"

        async def search(self, query: MemoryQuery) -> list[MemoryItem]:
            assert query.project == "fixture"
            return [MemoryItem(id="memory-1", content="Use bounded retries", score=0.9)]

    monkeypatch.setattr("autodev.api.system.AgentMemoryHttpProvider", FakeMemory)
    response = await client.get(
        "/api/memory/search",
        params={"query": "retry", "project": "fixture", "limit": 3},
    )

    assert response.status_code == 200
    assert response.json()[0]["id"] == "memory-1"
