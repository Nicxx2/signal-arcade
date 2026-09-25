"""Observational GC and worker disposal cannot change fitted or published evidence."""

import asyncio
import gc
from concurrent.futures import ThreadPoolExecutor
from threading import Event, get_ident
from types import SimpleNamespace

import pytest
import signal_arcade.intelligence.training_job as jobs
from signal_arcade.orchestrator import _joined_to_thread
from test_v1104_training_history import training_fixture


@pytest.mark.parametrize("ending", ["success", "error", "removed"])
def test_gc_observation_restores_hooks_and_keeps_original_max_timestamp(monkeypatch, ending):
    callbacks = []
    monkeypatch.setattr(jobs, "gc", SimpleNamespace(callbacks=callbacks))
    clock = [10.0]
    monkeypatch.setattr(
        jobs, "time", SimpleNamespace(monotonic=lambda: clock[0], time=lambda: clock[0] + 1000)
    )
    phases = {}

    def run():
        with jobs.observe_training_gc(phases, enabled=True):
            callback = callbacks[0]
            callback("start", {"generation": 0})
            callback("stop", {"generation": 0})
            for start, stop in ((10.0, 12.0), (13.0, 13.1)):
                clock[0] = start
                callback("start", {"generation": 2})
                clock[0] = stop
                callback("stop", {"generation": 2})
            if ending == "error":
                raise ValueError("fixture")
            if ending == "removed":
                callbacks.clear()

    if ending == "error":
        with pytest.raises(ValueError, match="fixture"):
            run()
    else:
        run()
    assert not callbacks
    assert phases == {
        "reconstruct_gc_count": 2.0,
        "reconstruct_gc_seconds": pytest.approx(2.1),
        "reconstruct_gc_max_seconds": 2.0,
        "reconstruct_gc_max_started_at": 1010.0,
    }


def test_disabled_gc_observer_leaves_global_policy_unchanged():
    before = (gc.isenabled(), gc.get_threshold(), list(gc.callbacks))
    phases = {}
    with jobs.observe_training_gc(phases, enabled=False):
        assert list(gc.callbacks) == before[2]
    assert (gc.isenabled(), gc.get_threshold(), list(gc.callbacks)) == before
    assert phases == {}


def test_disposal_preserves_published_models_artifacts_and_current_evidence(settings):
    learner, db, _ = training_fixture(settings, count=400)
    try:
        job = learner.prepare_next_training()
        assert job is not None
        learner.fit_training_job(job)
        assert learner.finish_training_job(job)
        models = [model.model_dump(mode="json") for model in learner.models]
        artifacts = {
            key: value.model_dump(mode="json") for key, value in learner.skill_artifacts.items()
        }
        observations = {
            key: value.model_dump(mode="json") for key, value in learner.observations.items()
        }
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(jobs.release_training_workspace, job).result(timeout=5)
        assert job.workspace is None and job.frozen_inputs == ()
        assert [model.model_dump(mode="json") for model in learner.models] == models
        assert {
            key: value.model_dump(mode="json") for key, value in learner.skill_artifacts.items()
        } == artifacts
        assert {
            key: value.model_dump(mode="json") for key, value in learner.observations.items()
        } == observations
        assert db.list_learning_models()
        assert db.list_challenger_artifacts()
    finally:
        db.close()


def test_repeated_cancellation_joins_disposal_off_loop():
    started, release = Event(), Event()
    destroyed = []

    class Workspace:
        def __del__(self):
            destroyed.append(get_ident())

    job = SimpleNamespace(workspace=Workspace(), frozen_inputs=(b"private",))

    def dispose():
        started.set()
        assert release.wait(5)
        jobs.release_training_workspace(job)

    async def run():
        owner = get_ident()
        task = asyncio.create_task(_joined_to_thread(dispose))
        try:
            for _ in range(1000):
                if started.is_set():
                    break
                await asyncio.sleep(0.001)
            assert started.is_set()
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(destroyed) == 1 and destroyed[0] != owner
        assert job.workspace is None

    asyncio.run(run())
