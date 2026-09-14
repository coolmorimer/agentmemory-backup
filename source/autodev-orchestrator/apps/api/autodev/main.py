from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect, status
from sqlalchemy import text

from autodev.api.approvals import router as approvals_router
from autodev.api.dashboard import router as dashboard_router
from autodev.api.deployments import router as deployments_router
from autodev.api.projects import router as projects_router
from autodev.api.system import router as system_router
from autodev.api.tasks import router as tasks_router
from autodev.config import Settings, get_settings
from autodev.db.session import Database
from autodev.events import AsyncEventBus
from autodev.telemetry.logging import configure_logging


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    application_settings = settings or get_settings()
    owns_database = database is None
    application_database = database or Database(application_settings.database_url)
    event_bus = AsyncEventBus()
    configure_logging(json_output=application_settings.environment != "development")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = application_settings
        app.state.database = application_database
        app.state.event_bus = event_bus
        yield
        if owns_database:
            await application_database.dispose()

    application = FastAPI(
        title="AutoDev Orchestrator",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(projects_router)
    application.include_router(tasks_router)
    application.include_router(deployments_router)
    application.include_router(approvals_router)
    application.include_router(dashboard_router)
    application.include_router(system_router)

    @application.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            structlog.get_logger().exception(
                "http.request.failed",
                method=request.method,
                path=request.url.path,
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
            )
            raise
        response.headers["x-correlation-id"] = correlation_id
        structlog.get_logger().info(
            "http.request.completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )
        structlog.contextvars.clear_contextvars()
        return response

    @application.websocket("/ws/events")
    async def event_stream(websocket: WebSocket) -> None:
        await websocket.accept()
        disconnect = asyncio.create_task(websocket.receive())
        try:
            async with event_bus.subscribe() as queue:
                while True:
                    next_event = asyncio.create_task(queue.get())
                    done, _ = await asyncio.wait(
                        {disconnect, next_event}, return_when=asyncio.FIRST_COMPLETED
                    )
                    if disconnect in done:
                        next_event.cancel()
                        await asyncio.gather(next_event, return_exceptions=True)
                        return
                    event = next_event.result()
                    await websocket.send_text(event.model_dump_json())
        except WebSocketDisconnect:
            return
        finally:
            disconnect.cancel()
            await asyncio.gather(disconnect, return_exceptions=True)

    @application.get("/health")
    async def health(response: Response) -> dict[str, str]:
        try:
            async with application_database.session() as session:
                await session.execute(text("SELECT 1"))
        except Exception:  # health boundary must not expose credentials or driver internals
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "degraded", "database": "unavailable"}
        return {"status": "ok", "database": "ok"}

    @application.get("/ready")
    async def ready(response: Response) -> dict[str, str]:
        try:
            async with application_database.session() as session:
                await session.execute(text("SELECT 1"))
        except Exception:  # readiness boundary intentionally returns no driver or credential detail
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "not_ready", "database": "unavailable"}
        return {"status": "ready", "database": "ok", "scheduler_source": "postgresql"}

    return application


app = create_app()
