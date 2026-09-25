"""An ordinary-event backlog must not monopolise the loop between durable units."""

# ruff: noqa: F811 -- shared fixture

import asyncio
import time

import pytest
from signal_arcade.intelligence.features import TokenState
from signal_arcade.models import EventKind, MarketEvent
from test_probe_retention import engine, position  # noqa: F401


@pytest.mark.parametrize("boundary", [False, True])
def test_completed_ticks_yield_for_urgent_arrivals_without_crossing_season_boundary(
    engine, monkeypatch, boundary
):
    engine.running = True
    engine.features.tokens["ordinary"] = TokenState(mint="ordinary")
    engine.broker.positions["urgent"] = position("urgent")
    started = asyncio.Event()
    handled, yielded_at, boundaries = [], [], []
    total = 120

    def event(index, mint="ordinary"):
        return MarketEvent(
            event_id=str(index), source="test", kind=EventKind.TRADE, mint=mint, slot=index + 1
        )

    def synchronous_work():
        # Represent a slow synchronous fast path without relying on an exact timing
        # assertion. The watcher must run before the entire prefetched batch finishes.
        time.sleep(0.001)

    async def handle(item, *, sequence=None):
        async with engine._event_lock:
            assert engine._accept_event_order(item, sequence)
            if item.mint == "urgent":
                assert any(x.event_id == item.event_id for x in engine.database.recent_events(10))
            handled.append(item.event_id)
            synchronous_work()
            started.set()
        return True

    async def finish_boundary():
        assert len(handled) == total
        assert engine.event_queue.boundary_ready()
        boundaries.append(len(handled))
        engine.event_queue.end_boundary()

    monkeypatch.setattr(engine, "_handle_persisted_event", handle)
    monkeypatch.setattr(engine, "_finish_season_boundary", finish_boundary)

    async def observer():
        await started.wait()
        assert not engine._event_lock.locked()
        assert engine._event_batches_in_flight == 1
        assert not engine.event_queue.boundary_ready()
        yielded_at.append(len(handled))
        await engine.enqueue_event(event(1000, "urgent"))

    async def run():
        for index in range(total):
            await engine.enqueue_event(event(index))
        if boundary:
            engine.event_queue.begin_boundary(engine._event_sequence)
        observer_task = asyncio.create_task(observer())
        worker = asyncio.create_task(engine._event_worker_loop())
        try:
            await asyncio.wait_for(observer_task, 5)
            await asyncio.wait_for(engine.event_queue.join(), 5)
            assert 0 < yielded_at[0] < total
            assert [x for x in handled if x != "1000"] == [str(i) for i in range(total)]
            assert len(handled) == len(set(handled)) == total + 1
            assert engine.events_processed == total + 1
            assert engine.events_dropped == 0
            assert not engine.event_queue._pending_sequences
            assert not engine.event_queue.has_dequeued_work
            if boundary:
                assert boundaries == [total] and handled[-1] == "1000"
            else:
                assert handled.index("1000") < total - 1
        finally:
            observer_task.cancel()
            worker.cancel()
            await asyncio.gather(observer_task, worker, return_exceptions=True)
        assert not engine._event_lock.locked()
        assert engine._event_batches_in_flight == 0

    asyncio.run(run())
