"""Completed-event lag cannot outlive a verified quiet learning boundary."""

# ruff: noqa: F811 -- shared fixtures

import asyncio

import pytest
from signal_arcade.models import EventKind, MarketEvent
from test_probe_retention import engine  # noqa: F401
from test_publication_diagnostics import clock  # noqa: F401
from test_publication_pressure import queued_job


@pytest.mark.parametrize(
    "quiet,allowed", [(4.999999, False), (5, True), (5.000001, True), (-1, False)]
)
def test_completed_lag_needs_five_seconds_of_real_idle_time(engine, clock, quiet, allowed):
    engine.last_processing_lag_seconds = 2
    engine._last_market_batch_completed_monotonic = clock[0] - quiet
    assert engine._learning_training_can_run() is allowed
    assert engine._learning_publication_can_run() is allowed
    assert engine.last_processing_lag_seconds == 2
    assert not engine._shadow_ai_can_run()
    engine.demo_mode = False
    engine.settings.learning_reserve_refresh_enabled = True
    assert engine._learning_reserve_blocked_reason() == "processing_lag"


@pytest.mark.parametrize(
    "block",
    [
        "queued",
        "dequeued",
        "producer",
        "inflight",
        "boundary",
        "maintenance",
        "storage",
        "stop",
        "unknown",
        "future",
        "nan",
        "inf",
    ],
)
def test_idle_recovery_never_bypasses_work_or_unknown_clocks(engine, clock, block):
    engine.last_processing_lag_seconds = 2
    engine._last_market_batch_completed_monotonic = clock[0] - 10
    if block in {"queued", "dequeued"}:
        engine.event_queue.put_nowait(
            (0, 1, MarketEvent(event_id="urgent", source="test", kind=EventKind.TRADE))
        )
        if block == "dequeued":
            engine.event_queue.get_nowait()
            assert engine.event_queue.qsize() == 0 and engine._event_batches_in_flight == 0
    elif block == "producer":
        engine.event_queue.admit(1)
    elif block == "inflight":
        engine._event_batches_in_flight = 1
    elif block == "boundary":
        engine.event_queue.begin_boundary(0)
    elif block == "maintenance":
        engine._maintenance_requested = True
    elif block == "storage":
        engine._storage_maintenance_active = True
    elif block == "stop":
        engine.stop_event.set()
    elif block == "unknown":
        engine._last_market_batch_completed_monotonic = None
    elif block == "future":
        engine._last_market_batch_completed_monotonic = clock[0] + 1
    else:
        engine.last_processing_lag_seconds = float(block)
    assert not engine._learning_training_can_run()
    assert not engine._learning_publication_can_run()


def test_dequeued_handoff_remains_protected_until_receipt_completion(engine, clock):
    engine.last_processing_lag_seconds = 2
    engine._last_market_batch_completed_monotonic = clock[0] - 10
    engine.event_queue.put_nowait(
        (0, 1, MarketEvent(event_id="handoff", source="test", kind=EventKind.TRADE))
    )
    engine.event_queue.get_nowait()
    assert engine.event_queue.qsize() == engine._event_batches_in_flight == 0
    assert engine._diagnostics_busy()
    assert not engine._learning_training_can_run()
    assert not engine._learning_publication_can_run()
    engine.event_queue.task_done()
    assert not engine.event_queue.has_admitted_work
    assert not engine.event_queue.has_dequeued_work
    assert not engine._diagnostics_busy()


@pytest.mark.parametrize("now", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_current_clock_cannot_establish_quiet_time(engine, clock, now):
    engine.last_processing_lag_seconds = 2
    engine._last_market_batch_completed_monotonic = clock[0] - 10
    clock[0] = now
    assert not engine._learning_training_can_run()
    assert not engine._learning_publication_can_run()


@pytest.mark.parametrize("ending", ["complete", "error", "cancel"])
def test_only_completed_successful_batches_establish_the_idle_clock(engine, monkeypatch, ending):
    engine.last_processing_lag_seconds = 2
    engine._last_market_batch_completed_monotonic = 1
    engine.event_queue.put_nowait(
        (0, 1, MarketEvent(event_id="event", source="test", kind=EventKind.HEALTH))
    )

    async def handle(*_args, **_kwargs):
        assert engine._last_market_batch_completed_monotonic is None
        engine.stop_event.set()
        if ending == "error":
            raise ValueError("isolated batch failure")
        if ending == "cancel":
            raise asyncio.CancelledError
        return True

    monkeypatch.setattr(engine, "_handle_persisted_event", handle)
    if ending == "cancel":
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(engine._event_worker_loop())
    else:
        asyncio.run(engine._event_worker_loop())
    assert (engine._last_market_batch_completed_monotonic is not None) is (ending == "complete")
    assert engine._event_batches_in_flight == 0
    assert not engine.event_queue.has_admitted_work


@pytest.mark.parametrize("invalid", [None, "expired", "context", "urgent"])
def test_idle_publication_preserves_job_age_context_and_urgent_recheck(
    engine, clock, monkeypatch, invalid
):
    engine.last_processing_lag_seconds = 2
    engine._last_market_batch_completed_monotonic = clock[0] - 10
    job = queued_job(engine)
    if invalid == "expired":
        job.started_monotonic = clock[0] - 121
    elif invalid == "context":
        engine.broker.season_id = "changed"
    calls = []

    def finish(*_args, runtime_context, **_kwargs):
        stale = engine.learning.training_job_stale(job, runtime_context)
        calls.append(stale)
        assert stale or engine._learning_publication_can_run()
        return not stale

    def collect(_job):
        if invalid == "urgent":
            engine.event_queue.put_nowait(
                (0, 1, MarketEvent(event_id="urgent", source="test", kind=EventKind.TRADE))
            )

    async def stop(_delay):
        assert invalid == "urgent" and not calls
        engine.stop_event.set()  # Terminal bookkeeping must still finish.

    monkeypatch.setattr(engine.learning, "finish_training_job", finish)
    monkeypatch.setattr(engine, "_collect_before_publication", collect)
    monkeypatch.setattr(engine, "_wait_for_stop", stop)
    assert asyncio.run(engine._publish_training_job(engine.learning, job, None)) is (
        invalid is None
    )
    assert calls == [invalid is not None]
