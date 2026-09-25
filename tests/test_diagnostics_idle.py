"""Recover quiet diagnostics without changing trading or fitting admission."""

# ruff: noqa: F811 -- shared pytest fixtures

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.models import EventKind, MarketEvent
from test_probe_retention import engine  # noqa: F401
from test_publication_diagnostics import clock  # noqa: F401


@pytest.mark.parametrize("lag", [0.999999, 1.0, 2.0])
@pytest.mark.parametrize(
    "depth,flight,boundary",
    [(0, 0, False), (1, 0, False), (0, 1, False), (0, 0, True), (100, 0, False), (101, 0, False)],
)
def test_lag_exception_requires_a_drained_boundary(
    engine, monkeypatch, lag, depth, flight, boundary
):
    monkeypatch.setattr(engine.event_queue, "qsize", lambda: depth)
    engine.event_queue.boundary = 0 if boundary else None
    engine._event_batches_in_flight = flight
    engine.last_processing_lag_seconds = lag
    assert engine._diagnostics_busy() == (
        depth > 100 or (lag >= 1 and bool(depth or flight or boundary))
    )
    assert engine.last_processing_lag_seconds == lag


@pytest.mark.parametrize("reason", ["maintenance", "storage", "training", "nan", "inf"])
def test_idle_exception_keeps_other_admission_blocks(engine, reason):
    engine.last_processing_lag_seconds = 2
    if reason == "maintenance":
        engine._maintenance_requested = True
    elif reason == "storage":
        engine._storage_maintenance_active = True
    elif reason == "training":
        engine.learning._training_active = (engine.risk_mode, None)
    else:
        engine.last_processing_lag_seconds = float(reason)
    assert engine._diagnostics_busy()


@pytest.mark.parametrize("event_age", [None, -3600, 300])
def test_idle_recovery_keeps_lag_evidence_and_learning_guards(
    engine, clock, monkeypatch, event_age
):
    engine.last_processing_lag_seconds = 2
    engine.last_event_processed_at = (
        datetime.now(UTC) - timedelta(seconds=event_age) if event_age is not None else None
    )
    engine._record_pipeline_recent("processed", lag_seconds=2, critical=True)
    clock[0] += 61
    saved = []
    engine.diagnostics.writer.offer = lambda raw: saved.append(json.loads(raw)) or True

    async def stop(_seconds):
        engine.stop_event.set()

    monkeypatch.setattr(engine, "_wait_for_stop", stop)
    asyncio.run(engine._diagnostics_loop())
    assert len(saved) == 1
    assert saved[0]["pipeline"]["critical_lag_max"] == 2
    assert engine.last_processing_lag_seconds == 2
    assert not engine._learning_training_can_run()
    assert not engine._learning_publication_can_run()
    assert not engine.diagnostics.collection_due()
    assert engine.diagnostics.total_dropped == 0


@pytest.mark.parametrize("arrival", ["urgent", "stop", "cancel"])
def test_idle_recovery_rechecks_after_wait_without_leaking_lock(
    engine, clock, monkeypatch, arrival
):
    engine.last_processing_lag_seconds = 2
    clock[0] += 61

    async def stop(_seconds):
        engine.stop_event.set()

    monkeypatch.setattr(engine, "_wait_for_stop", stop)

    async def exercise():
        await engine._event_lock.acquire()
        task = asyncio.create_task(engine._diagnostics_loop())
        await asyncio.sleep(0)
        if arrival == "urgent":
            engine.event_queue.put_nowait(
                (0, 1, MarketEvent(event_id="urgent", source="test", kind=EventKind.TRADE))
            )
        elif arrival == "stop":
            engine.stop_event.set()
        else:
            task.cancel()
        engine._event_lock.release()
        if arrival == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await asyncio.wait_for(task, 1)
        assert not engine._event_lock.locked()

    asyncio.run(exercise())
    assert engine.diagnostics.sequence == 0
    assert engine.diagnostics.total_dropped == 0
