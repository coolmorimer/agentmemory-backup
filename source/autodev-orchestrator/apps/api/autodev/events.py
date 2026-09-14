from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field
from redis.asyncio import Redis


class Event(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    project_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    correlation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EventPublisher(Protocol):
    async def publish(self, event: Event) -> None: ...


class AsyncEventBus:
    def __init__(self, *, subscriber_buffer: int = 1000) -> None:
        self.subscriber_buffer = subscriber_buffer
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self.dropped_events = 0

    async def publish(self, event: Event) -> None:
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self.dropped_events += 1

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[Event]]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=self.subscriber_buffer)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)


class RedisEventPublisher:
    def __init__(self, url: str, *, channel: str = "autodev.events") -> None:
        self._redis: Redis = Redis.from_url(url, decode_responses=True)
        self.channel = channel

    async def publish(self, event: Event) -> None:
        await self._redis.publish(self.channel, event.model_dump_json())

    async def close(self) -> None:
        await self._redis.aclose()


class CompositeEventPublisher:
    def __init__(self, *publishers: EventPublisher) -> None:
        self.publishers = publishers

    async def publish(self, event: Event) -> None:
        for publisher in self.publishers:
            await publisher.publish(event)
