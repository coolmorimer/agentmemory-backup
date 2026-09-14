from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autodev.api.dependencies import get_session
from autodev.db.models import (
    AuditEvent,
    ModelHealthRecord,
    ModelUsageRecord,
    RoutingPreferenceRecord,
)
from autodev.memory.agentmemory import AgentMemoryHttpProvider, MemoryProviderError
from autodev.memory.base import MemoryQuery
from autodev.providers.base import ProviderError
from autodev.schemas.providers import ModelSelectionUpdate, ProviderUpdate
from autodev.services.audit import record_audit
from autodev.services.provider_settings import (
    ModelSettingsService,
    ProviderSettingsError,
    ProviderSettingsService,
)

router = APIRouter(tags=["system"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


@router.get("/api/providers")
async def providers(request: Request, session: SessionDependency) -> list[dict[str, object]]:
    return await ProviderSettingsService(request.app.state.settings).public_configs(session)


@router.put("/api/providers/{name}")
async def update_provider(
    name: str,
    payload: ProviderUpdate,
    request: Request,
    session: SessionDependency,
) -> dict[str, object]:
    service = ProviderSettingsService(request.app.state.settings)
    try:
        async with session.begin():
            await service.save(session, name=name, **payload.model_dump())
            record_audit(
                session,
                "provider.configuration.updated",
                details={"provider": name, "enabled": payload.enabled},
            )
    except ProviderSettingsError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    return next(item for item in await service.public_configs(session) if item["name"] == name)


@router.delete("/api/providers/{name}/credential", status_code=status.HTTP_204_NO_CONTENT)
async def clear_provider_credential(
    name: str,
    request: Request,
    session: SessionDependency,
) -> Response:
    service = ProviderSettingsService(request.app.state.settings)
    async with session.begin():
        if not await service.clear_credential(session, name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="credential not found"
            )
        record_audit(
            session,
            "provider.credential.cleared",
            details={"provider": name},
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/providers/{name}/test")
async def test_provider(
    name: str,
    request: Request,
    session: SessionDependency,
) -> dict[str, object]:
    try:
        provider = await ProviderSettingsService(request.app.state.settings).provider(session, name)
        health = await provider.health()
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except (ProviderSettingsError, ProviderError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    return {
        "provider": name,
        "available": health.available,
        "latency_seconds": health.latency_seconds,
        "detail": health.detail,
    }


@router.get("/api/providers/health")
async def provider_health(session: SessionDependency) -> list[dict[str, Any]]:
    records = list(
        await session.scalars(select(ModelHealthRecord).order_by(ModelHealthRecord.provider))
    )
    return [
        {
            "provider": record.provider,
            "model": record.model,
            "state": record.state,
            "consecutive_failures": record.consecutive_failures,
            "cooldown_until": record.cooldown_until,
        }
        for record in records
    ]


@router.get("/api/models")
async def models(request: Request, session: SessionDependency) -> list[dict[str, object]]:
    return await ModelSettingsService(request.app.state.settings).list_models(session)


@router.post("/api/models/discover")
async def discover_models(
    request: Request,
    session: SessionDependency,
    provider: Annotated[str, Query(min_length=1, max_length=100)] = "ollama",
) -> dict[str, object]:
    service = ModelSettingsService(request.app.state.settings)
    try:
        async with session.begin():
            discovered = await service.discover(session, provider)
            record_audit(
                session,
                "models.discovered",
                details={"provider": provider, "count": len(discovered)},
            )
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except (ProviderSettingsError, ProviderError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    return {"provider": provider, "models": discovered}


@router.get("/api/model-selection")
async def model_selection(session: SessionDependency) -> dict[str, str]:
    records = list(await session.scalars(select(RoutingPreferenceRecord)))
    return {record.role: record.model_id for record in records}


@router.put("/api/model-selection/{role}")
async def update_model_selection(
    role: str,
    payload: ModelSelectionUpdate,
    request: Request,
    session: SessionDependency,
) -> dict[str, str]:
    allowed_roles = {"implementation", "review", "planning", "vision", "embedding"}
    if role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown role")
    service = ModelSettingsService(request.app.state.settings)
    try:
        async with session.begin():
            preference = await service.set_preference(
                session, role=role, model_id=payload.model_id
            )
            record_audit(
                session,
                "model.selection.updated",
                details={"role": role, "model_id": payload.model_id},
            )
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ProviderSettingsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return {"role": preference.role, "model_id": preference.model_id}


@router.get("/api/model-usage")
async def model_usage(
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[dict[str, Any]]:
    records = list(
        await session.scalars(
            select(ModelUsageRecord).order_by(ModelUsageRecord.created_at.desc()).limit(limit)
        )
    )
    return [
        {
            "id": str(record.id),
            "project_id": str(record.project_id) if record.project_id else None,
            "task_id": str(record.task_id) if record.task_id else None,
            "provider": record.provider,
            "model": record.model,
            "prompt_version": record.prompt_version,
            "status": record.status,
            "total_tokens": record.total_tokens,
            "latency_seconds": record.latency_seconds,
            "created_at": record.created_at,
        }
        for record in records
    ]


@router.get("/api/audit")
async def audit_log(
    session: SessionDependency,
    project_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[dict[str, Any]]:
    statement = select(AuditEvent)
    if project_id is not None:
        statement = statement.where(AuditEvent.project_id == project_id)
    if task_id is not None:
        statement = statement.where(AuditEvent.task_id == task_id)
    records = list(
        await session.scalars(statement.order_by(AuditEvent.created_at.desc()).limit(limit))
    )
    return [
        {
            "id": str(record.id),
            "event": record.event,
            "project_id": str(record.project_id) if record.project_id else None,
            "task_id": str(record.task_id) if record.task_id else None,
            "actor": record.actor,
            "agent": record.agent,
            "details": record.details,
            "created_at": record.created_at,
        }
        for record in records
    ]


@router.get("/api/memory/search")
async def search_memory(
    request: Request,
    query: Annotated[str, Query(min_length=1)],
    project: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 5,
) -> list[dict[str, Any]]:
    provider = AgentMemoryHttpProvider(request.app.state.settings.agentmemory_base_url)
    try:
        items = await provider.search(MemoryQuery(query=query, project=project, limit=limit))
    except MemoryProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="memory service unavailable",
        ) from error
    return [item.model_dump(mode="json") for item in items]
