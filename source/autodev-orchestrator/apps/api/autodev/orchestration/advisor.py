from __future__ import annotations

import uuid
from typing import Protocol

from autodev.config import Settings
from autodev.db.session import Database
from autodev.providers.base import ModelMessage, ModelRequest
from autodev.providers.registry import ProviderRegistry
from autodev.providers.reliability import (
    AllProvidersUnavailable,
    ProviderCandidate,
    ReliableProviderGateway,
)
from autodev.routing.models import BillingMode, RoutingDecision
from autodev.routing.quota import QuotaPolicy
from autodev.services.audit import record_audit
from autodev.services.provider_settings import ProviderSettingsService


class ImplementationAdvisor(Protocol):
    async def advise(
        self,
        route: RoutingDecision,
        *,
        project_id: uuid.UUID,
        task_id: uuid.UUID,
        title: str,
        description: str,
        context: str,
    ) -> str | None: ...


class ProviderImplementationAdvisor:
    """Use the selected LLM for bounded advice while Codex remains the repository tool runner."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self._database = database
        self._settings = settings

    async def advise(
        self,
        route: RoutingDecision,
        *,
        project_id: uuid.UUID,
        task_id: uuid.UUID,
        title: str,
        description: str,
        context: str,
    ) -> str | None:
        if route.provider == "codex":
            return None
        service = ProviderSettingsService(self._settings)
        async with self._database.session() as session:
            config = (await service.effective(session)).get(route.provider)
            if config is None:
                return None
            registry = ProviderRegistry()
            registry.register(await service.provider(session, route.provider))
            billing = {
                "local": BillingMode.LOCAL,
                "paid": BillingMode.PAID,
            }.get(config.billing_mode, BillingMode.FREE)
            gateway = ReliableProviderGateway(
                registry,
                quota_policy=QuotaPolicy(
                    allow_paid_models=self._settings.allow_paid_models,
                    max_cloud_cost_usd_day=self._settings.max_cloud_cost_usd_day,
                ),
            )
            remote_model = route.model_id.removeprefix(f"{route.provider}/")
            request = ModelRequest(
                model=remote_model,
                temperature=0.1,
                max_tokens=2048,
                messages=[
                    ModelMessage(
                        role="system",
                        content=(
                            "You are a read-only implementation advisor. Return concise technical "
                            "guidance for a separate coding agent. Never claim that you edited "
                            "files."
                        ),
                    ),
                    ModelMessage(
                        role="user",
                        content=(
                            f"Task: {title}\n\n{description}\n\nRepository context:\n"
                            f"{context[-20_000:]}"
                        ),
                    ),
                ],
            )
            try:
                response = await gateway.complete(
                    session,
                    request,
                    [ProviderCandidate(route.provider, remote_model, billing)],
                    project_id=project_id,
                    task_id=task_id,
                    prompt_version="implementation-advisor-v1",
                )
            except AllProvidersUnavailable as error:
                record_audit(
                    session,
                    "model.advice.failed",
                    project_id=project_id,
                    task_id=task_id,
                    details={"provider": route.provider, "error": str(error)},
                )
                await session.commit()
                return None
            record_audit(
                session,
                "model.advice.completed",
                project_id=project_id,
                task_id=task_id,
                details={"provider": route.provider, "model": remote_model},
            )
            await session.commit()
            return response.content
