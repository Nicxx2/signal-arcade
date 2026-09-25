from __future__ import annotations

import asyncio
import copy
import json
from datetime import timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.diagnostics_store import DiagnosticsStore, read_events
from signal_arcade.intelligence.collection_diagnostics import (
    COLLECTION_STAGES,
    CollectionDiagnostics,
)
from signal_arcade.intelligence.learning import LearningEngine
from signal_arcade.intelligence.reserve_refresh import validated_learning_state
from signal_arcade.orchestrator import Orchestrator
from test_learning import make_decision, make_state
from test_v1104_refresh import route_fixture, scheduler_fixture


@pytest.mark.parametrize("fresh", [True, False])
def test_instrumentation_preserves_selection_clocks_and_shared_lane_accounting(fresh):
    learner, states, now = scheduler_fixture()
    if not fresh:
        for state in states.values():
            state.last_reserve_at = now - timedelta(minutes=5)
    shared = "policy-0"
    observation = copy.deepcopy(learner.observations["discovery-0"])
    observation.mint = shared
    learner.observations[shared] = observation
    before = copy.deepcopy(learner)
    targets = {}
    counters = CollectionDiagnostics()
    selected = LearningEngine.due_checkpoint_mints(
        learner, states, now, limit=4, fresh=fresh, diagnostics=counters, selection=targets
    )
    assert selected == LearningEngine.due_checkpoint_mints(
        before, states, now, limit=4, fresh=fresh
    )
    assert targets[shared] == [("discovery", 60), ("policy", 60)]
    assert sum(len(value) for value in targets.values()) == 5
    channel = "cache" if fresh else "rpc"
    counts = counters.snapshot()["counts"]
    assert counts["policy_60"][channel + "_selected"] == 3
    assert counts["discovery_60"][channel + "_selected"] == 2
    assert learner.observations == before.observations


@pytest.mark.parametrize(
    "action",
    [
        "accepted",
        "unavailable",
        "timeout",
        "error",
        "cancelled",
        "pressure",
        "learner",
        "route",
        "invalid",
    ],
)
def test_rpc_accounting_tracks_failure_without_creating_evidence(settings, monkeypatch, action):
    engine = Orchestrator(settings)
    engine.demo_mode = False
    settings.learning_reserve_refresh_enabled = True
    monkeypatch.setattr(engine, "_rollover_market_data_healthy", lambda _: True)
    state, response, _decoder, _now = route_fixture()
    engine.features.tokens[state.mint] = state
    original = copy.deepcopy(state)
    learner = engine.learning
    collection = learner.collection_diagnostics

    def select(*args, **kwargs):
        kwargs["selection"][state.mint] = [("discovery", 300), ("policy", 300)]
        return [state.mint]

    monkeypatch.setattr(learner, "due_checkpoint_mints", select)
    observed = []
    monkeypatch.setattr(learner, "observe_market", lambda *a, **kw: observed.append(a[0]) or 0)

    async def fetch(*args, **kwargs):
        assert not engine._event_lock.locked()
        assert kwargs["critical"] is False
        if action == "unavailable":
            return None
        if action == "timeout":
            raise TimeoutError
        if action == "error":
            raise ValueError("isolated test")
        if action == "cancelled":
            raise asyncio.CancelledError
        if action == "pressure":
            engine.last_processing_lag_seconds = 1
        if action == "learner":
            engine.learning = copy.copy(learner)
            engine.learning.collection_diagnostics = CollectionDiagnostics()
        if action == "route":
            engine.features.tokens[state.mint] = copy.deepcopy(state)
        if action == "invalid":
            response["slot"] = 1
        return response

    monkeypatch.setattr(engine.http, "solana_multiple_accounts", fetch)
    errors = {"timeout": TimeoutError, "error": ValueError, "cancelled": asyncio.CancelledError}
    try:
        if action in errors:
            with pytest.raises(errors[action]):
                asyncio.run(engine._learning_reserve_tick())
        else:
            asyncio.run(engine._learning_reserve_tick())
        stage = {
            "pressure": "discarded",
            "learner": "discarded",
            "route": "rejected",
            "invalid": "rejected",
        }.get(action, action)
        for lane in ("discovery", "policy"):
            assert collection.snapshot()["counts"][lane + "_300"] == {
                "rpc_requested": 1,
                "rpc_" + stage: 1,
            }
        assert len(observed) == (1 if action == "accepted" else 0)
        assert engine.features.tokens[state.mint] == original
        assert not learner.observations
        if action == "learner":
            assert not engine.learning.collection_diagnostics.snapshot()["counts"]
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


def test_outcomes_count_once_deadlines_stay_fixed_and_restart_has_new_scope(settings):
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings)
    _, _, now = scheduler_fixture()
    state = make_state("tracked")
    learner.register(make_decision(now, state.mint), state, live=True, evaluation_actionable=True)
    try:
        # Cache staleness is retriable until the existing deadline, not a fabricated outcome.
        learner.observe_market(state, now + timedelta(seconds=60), live=True, cached=True)
        assert not learner.collection_diagnostics.snapshot()["counts"]
        state.last_reserve_at = now + timedelta(seconds=70)
        learner.observe_market(state, now + timedelta(seconds=70), live=True, cached=True)
        learner.observe_market(state, now + timedelta(seconds=71), live=True, cached=True)
        learner.expire_checkpoints(now + timedelta(seconds=391), states={state.mint: state})
        learner.expire_checkpoints(now + timedelta(seconds=392), states={state.mint: state})
        counts = learner.collection_diagnostics.snapshot()["counts"]
        for lane in ("discovery", "policy"):
            assert counts[lane + "_60"] == {"usable": 1}
            assert counts[lane + "_300"] == {"expired": 1}
        saved = learner.observations[state.mint].model_dump(mode="json")
        restarted = LearningEngine(database, settings)
        assert restarted.collection_diagnostics.scope != learner.collection_diagnostics.scope
        assert not restarted.collection_diagnostics.snapshot()["counts"]
        assert restarted.observations[state.mint].model_dump(mode="json") == saved
    finally:
        database.close()


def test_counters_are_bounded_and_survive_real_diagnostics_storage(settings, tmp_path):
    engine = Orchestrator(settings)
    engine.diagnostics.enabled = True
    tracker = engine.learning.collection_diagnostics
    for lane in ("discovery", "policy"):
        for horizon in (60, 300, 600, 900, 1200):
            for stage in COLLECTION_STAGES:
                tracker.record(lane, horizon, stage)
    snapshot = tracker.snapshot()
    tracker.record("private-mint", 123, "private-error")
    assert tracker.snapshot() == snapshot
    snapshot["counts"].clear()
    assert len(tracker.snapshot()["counts"]) == 10
    try:
        engine._collect_diagnostics()
        record = json.loads(engine.diagnostics.queue[-1])
        store = DiagnosticsStore(tmp_path / "history")
        try:
            assert store.append(record)
            rows = [
                row["record"]
                for row in read_events(tmp_path / "history", before=2e9)
                if row["record"]["kind"] == "collection"
            ]
            assert len(rows) == 2
            assert {row["lane"] for row in rows} == {"discovery", "policy"}
            for row in rows:
                assert row["scope"] == tracker.scope
                assert all(value == 1 for values in row["counts"] for value in values)
            engine._collect_diagnostics()
            assert not json.loads(engine.diagnostics.queue[-1])["events"]
        finally:
            store.close()
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


def test_collection_events_wait_for_space_without_displacing_proof(settings):
    engine = Orchestrator(settings)
    engine.learning.collection_diagnostics.record("discovery", 300, "expired")
    try:
        engine.diagnostics.enabled = False
        engine._record_collection_diagnostics()
        assert not engine.diagnostics.events
        engine.diagnostics.enabled = True
        for index in range(8):
            engine.diagnostics.event({"kind": "proof", "id": str(index)})
        before = list(engine.diagnostics.events)
        engine._record_collection_diagnostics()
        assert list(engine.diagnostics.events) == before
        assert engine.diagnostics.dropped == 0
        engine.diagnostics._take_events(0)
        engine._record_collection_diagnostics()
        assert len(engine.diagnostics.events) == 2
        assert (
            engine.learning.collection_diagnostics.snapshot()["counts"]["discovery_300"]["expired"]
            == 1
        )
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


@pytest.mark.parametrize("existing", [False, True])
def test_rpc_cannot_reopen_expired_or_already_observed_checkpoints(settings, existing):
    engine = Orchestrator(settings)
    state, response, decoder, now = route_fixture()
    engine.features.tokens[state.mint] = state
    original = copy.deepcopy(state)
    entered = now - timedelta(seconds=301 if existing else 391)
    decision = make_decision(entered, state.mint).model_copy(
        update={"configuration_fingerprint": engine.learning.configuration_fingerprint()}
    )
    assert engine.learning.register(
        decision, make_state(state.mint), live=True, evaluation_actionable=True
    )
    targets = {state.mint: [("discovery", 300), ("policy", 300)]}
    try:
        if existing:
            stream = validated_learning_state(
                state, response, decoder, requested_at=now, observed_at=now
            )
            engine.learning.observe_market(stream, now, live=True, cached=True)
        else:
            engine.learning.expire_checkpoints(now, states=engine.features.tokens)
        observation = engine.learning.observations[state.mint]
        primary = observation.checkpoints["300"].model_dump_json()
        if existing:
            assert observation.checkpoints["300"].net_return is not None
        else:
            assert observation.checkpoints["300"].net_return is None
        for _ in range(2):
            engine._apply_learning_reserve_result(
                {state.mint: copy.copy(state)}, {state.mint: state}, response, now, targets
            )
        assert observation.checkpoints["300"].model_dump_json() == primary
        for lane in ("discovery", "policy"):
            counts = engine.learning.collection_diagnostics.snapshot()["counts"][lane + "_300"]
            assert counts["rpc_accepted"] == 2
            assert counts["usable" if existing else "expired"] == 1
            assert counts.get("expired" if existing else "usable", 0) == 0
        assert engine._learning_refresh_status["checkpoint_updates"] == 0
        assert engine.features.tokens[state.mint] == original
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


def test_cancellation_after_rpc_does_not_apply_evidence_or_release_another_lock(
    settings, monkeypatch
):
    engine = Orchestrator(settings)
    engine.demo_mode = False
    settings.learning_reserve_refresh_enabled = True
    monkeypatch.setattr(engine, "_rollover_market_data_healthy", lambda _: True)
    state, response, _decoder, _now = route_fixture()
    engine.features.tokens[state.mint] = state

    def select(*args, **kwargs):
        kwargs["selection"][state.mint] = [("discovery", 300)]
        return [state.mint]

    monkeypatch.setattr(engine.learning, "due_checkpoint_mints", select)
    monkeypatch.setattr(
        engine,
        "_apply_learning_reserve_result",
        lambda *a: pytest.fail("cancelled response applied"),
    )

    async def scenario():
        responded = asyncio.Event()

        async def fetch(*args, **kwargs):
            await engine._event_lock.acquire()
            responded.set()
            return response

        monkeypatch.setattr(engine.http, "solana_multiple_accounts", fetch)
        task = asyncio.create_task(engine._learning_reserve_tick())
        try:
            await asyncio.wait_for(responded.wait(), timeout=2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert engine._event_lock.locked()
            assert engine._learning_refresh_status["accepted_routes"] == 0
            assert not engine.learning.observations
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            if engine._event_lock.locked():
                engine._event_lock.release()

    try:
        asyncio.run(scenario())
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


def test_diagnostic_cadence_uses_monotonic_time_and_new_scope_does_not_wait(settings, monkeypatch):
    import signal_arcade.diagnostics as diagnostics

    engine = Orchestrator(settings)
    engine.diagnostics.enabled = True
    engine.learning.collection_diagnostics.record("policy", 300, "expired")
    clock = [1000.0]
    monkeypatch.setattr(diagnostics.time, "monotonic", lambda: clock[0])
    try:
        engine._record_collection_diagnostics()
        assert len(engine.diagnostics.events) == 2
        first_scope = engine.diagnostics.events[0]["scope"]
        engine.diagnostics._take_events(0)
        clock[0] += 299.999
        engine._record_collection_diagnostics()
        assert not engine.diagnostics.events
        clock[0] = 1300.0
        engine._record_collection_diagnostics()
        assert len(engine.diagnostics.events) == 2
        engine.diagnostics._take_events(0)
        engine.learning.collection_diagnostics = CollectionDiagnostics()
        engine.learning.collection_diagnostics.record("policy", 300, "expired")
        engine._record_collection_diagnostics()
        assert len(engine.diagnostics.events) == 2
        assert engine.diagnostics.events[0]["scope"] != first_scope
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()
