"""Keep cancellation and changing load from bypassing the market boundary."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from threading import Event, get_ident

import pytest
from signal_arcade.diagnostics import DiagnosticsRecorder
from signal_arcade.models import EventKind, MarketEvent
from signal_arcade.orchestrator import Orchestrator, _joined_to_thread, _timed_to_thread


@pytest.mark.parametrize("timed", [False, True])
@pytest.mark.parametrize("worker_error", [False, True])
def test_cancellation_joins_work_queued_behind_a_busy_executor(tmp_path, timed, worker_error):
    release = Event()
    calls = []
    recorder = DiagnosticsRecorder(tmp_path, enabled=True)

    async def exercise():
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
        occupied = asyncio.Event()
        boundary = asyncio.Lock()

        def busy():
            loop.call_soon_threadsafe(occupied.set)
            assert release.wait(5)

        def queued():
            calls.append("completed")
            if worker_error:
                raise RuntimeError("failure after queued cancellation")
            return 17

        async def owned():
            async with boundary:
                if timed:
                    return await _timed_to_thread(recorder, "heartbeat", queued)
                return await _joined_to_thread(queued)

        occupied_worker = loop.run_in_executor(None, busy)
        task = None
        try:
            await asyncio.wait_for(occupied.wait(), 2)
            task = asyncio.create_task(owned())
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            for _ in range(2):
                task.cancel()
                await asyncio.sleep(0)
            assert calls == []  # The only executor thread is still occupied.
            assert boundary.locked() and not task.done()
        finally:
            release.set()
            await asyncio.wait_for(occupied_worker, 2)
            if task is not None:
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, 2)
        assert calls == ["completed"]
        assert not boundary.locked()
        if timed:
            assert recorder.phases["heartbeat_cpu"][0] == 1
            assert recorder.phases["heartbeat_wait"][0] == 1

    try:
        asyncio.run(exercise())
    finally:
        release.set()


@pytest.mark.parametrize("operation", ["snapshot", "heartbeat", "market", "storage"])
@pytest.mark.parametrize("cancellations", [1, 2])
@pytest.mark.parametrize("worker_error", [False, True])
def test_cancelled_work_keeps_its_boundary_until_thread_exits(
    settings, monkeypatch, operation, cancellations, worker_error
):
    engine = Orchestrator(settings)
    entered, release, exited = Event(), Event(), Event()

    def blocked(*args, **kwargs):
        entered.set()
        try:
            assert release.wait(5), "test did not release worker"
            if worker_error:
                raise RuntimeError("injected worker failure")
            return {} if operation in {"snapshot", "storage"} else 0
        finally:
            exited.set()

    if operation == "snapshot":
        monkeypatch.setattr(engine, "snapshot", blocked)
        work = engine._refresh_snapshot
    elif operation == "heartbeat":
        monkeypatch.setattr(engine, "_heartbeat_tick", blocked)
        work = engine._heartbeat_loop
    elif operation == "market":
        monkeypatch.setattr(engine.learning, "has_pending_mint", lambda mint: True)
        monkeypatch.setattr(engine.learning, "observe_market", blocked)

        async def work():
            return await engine._handle_persisted_event(
                MarketEvent(event_id="one", mint="one", source="fixture", kind=EventKind.TRADE)
            )

    else:
        from datetime import UTC, datetime

        monkeypatch.setattr(engine.database, "prune_history", blocked)

        async def work():
            return await engine._run_storage_maintenance(datetime.now(UTC))

    async def exercise():
        task = asyncio.create_task(work())
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            for _ in range(cancellations):
                task.cancel()
                await asyncio.sleep(0)
            assert not task.done(), "async cancellation abandoned a running thread"
            if operation == "storage":
                assert engine._storage_maintenance_active
            else:
                assert engine._event_lock.locked()
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 3)
            assert exited.is_set()
            assert not engine._event_lock.locked()
            await engine.http.close()

    try:
        asyncio.run(exercise())
    finally:
        release.set()
        engine.database.close()


def test_joined_worker_preserves_context_result_and_normal_failure():
    context = ContextVar("worker-test", default="default")

    def work(value, *, fail=False):
        if fail:
            raise ValueError("worker error remains visible")
        return value, context.get()

    async def exercise():
        context.set("caller")
        assert await _joined_to_thread(work, 7) == (7, "caller")
        with pytest.raises(ValueError, match="worker error remains visible"):
            await _joined_to_thread(work, 7, fail=True)

    asyncio.run(exercise())


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("failure", [False, True])
def test_thread_timings_preserve_work_and_record_only_on_owner_thread(
    tmp_path, monkeypatch, enabled, failure
):
    recorder = DiagnosticsRecorder(tmp_path, enabled=enabled)
    recorded_on, workers = [], []
    original = recorder.observe_duration

    def record(name, duration):
        recorded_on.append(get_ident())
        original(name, duration)

    def work(value):
        workers.append(get_ident())
        if failure:
            raise ValueError("unchanged error")
        return value

    monkeypatch.setattr(recorder, "observe_duration", record)

    async def exercise():
        if failure:
            with pytest.raises(ValueError, match="unchanged error"):
                await _timed_to_thread(recorder, "heartbeat", work, 17)
        else:
            assert await _timed_to_thread(recorder, "heartbeat", work, 17) == 17
        assert workers[0] != get_ident()
        assert recorded_on == ([get_ident(), get_ident()] if enabled else [])
        assert set(recorder.phases) == ({"heartbeat_cpu", "heartbeat_wait"} if enabled else set())
        assert all(value[0] == 1 and value[1] >= 0 for value in recorder.phases.values())
        assert not recorder.queue and not recorder.events

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "change", ["quiet", "queue", "in_flight", "lag", "maintenance", "storage", "shutdown"]
)
def test_trainer_rechecks_admission_after_wait_and_preserves_request(
    settings, monkeypatch, change
):
    engine = Orchestrator(settings)
    engine.learning.request_current_training()
    pending = dict(engine.learning._training_requests)
    admitted, preparations, waits = [], [], []
    original_gate = engine._learning_training_can_run

    def gate():
        allowed = original_gate()
        admitted.append(allowed)
        return allowed

    def prepare(context):
        preparations.append(original_gate() and not engine.stop_event.is_set())
        assert engine.learning._training_requests == pending
        engine.stop_event.set()
        return None

    async def wait(seconds):
        waits.append(seconds)
        assert seconds >= 0.25, "a deferred trainer must not busy-spin"
        assert engine.learning._training_requests == pending
        if not engine.event_queue.empty():
            engine.event_queue.get_nowait()
            engine.event_queue.task_done()
        engine._event_batches_in_flight = 0
        engine.last_processing_lag_seconds = 0
        engine._maintenance_requested = False
        engine._storage_maintenance_active = False
        await asyncio.sleep(0)

    monkeypatch.setattr(engine, "_learning_training_can_run", gate)
    monkeypatch.setattr(engine.learning, "prepare_next_training", prepare)
    monkeypatch.setattr(engine, "_wait_for_stop", wait)

    async def exercise():
        await engine._event_lock.acquire()
        task = asyncio.create_task(engine._learning_trainer_loop())
        try:
            await asyncio.sleep(0)
            assert admitted == [True]
            if change == "queue":
                engine.event_queue.put_nowait(
                    (0, 1, MarketEvent(event_id="held", source="fixture", kind=EventKind.TRADE))
                )
            elif change == "in_flight":
                engine._event_batches_in_flight = 1
            elif change == "lag":
                engine.last_processing_lag_seconds = 4
            elif change == "maintenance":
                engine._maintenance_requested = True
            elif change == "storage":
                engine._storage_maintenance_active = True
            elif change == "shutdown":
                engine.stop_event.set()
        finally:
            engine._event_lock.release()
        await asyncio.wait_for(task, 3)
        assert preparations == ([] if change == "shutdown" else [True])
        assert bool(waits) == (change not in {"quiet", "shutdown"})
        assert engine.learning._training_requests == pending
        await engine.http.close()

    try:
        asyncio.run(exercise())
    finally:
        engine.database.close()


def test_shutdown_waits_for_heartbeat_before_closing_database(settings, monkeypatch):
    engine = Orchestrator(settings)
    entered, release = Event(), Event()
    database_open = []

    def heartbeat(now):
        entered.set()
        assert release.wait(5)
        database_open.append(engine.database.health_check())
        return [], [], 0, 0

    monkeypatch.setattr(engine, "_heartbeat_tick", heartbeat)

    async def exercise():
        engine.service_running = True
        worker = asyncio.create_task(engine._heartbeat_loop(), name="heartbeat")
        engine.tasks.add(worker)
        stop = None
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            stop = asyncio.create_task(engine.stop())
            await asyncio.wait_for(engine.stop_event.wait(), 2)
            await asyncio.sleep(0)
            assert not stop.done()
            assert engine._event_lock.locked()
        finally:
            release.set()
            await asyncio.wait_for(stop if stop is not None else engine.stop(), 3)
        assert database_open == [True]

    try:
        asyncio.run(exercise())
    finally:
        release.set()
        engine.database.close()
