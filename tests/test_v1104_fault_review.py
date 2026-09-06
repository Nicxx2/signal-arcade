from __future__ import annotations

import asyncio
import sqlite3
import threading
from datetime import UTC, datetime

import pytest
from signal_arcade.database import Database
from signal_arcade.intelligence.learning import LearningEngine
from signal_arcade.models import EventKind, MarketEvent
from signal_arcade.orchestrator import Orchestrator
from test_v1104_seasons import event
from test_v1104_training_history import training_fixture


def test_source_switch_discards_parked_events_and_fences_an_already_dequeued_batch(
    settings, monkeypatch
):
    engine = Orchestrator(settings)
    engine.demo_mode = False

    async def no_source():
        pass

    monkeypatch.setattr(engine, "_start_source", no_source)
    old = MarketEvent(
        event_id="live-create",
        kind=EventKind.CREATE,
        source="solana:test",
        mint="old-live-mint",
        received_at=datetime.now(UTC),
    )
    engine._event_sequence = 2
    engine.event_queue.put_nowait((0, 1, old))
    dequeued = engine.event_queue.get_nowait()
    engine.event_queue.begin_boundary(1)
    engine.event_queue.put_nowait((0, 2, event(2)))

    async def scenario():
        await engine.set_demo_mode(True)
        assert engine.event_queue.qsize() == 0
        assert not engine.event_queue.boundary_active
        assert not await engine._handle_persisted_event(dequeued[2], sequence=dequeued[1])
        assert old.mint not in engine.features.tokens
        fresh = old.model_copy(
            update={"event_id": "demo-create", "source": "demo", "mint": "new-demo-mint"}
        )
        assert await engine._handle_persisted_event(fresh)
        assert fresh.mint in engine.features.tokens
        engine.event_queue.task_done()
        await asyncio.wait_for(engine.event_queue.join(), 1)

    try:
        asyncio.run(scenario())
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


def test_cancellation_during_batch_wait_releases_admitted_work(settings, monkeypatch):
    engine = Orchestrator(settings)
    monkeypatch.setattr(engine, "_event_batch_wait_seconds", lambda: 60)

    async def scenario():
        engine.event_queue.put_nowait((0, 1, event(1)))
        engine.event_queue.begin_boundary(1)
        worker = asyncio.create_task(engine._event_worker_loop())
        for _ in range(100):
            if engine._event_batches_in_flight:
                break
            await asyncio.sleep(0.001)
        assert engine._event_batches_in_flight == 1
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        assert engine._event_batches_in_flight == 0
        assert engine.event_queue.boundary_ready()
        await asyncio.wait_for(engine.event_queue.join(), 1)

    try:
        asyncio.run(scenario())
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


def test_direct_event_append_cannot_cross_a_source_switch(settings, monkeypatch):
    engine = Orchestrator(settings)
    engine.demo_mode = False
    entered, release = threading.Event(), threading.Event()

    async def no_source():
        pass

    def delayed_append(_event):
        entered.set()
        assert release.wait(3)
        return True

    monkeypatch.setattr(engine, "_start_source", no_source)
    monkeypatch.setattr(engine.database, "append_event", delayed_append)
    old = MarketEvent(
        event_id="delayed-live-create",
        kind=EventKind.CREATE,
        source="solana:test",
        mint="delayed-live-mint",
        received_at=datetime.now(UTC),
    )

    async def scenario():
        task = asyncio.create_task(engine.handle_event(old))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            await engine.set_demo_mode(True)
        finally:
            release.set()
            await task
        assert old.mint not in engine.features.tokens

    try:
        asyncio.run(scenario())
    finally:
        release.set()
        asyncio.run(engine.http.close())
        engine.database.close()


@pytest.mark.parametrize("failure", ["mid_artifact", "commit", "restart"])
def test_partial_training_publication_rolls_back_and_can_retry(settings, monkeypatch, failure):
    learner, database, context = training_fixture(settings)
    for observation in learner.observations.values():
        database.save_learning_observation(observation)
    if failure == "commit":
        database._conn.executescript(
            "CREATE TABLE fault_parent(id INTEGER PRIMARY KEY);"
            "CREATE TABLE fault_child(parent_id INTEGER REFERENCES fault_parent(id) "
            "DEFERRABLE INITIALLY DEFERRED);"
        )
    job = learner.prepare_next_training()
    learner.fit_training_job(job)
    assert len(job.workspace._training_output.artifacts) > 1
    save = database.save_challenger_artifact
    calls = 0

    def fail_second(artifact):
        nonlocal calls
        calls += 1
        assert not learner.models and not learner.skill_artifacts and not learner.skill_states
        if calls == 2:
            if failure == "commit":
                database._conn.execute("INSERT INTO fault_child VALUES(1)")
            else:
                raise sqlite3.OperationalError("injected disk-full failure")
        save(artifact)

    monkeypatch.setattr(database, "save_challenger_artifact", fail_second)
    try:
        with pytest.raises(sqlite3.Error):
            learner.finish_training_job(job)
        assert not database.list_learning_models()
        assert not database.list_challenger_artifacts()
        assert not database.list_challenger_skill_states()
        assert not learner.models and not learner.skill_artifacts and not learner.skill_states
        monkeypatch.setattr(database, "save_challenger_artifact", save)
        if failure == "restart":
            database.close()
            database = Database(settings.database_path)
            learner = LearningEngine(
                database, settings, configuration_fingerprint=lambda: context[0]
            )
            learner.request_current_training()
        assert learner.run_next_training()
        assert database.list_learning_models()
        assert len(database.list_challenger_artifacts()) == len(
            job.workspace._training_output.artifacts
        )
    finally:
        database.close()
