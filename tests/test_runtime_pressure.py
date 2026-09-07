from __future__ import annotations

import asyncio
import copy
import gc
import weakref
from collections import deque
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
from signal_arcade.ai_lab import AiDecisionLab
from signal_arcade.database import Database
from signal_arcade.intelligence.features import FeatureEngine
from signal_arcade.intelligence.training_job import (
    TRAINING_INPUTS,
    TrainingOutput,
    freeze_training_inputs,
    thaw_training_inputs,
)
from signal_arcade.models import AiDecisionMode, ChallengerSizeTrial, LearningCheckpoint
from signal_arcade.orchestrator import Orchestrator
from test_ai_lab import FakeHttp, _decision
from test_features_and_decisions import event
from test_v1104_training_history import training_fixture

# Exercise scheduling boundaries and compare the evidence used by the optimized paths.
# ruff: noqa: SLF001


def test_feature_window_discards_only_expired_trades_without_changing_features():
    from signal_arcade.models import EventKind

    start = datetime.now(UTC)
    engine = FeatureEngine()
    reference_trades = deque(maxlen=5000)
    for index in range(1001):
        state = engine.apply(
            event(
                f"e{index}",
                EventKind.TRADE,
                start + timedelta(seconds=index),
                {
                    "is_buy": index % 3 == 0,
                    "user": f"wallet-{index % 7}",
                    "sol_amount": 20_000_000 + index,
                    "token_amount": 1_000_000_000,
                    "virtual_token_reserves": 1_000_000_000_000_000,
                    "virtual_sol_reserves": 30_000_000_000,
                },
            )
        )
        reference_trades.append(state.trades[-1])
    assert len(state.trades) == 301
    assert state.trades[0].received_at == start + timedelta(seconds=700)
    assert state.last_evicted_trade is None
    reference = FeatureEngine()
    reference.tokens[state.mint] = copy.deepcopy(state)
    reference.tokens[state.mint].trades = reference_trades
    now = start + timedelta(seconds=1000)
    assert engine.snapshot(state.mint, now) == reference.snapshot(state.mint, now)
    # A regressed source timestamp uses the existing monotonic boundary, not a new old window.
    engine.apply(event("e1002", EventKind.TRADE, start, {"is_buy": True}))
    assert len(state.trades) == 302
    assert state.trades[-1].received_at == now


def test_training_copy_keeps_unknowns_times_and_sizing_economics_without_copying_audit(settings):
    learner, database, _ = training_fixture(settings)
    try:
        row = next(iter(learner.observations.values()))
        checkpoint = row.checkpoints["300"]
        checkpoint.route_snapshot = {"accounts": [{"sha256": "a" * 64}] * 1000}
        checkpoint.route_event_id = "verified-event"
        checkpoint.reserve_observed_at = checkpoint.observed_at
        row.checkpoints["600"] = LearningCheckpoint(
            horizon_seconds=600,
            observed_at=checkpoint.observed_at + timedelta(seconds=300),
            missing_reason="executable_exit_quote_unavailable",
            route_snapshot={"real_quote_reserves": 0},
        )
        from signal_arcade.models import LearningEvidenceEpisode, LearningEvidenceLane

        episode = LearningEvidenceEpisode(
            episode_id="policy-copy",
            idempotency_key="policy-copy",
            trajectory_key="policy-copy",
            lane=LearningEvidenceLane.POLICY,
            mint=row.mint,
            symbol=row.symbol,
            created_at=row.created_at,
            entry_at=row.created_at,
            risk_mode=row.risk_mode,
            baseline_version=row.baseline_version,
            feature_schema_version=row.feature_schema_version,
            baseline_action=row.baseline_action,
            checkpoints=copy.deepcopy(row.checkpoints),
            size_trials={
                "1.0": ChallengerSizeTrial(
                    multiplier=1,
                    budget_lamports=100,
                    token_units=1000,
                    entry_cost_lamports=100,
                    eligible_at_entry=True,
                    checkpoints=copy.deepcopy(row.checkpoints),
                )
            },
        )
        originals = copy.deepcopy((row, episode))
        frozen = freeze_training_inputs(([row], [episode], [], [], []))
        copied_row, copied_episode = [part[0] for part in thaw_training_inputs(frozen)[:2]]
        assert (row, episode) == originals
        for original, copied in [
            (row, copied_row),
            (episode, copied_episode),
            (episode.size_trials["1.0"], copied_episode.size_trials["1.0"]),
        ]:
            for horizon in ("300", "600"):
                assert copied.checkpoints[horizon].route_snapshot is None
                assert copied.checkpoints[horizon].model_dump(exclude={"route_snapshot"}) == (
                    original.checkpoints[horizon].model_dump(exclude={"route_snapshot"})
                )
        assert copied_episode.size_trials["1.0"].entry_cost_lamports == 100
        assert sum(map(len, frozen)) < 20000
        learner.request_current_training()
        job = learner.prepare_next_training()
        assert job is not None
        learner.fit_training_job(job)
        assert job.frozen_inputs == ()
        assert job.workspace._training_output.models
    finally:
        database.close()


@pytest.mark.parametrize("ending", ["resume", "expire", "maintenance", "off", "cancel"])
def test_shadow_work_waits_for_market_and_rechecks_before_inference(settings, monkeypatch, ending):
    database = Database(settings.database_path)
    database.set_setting("ai_decision_mode", AiDecisionMode.SHADOW.value)
    allowed = False
    calls = []
    lab = AiDecisionLab(
        database,
        FakeHttp(),
        settings,
        select_model=lambda _: None,
        configuration_fingerprint=lambda: "config-test",
        shadow_can_run=lambda: allowed,
    )
    decision = _decision(datetime.now(UTC))

    async def assess(*args, **kwargs):
        calls.append(kwargs)
        return None

    monkeypatch.setattr(lab, "_assess", assess)

    async def scenario():
        nonlocal allowed
        lab.queued_mints.add(decision.mint)
        lab.queue.put_nowait((decision, {}))
        worker = asyncio.create_task(lab._worker_loop())
        try:
            await asyncio.sleep(0.01)
            assert lab.shadow_deferred and not calls
            assert decision.mint in lab.queued_mints
            if ending == "resume":
                allowed = True
            elif ending == "expire":
                decision.created_at -= timedelta(minutes=2)
                allowed = True
            elif ending == "maintenance":
                lab.maintenance_paused = True
                allowed = True
            elif ending == "off":
                lab.set_mode(AiDecisionMode.OFF)
                allowed = True
            else:
                worker.cancel()
            await asyncio.wait_for(lab.queue.join(), timeout=2)
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        assert not lab.shadow_deferred and not lab.queued_mints

    try:
        asyncio.run(scenario())
        assert len(calls) == (1 if ending == "resume" else 0)
        if calls:
            assert calls[0] == {"applied": False, "timeout_seconds": 28}
        assert lab.shadow_queue_drops == (1 if ending in {"expire", "maintenance", "off"} else 0)
        assert database.list_ai_assessments() == []
    finally:
        database.close()


def test_shadow_admission_protects_market_locks_and_training(settings):
    engine = Orchestrator(settings)

    async def scenario():
        assert engine._shadow_ai_can_run()
        async with engine._event_lock:
            assert not engine._shadow_ai_can_run()
        async with engine.http._ollama_generation_lock:
            assert not engine._shadow_ai_can_run()
        engine.learning._training_active = object()
        assert not engine._shadow_ai_can_run()
        engine.learning._training_active = None
        engine.last_processing_lag_seconds = 2
        assert not engine._shadow_ai_can_run()
        engine.last_processing_lag_seconds = 0
        assert engine._shadow_ai_can_run()

    try:
        asyncio.run(scenario())
    finally:
        engine.database.close()


def test_deferred_cleanup_is_paced_then_resumes_fast_catchup(settings, monkeypatch):
    engine = Orchestrator(settings)
    waits = []
    passes = 0

    async def wait(seconds):
        waits.append(seconds)

    async def cleanup(now):
        nonlocal passes
        passes += 1
        engine._storage_maintenance_requested = True
        engine._storage_maintenance_deferred_reason = (
            "protecting_market_throughput" if passes == 1 else None
        )
        if passes == 2:
            engine.stop_event.set()

    monkeypatch.setattr(engine, "_wait_for_stop", wait)
    monkeypatch.setattr(engine, "_run_storage_maintenance", cleanup)
    try:
        asyncio.run(engine._storage_loop())
        assert waits == [15, 2, 0.25]
        assert passes == 2
    finally:
        engine.database.close()


def test_compact_training_produces_identical_linear_and_xgboost_artifacts(settings, monkeypatch):
    import signal_arcade.intelligence.learning as learning_module

    learner, database, _ = training_fixture(settings)
    fixed_now = datetime.now(UTC)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    try:
        templates = list(learner.observations.values())
        learner.observations = {}
        for index in range(600):
            row = templates[index % len(templates)].model_copy(deep=True)
            row.mint = row.observation_id = row.decision_id = f"copy-proof-{index}"
            row.created_at = fixed_now - timedelta(minutes=700 - index)
            row.checkpoints["300"].observed_at = row.created_at + timedelta(seconds=300)
            row.checkpoints["300"].route_snapshot = {"accounts": [{"sha256": "a" * 64}]}
            learner.observations[row.mint] = row
        job = learner.prepare_next_training()
        assert job is not None
        reference = replace(
            job,
            workspace=copy.copy(job.workspace),
            frozen_inputs=(
                TRAINING_INPUTS.dump_json(
                    (list(learner.observations.values()), [], [], [], []),
                    round_trip=True,
                    exclude={0: {"__all__": {"size_trials", "challenger_evaluations"}}},
                ),
            ),
        )
        reference.workspace._training_output = TrainingOutput()
        monkeypatch.setattr(learning_module, "datetime", FixedDateTime)
        learner.fit_training_job(job)
        learner.fit_training_job(reference)
        actual = job.workspace._training_output
        expected = reference.workspace._training_output
        assert any(a.model_family.value == "xgboost" for a, _, _ in actual.artifacts)
        assert actual.models == expected.models
        # Some artifacts use the model's default wall-clock creation time. Their identity,
        # payload bytes, training/validation evidence and every qualification result must match.
        assert len(actual.artifacts) == len(expected.artifacts)
        for (actual_artifact, actual_cohort, actual_payload), (
            expected_artifact,
            expected_cohort,
            expected_payload,
        ) in zip(actual.artifacts, expected.artifacts, strict=True):
            assert actual_artifact.model_dump(exclude={"created_at"}) == (
                expected_artifact.model_dump(exclude={"created_at"})
            )
            assert actual_cohort == expected_cohort
            assert actual_payload == expected_payload
        assert not database.list_learning_models(), "fitting alone cannot publish authority"
    finally:
        database.close()


def test_idle_trainer_releases_completed_workspace(settings, monkeypatch):
    engine = Orchestrator(settings)
    finished = False
    references = []

    class WorkspaceJob:
        pass

    def prepare(*args):
        job = WorkspaceJob()
        references.append(weakref.ref(job))
        return job

    def finish(*args, **kwargs):
        nonlocal finished
        finished = True
        return True

    monkeypatch.setattr(engine.learning, "has_pending_training", lambda: not finished)
    monkeypatch.setattr(engine.learning, "prepare_next_training", prepare)
    monkeypatch.setattr(engine.learning, "fit_training_job", lambda job: None)
    monkeypatch.setattr(engine.learning, "finish_training_job", finish)
    monkeypatch.setattr(engine, "_record_training_diagnostics", lambda *args: None)

    async def scenario():
        idle = asyncio.Event()
        release = asyncio.Event()

        async def wait(seconds):
            if finished:
                idle.set()
                await release.wait()

        monkeypatch.setattr(engine, "_wait_for_stop", wait)
        worker = asyncio.create_task(engine._learning_trainer_loop())
        try:
            await asyncio.wait_for(idle.wait(), 3)
            gc.collect()
            assert references and references[0]() is None
        finally:
            engine.stop_event.set()
            release.set()
            await worker

    try:
        asyncio.run(scenario())
    finally:
        engine.database.close()


@pytest.mark.parametrize("phase", ["prepare", "fit", "publish", "fit_error"])
def test_shutdown_joins_training_phase_before_closing_database(settings, monkeypatch, phase):
    learner, database, _ = training_fixture(settings)
    engine = Orchestrator(settings)
    engine.database.close()
    engine.database = database
    engine.learning = learner
    entered, release = Event(), Event()
    database_was_open = []
    method = {
        "prepare": "prepare_next_training",
        "fit": "fit_training_job",
        "publish": "finish_training_job",
        "fit_error": "fit_training_job",
    }[phase]
    original = getattr(learner, method)

    def blocked_phase(*args, **kwargs):
        entered.set()
        assert release.wait(5), "test did not release the in-flight training thread"
        # Shutdown must keep the real database open even when the thread subsequently fails.
        database_was_open.append(database.integrity_check())
        if phase == "fit_error":
            raise RuntimeError("injected failure during shutdown")
        return original(*args, **kwargs)

    monkeypatch.setattr(learner, method, blocked_phase)

    async def scenario():
        engine.service_running = True
        worker = asyncio.create_task(engine._learning_trainer_loop(), name="learning-trainer")
        engine.tasks.add(worker)
        stop = None
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            stop = asyncio.create_task(engine.stop())
            await asyncio.wait_for(engine.stop_event.wait(), 2)
            await asyncio.sleep(0)
            assert not stop.done()
            assert not worker.cancelled()
        finally:
            release.set()
            await asyncio.wait_for(stop if stop is not None else engine.stop(), 5)
        assert worker.done() and not worker.cancelled()
        assert database_was_open == [True]
        assert learner._training_active is None
        if phase == "publish":
            # An atomic publication already admitted before stopping is allowed to finish.
            assert learner.training_status()["published_models"] == 1
        else:
            assert learner.training_status()["published_models"] == 0
        if phase == "fit_error":
            assert "injected failure" in learner.training_status()["last_error"]
            assert learner.has_pending_training()
        elif phase != "publish":
            assert learner.training_status()["discarded_stale_jobs"] == 1

    try:
        asyncio.run(scenario())
    finally:
        release.set()
        database.close()
