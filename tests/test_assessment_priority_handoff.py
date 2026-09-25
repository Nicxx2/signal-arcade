"""A newly saved AI outcome must not strand its older ticks at candidate priority."""

# ruff: noqa: F811 -- shared fixture

import asyncio

import pytest
from signal_arcade.event_queue import SeasonEventQueue
from signal_arcade.intelligence.features import TokenState
from signal_arcade.models import EventKind, MarketEvent
from test_ai_save_handoff import assessment
from test_probe_retention import engine  # noqa: F401


@pytest.mark.parametrize("queued_old", [False, True])
def test_registration_keeps_prefetched_and_queued_ticks_before_newer_urgent_tick(
    engine, monkeypatch, queued_old
):
    engine.settings.event_batch_size = 4
    engine.running = True
    for mint in ("target", "other"):
        engine.features.tokens[mint] = TokenState(mint=mint)
    reached, release = asyncio.Event(), asyncio.Event()
    accepted, rejected = [], []

    def event(index, mint):
        return MarketEvent(
            event_id=str(index), source="test", kind=EventKind.TRADE, mint=mint, slot=index
        )

    async def handle(item, *, sequence=None):
        if item.event_id == "1":
            reached.set()
            await release.wait()
        if not engine._accept_event_order(item, sequence):
            rejected.append(item.event_id)
            return False
        if item.mint == "target":
            assert engine.database.recent_events(20)[0] is not None
            assert any(x.event_id == item.event_id for x in engine.database.recent_events(20))
            accepted.append(item.slot)
        return True

    monkeypatch.setattr(engine, "_handle_persisted_event", handle)

    async def run():
        for index, mint in ((1, "other"), (2, "target"), (3, "other"), (4, "target")):
            await engine.enqueue_event(event(index, mint))
        if queued_old:
            await engine.enqueue_event(event(5, "target"))
        worker = asyncio.create_task(engine._event_worker_loop())
        try:
            await asyncio.wait_for(reached.wait(), 2)
            await engine.ai_lab._save_assessment(assessment("target"))
            await engine.enqueue_event(event(10, "target"))
            release.set()
            await asyncio.wait_for(engine.event_queue.join(), 3)
            assert not rejected
            assert accepted == ([2, 4, 5, 10] if queued_old else [2, 4, 10])
            assert not engine.event_queue._pending_sequences
        finally:
            release.set()
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    asyncio.run(run())


@pytest.mark.parametrize("boundary", [False, True])
def test_promotion_preserves_season_boundary_receipts_and_existing_critical_order(boundary):
    queue = SeasonEventQueue(8)
    for sequence, priority, mint in ((1, 0, "held"), (2, 2, "target"), (3, 1, "target")):
        queue.put_nowait(
            (
                priority,
                sequence,
                MarketEvent(event_id=str(sequence), source="test", mint=mint, kind=EventKind.TRADE),
            )
        )
    if boundary:
        queue.begin_boundary(3)
    for sequence, mint in ((4, "other"), (5, "target")):
        queue.put_nowait(
            (
                2,
                sequence,
                MarketEvent(event_id=str(sequence), source="test", mint=mint, kind=EventKind.TRADE),
            )
        )
    original = set(queue._pending_sequences)
    assert queue.promote_mint("absent") == 0
    assert queue.promote_mint("target") == 3
    assert queue.promote_mint("target") == 0
    assert queue._pending_sequences == original
    seen = []
    while not queue.empty():
        seen.append(queue.get_nowait()[1])
        queue.task_done()
    if boundary:
        assert seen == [1, 2, 3] and queue.boundary_ready()
        queue.end_boundary()
        while not queue.empty():
            seen.append(queue.get_nowait()[1])
            queue.task_done()
    assert seen == [1, 2, 3, 5, 4]
    assert not queue._pending_sequences
    asyncio.run(queue.join())


def test_duplicate_registration_does_not_repeat_the_priority_transition(engine):
    async def run():
        value = assessment("target")
        await engine.ai_lab._save_assessment(value)
        await engine.ai_lab._save_assessment(value)
        assert engine._event_priority_revision == 1
        assert len(engine.ai_lab.pending_outcomes["target"]) == 1
        assert len(engine.database.list_ai_assessments()) == 1

    asyncio.run(run())
