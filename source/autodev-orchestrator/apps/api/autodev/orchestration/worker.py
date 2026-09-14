from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Protocol

from autodev.db.models import Task
from autodev.db.session import Database
from autodev.domain.enums import TaskStatus
from autodev.domain.fsm import TaskStateMachine
from autodev.orchestration.scheduler import Scheduler
from autodev.services.audit import record_audit


class TaskExecutor(Protocol):
    async def execute_claimed(self, task_id: uuid.UUID) -> object: ...


class WorkerPool:
    """Claims durable work serially and executes independent tasks concurrently."""

    def __init__(
        self,
        database: Database,
        executor: TaskExecutor,
        *,
        scheduler: Scheduler | None = None,
        concurrency: int = 4,
        worker_prefix: str = "worker",
        lease_seconds: int = 300,
        heartbeat_interval: float | None = None,
        on_error: Callable[[uuid.UUID, Exception], Awaitable[None]] | None = None,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        self._database = database
        self._executor = executor
        self._scheduler = scheduler or Scheduler()
        self._concurrency = concurrency
        self._worker_prefix = worker_prefix
        self._lease_seconds = lease_seconds
        self._heartbeat_interval = heartbeat_interval or max(1.0, lease_seconds / 3)
        self._on_error = on_error
        self._fsm = TaskStateMachine()

    async def run_once(self) -> int:
        async with self._database.session() as session:
            await self._scheduler.release_ready_dependencies(session)

        claimed: list[tuple[uuid.UUID, str]] = []
        for slot in range(self._concurrency):
            worker_id = f"{self._worker_prefix}-{slot + 1}"
            async with self._database.session() as session:
                task = await self._scheduler.claim_next(
                    session,
                    worker_id=worker_id,
                    lease_seconds=self._lease_seconds,
                )
            if task is None:
                break
            claimed.append((task.id, worker_id))

        if not claimed:
            return 0
        async with asyncio.TaskGroup() as group:
            for task_id, worker_id in claimed:
                group.create_task(self._execute(task_id, worker_id))
        return len(claimed)

    async def run_forever(self, stop: asyncio.Event, *, poll_interval: float = 1.0) -> None:
        async with self._database.session() as session:
            await self._scheduler.recover_expired(session)
        while not stop.is_set():
            processed = await self.run_once()
            if processed:
                continue
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=poll_interval)

    async def _execute(self, task_id: uuid.UUID, worker_id: str) -> None:
        heartbeat_stop = asyncio.Event()
        heartbeat = asyncio.create_task(
            self._heartbeat(task_id, worker_id, heartbeat_stop),
            name=f"heartbeat-{task_id}",
        )
        try:
            await self._executor.execute_claimed(task_id)
        except Exception as error:
            await self._recover_crashed_task(task_id, error)
            if self._on_error is not None:
                await self._on_error(task_id, error)
        finally:
            heartbeat_stop.set()
            await heartbeat

    async def _heartbeat(self, task_id: uuid.UUID, worker_id: str, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._heartbeat_interval)
            except TimeoutError:
                async with self._database.session() as session:
                    renewed = await self._scheduler.renew_lease(
                        session,
                        task_id=task_id,
                        worker_id=worker_id,
                        lease_seconds=self._lease_seconds,
                    )
                if not renewed:
                    return

    async def _recover_crashed_task(self, task_id: uuid.UUID, error: Exception) -> None:
        async with self._database.session() as session, session.begin():
            task = await session.get(Task, task_id, with_for_update=True)
            if task is None or task.status is not TaskStatus.RUNNING:
                return
            target = (
                TaskStatus.FAILED if task.attempt_count >= task.max_attempts else TaskStatus.READY
            )
            task.status = self._fsm.transition(task.status, target)
            task.claimed_by = None
            task.lease_expires_at = None
            record_audit(
                session,
                "task.worker.crashed",
                project_id=task.project_id,
                task_id=task.id,
                details={"error_type": type(error).__name__, "result": target.value},
            )
