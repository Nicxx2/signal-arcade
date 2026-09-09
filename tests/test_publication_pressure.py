"""A completed optional fit must reconsider newly arrived protected market work."""

import asyncio
import time
from datetime import UTC, datetime
from threading import Event
from types import SimpleNamespace

import pytest
from signal_arcade.intelligence.training_job import TrainingOutput
from signal_arcade.models import EventKind, MarketEvent
from signal_arcade.orchestrator import Orchestrator
from test_v1104_training_history import training_fixture


def queued_job(engine):
    key = (engine.learning.current_risk_mode, engine.learning.configuration_fingerprint())
    engine.learning._training_active = key
    return SimpleNamespace(
        workspace=SimpleNamespace(_training_output=TrainingOutput()),
        authority_context=engine.learning._training_authority_context(),
        runtime_context=engine._training_runtime_context(),
        started_monotonic=time.monotonic(),
        phase_seconds={},
        key=key,
        requested_at=datetime.now(UTC),
    )


def test_publication_rechecks_pressure_that_arrives_during_fit(settings, monkeypatch):
    engine = Orchestrator(settings)
    engine.learning.request_current_training()
    publications, waits = [], []
    job = SimpleNamespace(
        workspace=SimpleNamespace(_training_output=None),
        authority_context=engine.learning._training_authority_context(),
        runtime_context=engine._training_runtime_context(),
        started_monotonic=time.monotonic(),
        phase_seconds={},
        key=(engine.learning.current_risk_mode, engine.learning.configuration_fingerprint()),
        requested_at=datetime.now(UTC),
    )
    original_gate = engine._learning_training_can_run

    async def exercise():
        loop = asyncio.get_running_loop()
        arrived = Event()

        def enqueue():
            engine.event_queue.put_nowait(
                (0, 1, MarketEvent(event_id="protected", source="fixture", kind=EventKind.TRADE))
            )
            arrived.set()

        def fit(_job):
            loop.call_soon_threadsafe(enqueue)
            assert arrived.wait(2)

        def finish(_job, **kwargs):
            publications.append(original_gate())
            engine.stop_event.set()
            return True

        async def wait(seconds):
            waits.append(seconds)
            assert seconds >= 0.01
            if not engine.event_queue.empty():
                engine.event_queue.get_nowait()
                engine.event_queue.task_done()
            await asyncio.sleep(0)

        monkeypatch.setattr(engine.learning, "prepare_next_training", lambda context: job)
        monkeypatch.setattr(engine.learning, "fit_training_job", fit)
        monkeypatch.setattr(engine.learning, "finish_training_job", finish)
        monkeypatch.setattr(engine, "_record_training_diagnostics", lambda *args: None)
        monkeypatch.setattr(engine, "_wait_for_stop", wait)
        try:
            await asyncio.wait_for(engine._learning_trainer_loop(), 3)
            assert publications == [True]
            assert waits
        finally:
            await engine.http.close()

    try:
        asyncio.run(exercise())
    finally:
        engine.database.close()


@pytest.mark.parametrize(
    "change", ["urgent", "in_flight", "lag", "maintenance", "storage", "boundary"]
)
def test_publication_rechecks_after_waiting_for_market_boundary(settings, monkeypatch, change):
    engine = Orchestrator(settings)
    job = queued_job(engine)
    publications, waits = [], []

    def finish(*args, **kwargs):
        publications.append(engine._learning_publication_can_run())
        return True

    async def wait(seconds):
        waits.append(seconds)
        while not engine.event_queue.empty():
            engine.event_queue.get_nowait()
            engine.event_queue.task_done()
        engine.event_queue.end_boundary()
        engine._event_batches_in_flight = 0
        engine.last_processing_lag_seconds = 0
        engine._maintenance_requested = engine._storage_maintenance_active = False
        await asyncio.sleep(0)

    monkeypatch.setattr(engine.learning, "finish_training_job", finish)
    monkeypatch.setattr(engine, "_wait_for_stop", wait)
    monkeypatch.setattr(engine, "_record_training_diagnostics", lambda *args: None)

    async def exercise():
        await engine._event_lock.acquire()
        task = asyncio.create_task(engine._publish_training_job(engine.learning, job, None))
        try:
            await asyncio.sleep(0)
            if change == "urgent":
                engine.event_queue.put_nowait(
                    (0, 1, MarketEvent(event_id="urgent", source="test", kind=EventKind.TRADE))
                )
            elif change == "in_flight":
                engine._event_batches_in_flight = 1
            elif change == "lag":
                engine.last_processing_lag_seconds = 5
            elif change == "maintenance":
                engine._maintenance_requested = True
            elif change == "storage":
                engine._storage_maintenance_active = True
            else:
                engine.event_queue.begin_boundary(1)
        finally:
            engine._event_lock.release()
        await asyncio.wait_for(task, 2)
        assert publications == [True]
        assert waits and all(delay >= 0.1 for delay in waits)
        await engine.http.close()

    try:
        asyncio.run(exercise())
    finally:
        engine.database.close()


def test_completed_fit_can_publish_with_small_candidate_backlog(settings):
    engine = Orchestrator(settings)
    job = queued_job(engine)
    engine.event_queue.put_nowait(
        (2, 1, MarketEvent(event_id="candidate", source="test", kind=EventKind.TRADE))
    )

    async def exercise():
        assert not engine._learning_training_can_run()
        assert engine._learning_publication_can_run()
        assert await engine._publish_training_job(engine.learning, job, None)
        assert engine.event_queue.qsize() == 1
        assert engine.learning._training_active is None
        await engine.http.close()

    try:
        asyncio.run(exercise())
    finally:
        engine.database.close()


@pytest.mark.parametrize("change", ["age", "season", "authority", "shutdown"])
def test_deferred_real_fit_cannot_publish_after_its_validity_changes(settings, monkeypatch, change):
    learner, database, _ = training_fixture(settings)
    engine = Orchestrator(settings)
    original_database = engine.database
    engine.learning, engine.database = learner, database
    job = learner.prepare_next_training(engine._training_runtime_context())
    learner.fit_training_job(job)
    engine.event_queue.put_nowait(
        (0, 1, MarketEvent(event_id="held", source="test", kind=EventKind.TRADE))
    )

    async def wait(_seconds):
        if change == "age":
            job.started_monotonic -= 121
        elif change == "season":
            engine.broker.season_id = "different-season"
        elif change == "authority":
            learner.consent_granted = not learner.consent_granted
        else:
            engine.stop_event.set()
        engine.event_queue.get_nowait()
        engine.event_queue.task_done()
        await asyncio.sleep(0)

    monkeypatch.setattr(engine, "_wait_for_stop", wait)

    async def exercise():
        assert not await engine._publish_training_job(learner, job, None)
        assert not database.list_learning_models()
        assert not database.list_challenger_artifacts()
        assert learner._training_active is None
        assert learner.has_pending_training()
        await engine.http.close()

    try:
        asyncio.run(exercise())
    finally:
        database.close()
        original_database.close()


def test_cancelled_deferred_trainer_releases_job_and_preserves_request(settings, monkeypatch):
    engine = Orchestrator(settings)
    job = queued_job(engine)
    engine.learning.request_current_training()
    entered = asyncio.Event()

    def fit(_job):
        engine._event_batches_in_flight = 1

    async def wait(_seconds):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(engine.learning, "prepare_next_training", lambda context: job)
    monkeypatch.setattr(engine.learning, "fit_training_job", fit)
    monkeypatch.setattr(engine, "_wait_for_stop", wait)

    async def exercise():
        task = asyncio.create_task(engine._learning_trainer_loop())
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert engine.learning._training_active is None
        assert job.key in engine.learning._training_requests
        assert not engine.database.list_learning_models()
        await engine.http.close()

    try:
        asyncio.run(exercise())
    finally:
        engine.database.close()


@pytest.mark.parametrize("coalesced", [False, True])
def test_cancellation_during_preparation_releases_job_before_resuming(
    settings, monkeypatch, coalesced
):
    engine = Orchestrator(settings)
    learner = engine.learning
    learner.request_current_training()
    key = next(iter(learner._training_requests))
    requested_at = learner._training_requests[key]
    entered, release = Event(), Event()
    prepare = learner.prepare_next_training

    def delayed(context):
        job = prepare(context)
        assert job is not None
        entered.set()
        assert release.wait(3)
        return job

    monkeypatch.setattr(learner, "prepare_next_training", delayed)

    async def exercise():
        task = asyncio.create_task(engine._learning_trainer_loop())
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            assert learner._training_active == key
            if coalesced:
                learner.request_current_training()
            pending_at = learner._training_requests.get(key, requested_at)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            assert engine._event_lock.locked()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not engine._event_lock.locked()
        assert learner._training_active is None
        assert learner._training_requests[key] == pending_at
        assert not engine.database.list_learning_models()
        assert not engine.database.list_challenger_artifacts()
        # Reusing this learner must be able to prepare again, without a process reset.
        next_job = prepare(engine._training_runtime_context())
        assert next_job is not None
        learner.release_unpublished_training_job(next_job)

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


@pytest.mark.parametrize("ending", ["not_due", "error", "fit"])
def test_cancelled_trainer_handles_empty_failed_and_fitting_preparation(
    settings, monkeypatch, ending
):
    engine = Orchestrator(settings)
    learner = engine.learning
    learner.request_current_training()
    entered, release = Event(), Event()

    def blocked(*args):
        entered.set()
        assert release.wait(3)
        if ending == "error":
            raise ValueError("injected preparation failure")
        return object()

    if ending == "fit":
        monkeypatch.setattr(learner, "fit_training_job", blocked)
    else:
        monkeypatch.setattr(learner, "_latest_model_for_context", blocked)
        monkeypatch.setattr(learner, "_new_outcomes_since_model", lambda model: 0)

    async def exercise():
        task = asyncio.create_task(engine._learning_trainer_loop())
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert learner._training_active is None
        assert learner.has_pending_training() == (ending != "not_due")
        assert not engine._event_lock.locked()
        assert not engine.database.list_learning_models()
        assert not engine.database.list_challenger_artifacts()

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()
