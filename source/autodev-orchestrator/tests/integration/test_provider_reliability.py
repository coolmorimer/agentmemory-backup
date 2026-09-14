from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select

from autodev.db.models import ModelHealthRecord, ModelUsageRecord, ProviderQuotaSnapshot
from autodev.db.session import Database
from autodev.providers.base import ModelMessage, ModelRequest
from autodev.providers.openai_compatible import OpenAICompatibleProvider
from autodev.providers.registry import ProviderRegistry
from autodev.providers.reliability import (
    AllProvidersUnavailable,
    ProviderCandidate,
    ReliableProviderGateway,
    quota_from_headers,
)


async def test_429_enters_durable_cooldown_and_falls_back(database: Database) -> None:
    calls = {"limited": 0, "fallback": 0}

    async def limited_handler(_request: httpx.Request) -> httpx.Response:
        calls["limited"] += 1
        return httpx.Response(
            429,
            text="slow down",
            headers={
                "retry-after": "60",
                "x-ratelimit-remaining-requests": "0",
                "x-ratelimit-reset-requests": "60s",
            },
        )

    async def fallback_handler(_request: httpx.Request) -> httpx.Response:
        calls["fallback"] += 1
        return httpx.Response(
            200,
            headers={"x-ratelimit-remaining-requests": "9"},
            json={
                "model": "safe-model",
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            },
        )

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(limited_handler)) as limited_client,
        httpx.AsyncClient(transport=httpx.MockTransport(fallback_handler)) as fallback_client,
    ):
        registry = ProviderRegistry()
        registry.register(
            OpenAICompatibleProvider(
                name="limited", base_url="https://limited.test/v1", client=limited_client
            )
        )
        registry.register(
            OpenAICompatibleProvider(
                name="fallback", base_url="https://fallback.test/v1", client=fallback_client
            )
        )
        gateway = ReliableProviderGateway(registry)
        candidates = [
            ProviderCandidate(provider="limited", model="fast-model"),
            ProviderCandidate(provider="fallback", model="safe-model"),
        ]
        request = ModelRequest(
            model="router-placeholder",
            messages=[ModelMessage(role="user", content="work")],
        )
        async with database.session() as session:
            first = await gateway.complete(session, request, candidates, prompt_version="test-v1")
            await session.commit()
        async with database.session() as session:
            second = await gateway.complete(session, request, candidates, prompt_version="test-v1")
            await session.commit()

    assert first.model == second.model == "safe-model"
    assert calls == {"limited": 1, "fallback": 2}
    async with database.session() as session:
        health = await session.scalar(
            select(ModelHealthRecord).where(ModelHealthRecord.provider == "limited")
        )
        limited_quota = await session.scalar(
            select(ProviderQuotaSnapshot).where(ProviderQuotaSnapshot.provider == "limited")
        )
        fallback_quota = await session.scalar(
            select(ProviderQuotaSnapshot).where(ProviderQuotaSnapshot.provider == "fallback")
        )
        usage_count = await session.scalar(select(func.count()).select_from(ModelUsageRecord))
    assert health is not None and health.state == "COOLDOWN"
    assert health.cooldown_until is not None
    assert limited_quota is not None and limited_quota.requests_remaining == 0
    assert fallback_quota is not None and fallback_quota.requests_remaining == 9
    assert fallback_quota.tokens_used == 6
    assert usage_count == 3


def test_quota_header_parser_handles_relative_and_epoch_resets() -> None:
    now = datetime(2026, 9, 3, tzinfo=UTC)
    relative = quota_from_headers(
        {
            "X-RateLimit-Remaining-Requests": "42",
            "x-ratelimit-remaining-tokens": "900",
            "x-ratelimit-reset-requests": "1m30s",
        },
        now=now,
    )
    epoch = quota_from_headers(
        {"ratelimit-reset": str(int((now + timedelta(minutes=5)).timestamp()))},
        now=now,
    )

    assert relative.requests_remaining == 42
    assert relative.tokens_remaining == 900
    assert relative.reset_at == now + timedelta(seconds=90)
    assert epoch.reset_at == now + timedelta(minutes=5)


async def test_transport_timeout_falls_back_and_records_degraded_state(
    database: Database,
) -> None:
    async def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("offline", request=request)

    async def fallback_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "fallback-model",
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            },
        )

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler)) as offline_client,
        httpx.AsyncClient(transport=httpx.MockTransport(fallback_handler)) as fallback_client,
    ):
        registry = ProviderRegistry()
        registry.register(
            OpenAICompatibleProvider(
                name="offline", base_url="https://offline.test/v1", client=offline_client
            )
        )
        registry.register(
            OpenAICompatibleProvider(
                name="fallback", base_url="https://fallback.test/v1", client=fallback_client
            )
        )
        async with database.session() as session:
            response = await ReliableProviderGateway(registry).complete(
                session,
                ModelRequest(model="placeholder", messages=[]),
                [
                    ProviderCandidate(provider="offline", model="offline-model"),
                    ProviderCandidate(provider="fallback", model="fallback-model"),
                ],
            )
            await session.commit()

    assert response.model == "fallback-model"
    async with database.session() as session:
        health = await session.scalar(
            select(ModelHealthRecord).where(ModelHealthRecord.provider == "offline")
        )
    assert health is not None and health.state == "DEGRADED"


async def test_empty_candidate_list_fails_without_paid_or_network_use(database: Database) -> None:
    with pytest.raises(AllProvidersUnavailable, match="no candidates"):
        async with database.session() as session:
            await ReliableProviderGateway(ProviderRegistry()).complete(
                session, ModelRequest(model="placeholder", messages=[]), []
            )
