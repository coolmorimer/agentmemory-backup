from __future__ import annotations

from httpx import AsyncClient

from autodev.db.models import ModelHealthRecord, ModelUsageRecord, ProviderQuotaSnapshot
from autodev.db.session import Database


async def test_dashboard_exposes_summary_and_prometheus_metrics(client: AsyncClient) -> None:
    created = await client.post(
        "/api/projects",
        json={"name": "dashboard", "repository_path": "C:/dashboard"},
    )
    assert created.status_code == 201

    summary = await client.get("/api/dashboard/summary")
    assert summary.status_code == 200
    assert summary.json()["projects"] == {"CREATED": 1}
    assert summary.json()["tasks"] == {}

    metrics = await client.get("/api/dashboard/metrics")
    assert metrics.status_code == 200
    assert "autodev_tasks_total 0" in metrics.text
    assert metrics.headers["content-type"].startswith("text/plain")


async def test_dashboard_aggregates_model_statistics(
    client: AsyncClient, database: Database
) -> None:
    async with database.session() as session:
        session.add_all(
            [
                ModelUsageRecord(
                    provider="ollama",
                    model="qwen3",
                    prompt_version="v1",
                    status="COMPLETED",
                    total_tokens=120,
                    latency_seconds=2,
                ),
                ModelUsageRecord(
                    provider="ollama",
                    model="qwen3",
                    prompt_version="v1",
                    status="FAILED",
                    total_tokens=20,
                    latency_seconds=4,
                ),
                ModelHealthRecord(provider="ollama", model="qwen3", state="DEGRADED"),
                ProviderQuotaSnapshot(
                    provider="ollama",
                    model="qwen3",
                    window="rolling",
                    requests_remaining=7,
                ),
            ]
        )
        await session.commit()

    response = await client.get("/api/dashboard/models")
    assert response.status_code == 200
    assert response.json() == [
        {
            "provider": "ollama",
            "model": "qwen3",
            "calls": 2,
            "success_rate": 0.5,
            "average_latency_seconds": 3.0,
            "tokens": 140,
            "health": "DEGRADED",
            "requests_remaining": 7,
            "reset_at": None,
        }
    ]
