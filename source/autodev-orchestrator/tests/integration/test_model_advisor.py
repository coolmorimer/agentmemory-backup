from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from autodev.config import Settings
from autodev.db.models import AuditEvent, ModelUsageRecord
from autodev.db.session import Database
from autodev.orchestration.advisor import ProviderImplementationAdvisor
from autodev.providers.base import (
    ModelRequest,
    ModelResponse,
    ProviderError,
    ProviderHealth,
    TokenUsage,
)
from autodev.routing.models import RoutingDecision
from autodev.services.provider_settings import ProviderSettingsService


class FakeAdvisorProvider:
    name = "ollama"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if self.fail:
            raise ProviderError(
                "fixture provider failure",
                provider=self.name,
                retryable=False,
            )
        return ModelResponse(
            provider=self.name,
            model=request.model,
            content="Inspect the transaction boundary first.",
            usage=TokenUsage(prompt_tokens=4, completion_tokens=5, total_tokens=9),
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(available=not self.fail)


def route() -> RoutingDecision:
    return RoutingDecision(
        model_id="ollama/qwen2.5-coder:7b",
        provider="ollama",
        score=1,
        reasons=["operator selection"],
    )


async def test_selected_local_model_produces_recorded_advice(
    database: Database, monkeypatch: Any
) -> None:
    provider = FakeAdvisorProvider()

    async def configured_provider(
        _service: ProviderSettingsService, _session: Any, _name: str
    ) -> FakeAdvisorProvider:
        return provider

    monkeypatch.setattr(ProviderSettingsService, "provider", configured_provider)
    project_id = uuid.uuid4()
    task_id = uuid.uuid4()
    advice = await ProviderImplementationAdvisor(database, Settings()).advise(
        route(),
        project_id=project_id,
        task_id=task_id,
        title="Implement transaction",
        description="Keep it atomic",
        context="repository map",
    )

    assert advice == "Inspect the transaction boundary first."
    assert provider.requests[0].model == "qwen2.5-coder:7b"
    async with database.session() as session:
        usage = await session.scalar(select(ModelUsageRecord))
        audit = await session.scalar(
            select(AuditEvent).where(AuditEvent.event == "model.advice.completed")
        )
        assert usage is not None
        assert usage.total_tokens == 9
        assert audit is not None


async def test_advisor_failure_degrades_to_codex_without_stopping_task(
    database: Database, monkeypatch: Any
) -> None:
    provider = FakeAdvisorProvider(fail=True)

    async def configured_provider(
        _service: ProviderSettingsService, _session: Any, _name: str
    ) -> FakeAdvisorProvider:
        return provider

    monkeypatch.setattr(ProviderSettingsService, "provider", configured_provider)
    advice = await ProviderImplementationAdvisor(database, Settings()).advise(
        route(),
        project_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        title="Implement transaction",
        description="Keep it atomic",
        context="repository map",
    )

    assert advice is None
    async with database.session() as session:
        audit = await session.scalar(
            select(AuditEvent).where(AuditEvent.event == "model.advice.failed")
        )
        assert audit is not None
