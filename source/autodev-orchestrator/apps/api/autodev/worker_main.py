from __future__ import annotations

import asyncio

import structlog

from autodev.codex.app_server import CodexAppServerAdapter
from autodev.config import get_settings
from autodev.db.session import Database
from autodev.memory.agentmemory import AgentMemoryHttpProvider
from autodev.orchestration.advisor import ProviderImplementationAdvisor
from autodev.orchestration.engine import ExecutionEngine
from autodev.orchestration.worker import WorkerPool
from autodev.routing.router import ModelRouter, default_profiles
from autodev.services.provider_settings import ModelSettingsService
from autodev.telemetry.logging import configure_logging


async def main() -> None:
    settings = get_settings()
    configure_logging(json_output=settings.environment != "development")
    database = Database(settings.database_url)
    model_settings = ModelSettingsService(settings)
    engine = ExecutionEngine(
        database,
        router=ModelRouter(
            default_profiles(),
            allow_paid_models=settings.allow_paid_models,
            max_cloud_cost_usd_day=settings.max_cloud_cost_usd_day,
        ),
        coding_agent=CodexAppServerAdapter(executable=settings.codex_executable),
        memory_provider=AgentMemoryHttpProvider(settings.agentmemory_base_url),
        router_resolver=model_settings.router,
        preference_resolver=model_settings.preferred,
        implementation_advisor=ProviderImplementationAdvisor(database, settings),
    )
    pool = WorkerPool(database, engine, concurrency=settings.max_codex_workers)
    stop = asyncio.Event()
    structlog.get_logger().info("worker.started", concurrency=settings.max_codex_workers)
    try:
        await pool.run_forever(stop)
    finally:
        await database.dispose()


def run() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    run()
