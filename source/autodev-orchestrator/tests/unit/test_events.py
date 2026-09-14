from __future__ import annotations

from autodev.events import AsyncEventBus, Event


async def test_event_bus_broadcasts_to_subscriber() -> None:
    bus = AsyncEventBus()
    event = Event(name="task.completed", payload={"commit": "abc123"})

    async with bus.subscribe() as queue:
        await bus.publish(event)
        received = await queue.get()

    assert received == event
    assert bus.dropped_events == 0


async def test_event_bus_counts_backpressure_drops() -> None:
    bus = AsyncEventBus(subscriber_buffer=1)

    async with bus.subscribe():
        await bus.publish(Event(name="first"))
        await bus.publish(Event(name="second"))

    assert bus.dropped_events == 1
