"""Observational attribution preserves admission and joined-worker ownership."""

# ruff: noqa: F811 -- shared pytest fixtures

import asyncio
import random
from threading import Event

import pytest
from signal_arcade.diagnostics_store import MAX_EVENT_PAYLOAD, encode
from signal_arcade.models import EventKind, MarketEvent
from signal_arcade.orchestrator import _HEARTBEAT_WORK, _timed_to_thread
from signal_arcade.work_timing import measure_work
from test_probe_retention import engine  # noqa: F401
from test_publication_diagnostics import clock  # noqa: F401
from test_publication_pressure import queued_job


def test_full_training_attribution_still_fits_the_durable_event_budget(engine):
    rng = random.Random(112)  # noqa: S311 -- deterministic payload stress
    job = queued_job(engine)
    fields = [
        "prepare_seconds",
        "reconstruct_seconds",
        "reconstruct_cpu_seconds",
        "reconstruct_gc_count",
        "reconstruct_gc_seconds",
        "reconstruct_gc_max_seconds",
        "reconstruct_gc_max_started_at",
        "fit_seconds",
        "fit_cpu_seconds",
        "publication_wait_seconds",
        "publication_lock_seconds",
        "publication_collect_seconds",
        *[
            f"publication_blocked_{reason}_seconds"
            for reason in (
                "maintenance",
                "storage",
                "boundary",
                "dequeued",
                "batch",
                "queue",
                "priority",
                "lag",
                "recheck",
            )
        ],
    ]
    job.phase_seconds.update({name: rng.random() * 120 for name in fields})
    engine.diagnostics.enabled = True
    engine._record_training_diagnostics(job, True, job.started_monotonic)
    assert engine.diagnostics.publications
    for _, events in engine.diagnostics.publications:
        for event in events:
            encode(event, max_payload=MAX_EVENT_PAYLOAD)


@pytest.mark.parametrize(
    "block", ["maintenance", "storage", "boundary", "dequeued", "batch", "queue", "priority", "lag"]
)
def test_publication_reason_preserves_each_existing_guard(engine, block):
    engine.last_processing_lag_seconds = 0
    event = MarketEvent(event_id="guard", source="test", kind=EventKind.TRADE)
    if block == "maintenance":
        engine._maintenance_requested = True
    elif block == "storage":
        engine._storage_maintenance_active = True
    elif block == "boundary":
        engine.event_queue.begin_boundary(0)
    elif block == "dequeued":
        engine.event_queue.put_nowait((0, 0, event))
        engine.event_queue.get_nowait()
    elif block == "batch":
        engine._event_batches_in_flight = 1
    elif block == "queue":
        engine.settings.event_queue_max = 20
        engine.event_queue.put_nowait((4, 0, event))
    elif block == "priority":
        engine.event_queue.put_nowait((0, 0, event))
    else:
        engine.last_processing_lag_seconds = float("nan")
    assert engine._learning_publication_blocked_reason() == block
    assert not engine._learning_publication_can_run()


def test_publication_retry_records_reason_without_shortening_wait(engine, clock, monkeypatch):
    job = queued_job(engine)
    engine._maintenance_requested = True
    calls = []

    async def wait(seconds):
        assert seconds == 0.25
        clock[0] += 3  # Includes delayed task resumption, not three seconds of CPU.
        engine._maintenance_requested = False

    def finish(*args, **kwargs):
        calls.append(True)
        return True

    monkeypatch.setattr(engine, "_wait_for_stop", wait)
    monkeypatch.setattr(engine.learning, "finish_training_job", finish)
    monkeypatch.setattr(engine, "_record_training_diagnostics", lambda *args: None)
    monkeypatch.setattr(engine, "_collect_before_publication", lambda *args: None)
    assert asyncio.run(engine._publish_training_job(engine.learning, job, None))
    assert calls == [True]
    assert job.phase_seconds["publication_blocked_maintenance_seconds"] == 3
    assert job.phase_seconds["publication_wait_seconds"] == 3
    assert job.phase_seconds["publication_collect_seconds"] == 0


@pytest.mark.parametrize("ending", ["success", "error", "cancel"])
def test_heartbeat_detail_is_exported_only_after_worker_finishes(engine, ending):
    started, release, finished = Event(), Event(), Event()
    timing = {}

    def worker():
        with measure_work("checkpoint_select"):
            started.set()
            assert release.wait(3)
        with measure_work("checkpoint_govern"):
            finished.set()
            if ending == "error":
                raise ValueError("injected")
        return 42

    async def exercise():
        token = _HEARTBEAT_WORK.set(timing)
        try:
            task = asyncio.create_task(_timed_to_thread(engine.diagnostics, "heartbeat", worker))
            try:
                for _ in range(1000):
                    if started.is_set():
                        break
                    await asyncio.sleep(0.001)
                assert started.is_set() and not timing
                if ending == "cancel":
                    task.cancel()
                    await asyncio.sleep(0)
                    task.cancel()
                    await asyncio.sleep(0)
                    assert not task.done() and not timing
            finally:
                release.set()
            if ending == "success":
                assert await task == 42
            else:
                with pytest.raises(asyncio.CancelledError if ending == "cancel" else ValueError):
                    await task
            assert finished.is_set()
            assert {
                "dispatch",
                "worker",
                "worker_cpu",
                "resume",
                "checkpoint_select",
                "checkpoint_govern",
            } <= timing.keys()
            assert all(value >= 0 for value in timing.values())
        finally:
            _HEARTBEAT_WORK.reset(token)

    engine.diagnostics.enabled = True
    asyncio.run(exercise())
