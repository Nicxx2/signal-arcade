from __future__ import annotations

import asyncio
import copy
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.intelligence.learning import TRAINING_INPUTS, _skill_qualification_gates
from signal_arcade.intelligence.training_job import TrainingOutput
from signal_arcade.models import ChallengerSkill, EventKind, MarketEvent
from signal_arcade.orchestrator import Orchestrator
from test_v1104_training_history import training_fixture

# These regressions deliberately exercise boundaries and interrupt private workers.
# ruff: noqa: SLF001


def test_dashboard_pressure_reuses_view_but_cannot_defer_it_indefinitely(settings, monkeypatch):
    engine = Orchestrator(settings)
    calls = []

    def snapshot():
        calls.append(True)
        return {}

    monkeypatch.setattr(engine, "snapshot", snapshot)

    async def exercise():
        first = await engine.snapshot_view()
        original_task = engine._ui_snapshot_task
        _, generated, payload = engine._ui_snapshot_cache
        engine.last_processing_lag_seconds = 5
        engine._ui_snapshot_cache = (time.monotonic() - 6, generated, payload)
        stale = await engine.snapshot_view()
        assert len(calls) == 1 and engine._ui_snapshot_task is original_task
        assert stale["snapshot_generated_at"] == first["snapshot_generated_at"]
        # Elapsed reuse time, not continuing pressure or repeated polling, admits one refresh.
        engine._ui_snapshot_cache = (time.monotonic() - 13, generated, payload)
        await engine.snapshot_view()
        assert len(calls) == 2
        # Explicit actions bypass adaptive reuse even during pressure.
        engine.invalidate_snapshot_cache()
        await engine.snapshot_view()
        assert len(calls) == 3
        await engine.http.close()

    try:
        asyncio.run(exercise())
    finally:
        engine.database.close()


def test_dashboard_cost_budget_recovers_after_a_fast_refresh(settings):
    engine = Orchestrator(settings)
    try:
        assert engine._snapshot_cache_seconds() == 5
        engine._ui_snapshot_last_duration = 1
        assert engine._snapshot_cache_seconds() == 9
        engine._ui_snapshot_last_duration = 100
        assert engine._snapshot_cache_seconds() == 12
        engine._ui_snapshot_last_duration = 0.01
        assert engine._snapshot_cache_seconds() == 5
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


def test_not_due_training_skips_copy_and_keeps_new_request(settings, monkeypatch):
    learner, database, _ = training_fixture(settings)
    assert learner.run_next_training()
    assert learner.models
    published = learner.training_status()["published_models"]
    learner.request_current_training()
    original = learner._new_outcomes_since_model

    def readiness(model):
        learner.request_current_training()
        return original(model)

    monkeypatch.setattr(learner, "_new_outcomes_since_model", readiness)
    assert learner.prepare_next_training() is None
    assert learner.has_pending_training()
    assert learner.training_status()["published_models"] == published
    assert learner.training_status()["skipped_not_due"] == 1
    assert learner.training_status()["state"] == "queued"
    database.close()


def test_empty_fit_does_not_publish_or_prune(settings, monkeypatch):
    learner, database, _ = training_fixture(settings)
    job = learner.prepare_next_training()
    assert job is not None

    def unexpected():
        pytest.fail("an empty fit must not prune unchanged models")

    monkeypatch.setattr(learner, "_prune_model_history", unexpected)
    # Publication can see an empty output even after preparation was eligible.
    assert learner.finish_training_job(job)
    assert learner.training_status()["published_models"] == 0
    assert learner.training_status()["skipped_not_due"] == 1
    assert database.list_learning_models() == []
    database.close()


def test_skill_gates_follow_testing_artifact_then_latest(settings):
    learner, database, _ = training_fixture(settings)
    assert learner.run_next_training()
    state = learner._current_skill_state(ChallengerSkill.ENTRY)
    original = learner.skill_artifacts[state.latest_candidate_version]
    testing = original.model_copy(update={"version": "testing", "sample_count": 123})
    latest = original.model_copy(update={"version": "latest", "sample_count": 4})
    learner.skill_artifacts.update(testing=testing, latest=latest)
    state.latest_candidate_version = "latest"
    state.testing_version = "testing"
    status = next(item for item in learner.skill_statuses() if item["skill"] == "entry")
    assert status["testing_candidate"]["version"] == status["gate_artifact_version"] == "testing"
    assert status["gates"] == _skill_qualification_gates(ChallengerSkill.ENTRY, testing)
    state.testing_version = None
    status = next(item for item in learner.skill_statuses() if item["skill"] == "entry")
    assert status["gate_artifact_version"] == "latest"
    assert status["gate_subject"] == "latest_candidate"
    assert status["gates"] == _skill_qualification_gates(ChallengerSkill.ENTRY, latest)
    database.close()


def test_compact_training_retains_nonlinear_fit_and_payload(settings):
    learner, database, _ = training_fixture(settings)
    originals = list(learner.observations.values())
    learner.observations = {}
    start = datetime.now(UTC) - timedelta(days=1)
    for i in range(600):
        item = originals[i % len(originals)].model_copy(deep=True)
        item.mint = f"nonlinear-{i}"
        item.created_at = start + timedelta(minutes=i)
        left, right = (i * 37 % 101) / 100, (i * 61 % 103) / 102
        item.features["opportunity"] = left
        item.features["momentum"] = right
        item.checkpoints["300"].observed_at = item.created_at + timedelta(minutes=5)
        item.checkpoints["300"].net_return = 0.3 if (left > 0.5) == (right > 0.5) else -0.2
        learner.observations[item.mint] = item
    compact = learner.prepare_next_training()
    assert compact is not None
    workspace = copy.copy(compact.workspace)
    workspace._training_output = TrainingOutput()
    workspace._evidence_episode_ids_by_mint = {}
    full = replace(
        compact,
        workspace=workspace,
        phase_seconds={},
        frozen_inputs=TRAINING_INPUTS.dump_json(
            (
                list(learner.observations.values()),
                list(learner.evidence_episodes.values()),
                learner.models,
                list(learner.skill_artifacts.values()),
                list(learner.skill_states.values()),
            ),
            round_trip=True,
        ),
    )
    learner.fit_training_job(compact)
    learner.fit_training_job(full)

    def nonlinear(job):
        return next(
            (artifact, payload)
            for artifact, _, payload in job.workspace._training_output.artifacts
            if artifact.model_family.value == "xgboost"
        )

    compact_artifact, compact_payload = nonlinear(compact)
    full_artifact, full_payload = nonlinear(full)
    assert compact_payload == full_payload
    assert compact_artifact.metrics == full_artifact.metrics
    assert compact_artifact.parameters == full_artifact.parameters
    assert compact_artifact.qualified == full_artifact.qualified
    assert compact_artifact.evidence_cohort_digest == full_artifact.evidence_cohort_digest
    database.close()


def test_legacy_manual_comparison_flag_is_normalized_without_rewriting_scorecard(settings):
    from test_profile_transitions import prepare_locked_orchestrator

    engine = prepare_locked_orchestrator(settings)
    engine.broker.reset()
    archived = engine.database.list_paper_seasons()[0]
    assert archived["boundary_type"] == "reset"
    assert archived["comparable"] is False
    # Reproduce the earlier release's flag, leaving the recorded accounting values untouched.
    with engine.database._conn:
        engine.database._conn.execute(
            "UPDATE paper_seasons SET comparable=1 WHERE season_id=?", (archived["season_id"],)
        )
    result = asyncio.run(engine.seasons_view())
    assert result["summary"]["comparable_seasons"] == 0
    assert result["seasons"][0]["net_pnl_minor"] == archived["net_pnl_minor"]
    assert engine.database.list_paper_seasons()[0]["recorded_comparable"] is True
    assert engine.database._conn.execute("SELECT comparable FROM paper_seasons").fetchone()[0] == 1
    asyncio.run(engine.http.close())
    engine.database.close()


@pytest.mark.parametrize("budget", [False, True])
def test_interrupted_cleanup_rolls_back_and_clears_progress_handler(tmp_path, budget):
    database = Database(tmp_path / "interrupt.sqlite3")
    now = datetime.now(UTC)
    database.append_events(
        [
            MarketEvent(
                event_id=f"event-{i:05d}",
                source="test",
                kind=EventKind.TRADE,
                mint="mint",
                received_at=now - timedelta(days=2),
            )
            for i in range(1000)
        ]
    )
    calls = 0

    def interrupt():
        nonlocal calls
        calls += 1
        return calls >= 5

    if budget:
        result = database.enforce_storage_budget(
            1, preserve_recent_events=0, max_rows_per_chunk=1000, stop_requested=interrupt
        )
    else:
        result = database.prune_history(now, max_rows_per_category=1000, stop_requested=interrupt)
    assert result["work_remaining"] == 1
    assert result["raw_trades"] == 0
    assert database.storage_stats(force=True)["market_events"] == 1000
    database.set_setting("after-interrupt", True)
    assert database.get_setting("after-interrupt") is True
    assert database.integrity_check()
    database.close()


def test_cleanup_preserves_timestamp_ties_and_short_history(tmp_path):
    database = Database(tmp_path / "ties.sqlite3")
    now = datetime.now(UTC)
    database.append_events(
        [
            MarketEvent(
                event_id=f"event-{i:02d}",
                source="test",
                kind=EventKind.TRADE,
                mint="mint",
                received_at=now,
            )
            for i in range(10)
        ]
    )
    result = database.enforce_storage_budget(1, preserve_recent_events=3)
    assert result["raw_trades"] == 7
    assert {event.event_id for event in database.recent_events()} == {
        "event-07",
        "event-08",
        "event-09",
    }
    assert database.enforce_storage_budget(1, preserve_recent_events=20)["raw_trades"] == 0
    database.close()


def test_timed_out_and_cancelled_browsers_keep_one_fair_refresh(settings, monkeypatch):
    engine = Orchestrator(settings)
    monkeypatch.setattr("signal_arcade.orchestrator._UI_SNAPSHOT_LOCK_WAIT_SECONDS", 0.02)

    async def exercise():
        first = await engine.snapshot_view()
        engine.invalidate_snapshot_cache()
        await engine._event_lock.acquire()
        try:
            stale = await engine.snapshot_view()
            task = engine._ui_snapshot_task
            browser = asyncio.create_task(engine.snapshot_view())
            await asyncio.sleep(0)
            browser.cancel()
            with pytest.raises(asyncio.CancelledError):
                await browser
            assert task is engine._ui_snapshot_task and not task.done()
            assert stale["snapshot_generated_at"] == first["snapshot_generated_at"]
        finally:
            engine._event_lock.release()
        # No further HTTP request is necessary for the queued refresh to make progress.
        fresh = await asyncio.wait_for(task, 2)
        assert fresh["snapshot_generated_at"] != first["snapshot_generated_at"]
        assert fresh["storage"]["row_counts_as_of"]
        await engine.http.close()

    asyncio.run(exercise())
    engine.database.close()


def test_refresh_shutdown_waits_for_thread_before_releasing_boundary(settings, monkeypatch):
    engine = Orchestrator(settings)
    entered = threading.Event()
    release = threading.Event()

    def snapshot():
        entered.set()
        release.wait(2)
        return {}

    monkeypatch.setattr(engine, "snapshot", snapshot)

    async def exercise():
        task = asyncio.create_task(engine._refresh_snapshot())
        assert await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        await asyncio.sleep(0.02)
        assert engine._event_lock.locked()
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not engine._event_lock.locked()
        await engine.http.close()

    try:
        asyncio.run(exercise())
    finally:
        release.set()
        engine.database.close()


def test_cleanup_cancellation_joins_its_database_thread(settings, monkeypatch):
    engine = Orchestrator(settings)
    entered = threading.Event()
    release = threading.Event()

    def prune(*_args, **kwargs):
        entered.set()
        release.wait(2)
        assert kwargs["stop_requested"]()
        return {"work_remaining": 1}

    monkeypatch.setattr(engine.database, "prune_history", prune)

    async def exercise():
        task = asyncio.create_task(engine._run_storage_maintenance(datetime.now(UTC)))
        assert await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        await asyncio.sleep(0.02)
        assert engine._storage_maintenance_active
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not engine._storage_maintenance_active
        await engine.http.close()

    try:
        asyncio.run(exercise())
    finally:
        release.set()
        engine.database.close()


@pytest.mark.parametrize("budget", [False, True])
def test_cleanup_yields_while_a_trading_writer_holds_the_connection(tmp_path, budget):
    database = Database(tmp_path / "busy-writer.sqlite3")
    now = datetime.now(UTC)
    database.append_event(
        MarketEvent(
            event_id="retained-during-contention",
            source="test",
            kind=EventKind.TRADE,
            mint="mint",
            received_at=now - timedelta(days=2),
        )
    )
    assert database.storage_stats()["market_events"] == 1
    finished = threading.Event()
    results = []
    errors = []

    def cleanup():
        try:
            result = (
                database.enforce_storage_budget(
                    1, preserve_recent_events=0, max_duration_seconds=0.05
                )
                if budget
                else database.prune_history(now, max_duration_seconds=0.05)
            )
            results.append(result)
        except Exception as exc:
            errors.append(exc)
        finally:
            finished.set()

    worker = threading.Thread(target=cleanup)
    try:
        with database._lock:
            worker.start()
            # The cleanup must return without waiting for this writer to release its lock.
            assert finished.wait(1)
        assert not errors
        assert results[0]["work_remaining"] == 1
        assert results[0]["raw_trades"] == 0
        assert len(database.recent_events()) == 1
        assert database.prune_history(now)["raw_trades"] == 1
        assert database.storage_stats()["market_events"] == 0
        database.set_setting("writer-after-contention", True)
        assert database.get_setting("writer-after-contention") is True
    finally:
        worker.join(2)
        database.close()


def test_failed_dashboard_refresh_can_retry_without_poisoning_its_cache(settings, monkeypatch):
    engine = Orchestrator(settings)
    snapshot = engine.snapshot

    def failed_snapshot():
        raise RuntimeError("injected snapshot read failure")

    async def exercise():
        original = await engine.snapshot_view()
        engine.invalidate_snapshot_cache()
        monkeypatch.setattr(engine, "snapshot", failed_snapshot)
        with pytest.raises(RuntimeError, match="injected snapshot read failure"):
            await engine.snapshot_view()
        assert not engine._event_lock.locked()
        assert engine._ui_snapshot_cache[1].isoformat() == original["snapshot_generated_at"]
        monkeypatch.setattr(engine, "snapshot", snapshot)
        recovered = await asyncio.wait_for(engine.snapshot_view(), 2)
        assert recovered["snapshot_generated_at"] != original["snapshot_generated_at"]
        assert recovered["version"] == original["version"]

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


@pytest.mark.parametrize("source", ["queue", "lag", "training"])
def test_dashboard_pressure_sources_bound_only_read_view_reuse(settings, monkeypatch, source):
    engine = Orchestrator(settings)
    try:
        if source == "queue":
            monkeypatch.setattr(engine.event_queue, "qsize", lambda: settings.event_queue_max)
        elif source == "lag":
            engine.last_processing_lag_seconds = 2
        else:
            engine.learning._training_active = object()
        assert engine._snapshot_cache_seconds() == 12
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()
