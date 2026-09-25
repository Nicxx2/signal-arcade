"""Collection telemetry and guard retries must preserve the evidence contract."""

import asyncio
import copy
from datetime import datetime, timedelta

import pytest
from signal_arcade.diagnostics import DiagnosticsRecorder
from signal_arcade.diagnostics_store import MAX_EVENT_PAYLOAD, DiagnosticsStore, encode, read_events
from signal_arcade.intelligence.collection_diagnostics import (
    EXPIRY_RPC_STAGES,
    CollectionDiagnostics,
    CollectionTargets,
)
from signal_arcade.intelligence.learning import LearningEngine
from signal_arcade.orchestrator import _HEARTBEAT_WORK, Orchestrator, _measure_heartbeat_work
from test_learning import make_decision, make_state, policy_episode_for
from test_market_checkpoint_dispatch import enrolled
from test_reserve_contract_integration import public_config_route


def expiry_count(tracker, lane, horizon, stage):
    event = next(e for e in tracker.expiry_events() if e["lane"] == lane)
    return event["last_rpc"][event["horizons"].index(horizon)][event["stages"].index(stage)]


def test_expiry_tracks_separate_trajectories_and_restored_unknowns(settings):
    learner, database, state, start = enrolled(settings)
    observation = learner.observations[state.mint]
    policy = policy_episode_for(learner, state.mint)
    later = policy.model_copy(
        deep=True,
        update={
            "episode_id": "later-policy",
            "entry_at": start + timedelta(seconds=13),
            "idempotency_key": "later-policy",
            "trajectory_key": "later-policy",
        },
    )
    learner.evidence_episodes[later.episode_id] = later
    learner._evidence_episode_ids_by_mint[state.mint].append(later.episode_id)
    states = {state.mint: state}
    state.last_reserve_at = start - timedelta(minutes=5)
    tracker = learner.collection_diagnostics
    targets = CollectionTargets()
    try:
        assert learner.due_checkpoint_mints(
            states,
            start + timedelta(seconds=301),
            limit=5,
            fresh=False,
            diagnostics=tracker,
            selection=targets,
        ) == [state.mint]
        assert ("discovery", 300, observation.observation_id) in targets.identities[state.mint]
        assert ("policy", 300, later.episode_id) not in targets.identities[state.mint]
        tracker.record_targets(targets, "rpc_discarded")
        learner.expire_checkpoints(start + timedelta(seconds=405), states=states)
        assert expiry_count(tracker, "discovery", 300, "rpc_discarded") == 1
        assert expiry_count(tracker, "policy", 300, "rpc_discarded") == 1
        assert expiry_count(tracker, "policy", 300, "unknown") == 1
        # An in-flight response cannot re-open closed telemetry or evidence.
        before = copy.deepcopy(tracker._pending)
        saved = observation.model_dump_json()
        tracker.record_targets(targets, "rpc_accepted")
        learner.expire_checkpoints(start + timedelta(seconds=406), states=states)
        assert tracker._pending == before
        assert observation.model_dump_json() == saved
        restored = LearningEngine(database, settings)
        restored.expire_checkpoints(start + timedelta(seconds=700), states=states)
        assert expiry_count(restored.collection_diagnostics, "discovery", 600, "unknown") == 1
    finally:
        database.close()


def test_unselected_enrollment_and_evicted_tracking_are_honest(monkeypatch):
    import signal_arcade.intelligence.collection_diagnostics as module

    monkeypatch.setattr(module, "MAX_TRACKED_CHECKPOINTS", 5)
    tracker = CollectionDiagnostics()
    tracker.enrolled("discovery", "old")
    tracker.enrolled("policy", "new")
    assert len(tracker._pending) == 5
    tracker.record("discovery", 300, "expired", trajectory_id="old")
    tracker.record("policy", 300, "expired", trajectory_id="new")
    assert expiry_count(tracker, "discovery", 300, "unknown") == 1
    assert expiry_count(tracker, "policy", 300, "no_rpc_selection") == 1


@pytest.mark.parametrize("venue", ["pump_curve", "pump_swap"])
@pytest.mark.parametrize("late_microseconds", [0, 1])
def test_inflight_refresh_respects_exact_deadline_and_persists_both_lanes(
    settings, monkeypatch, venue, late_microseconds
):
    import signal_arcade.orchestrator as orchestration

    engine = Orchestrator(settings)
    engine.demo_mode = False
    settings.learning_reserve_refresh_enabled = True
    state, response, _decoder, requested_at = public_config_route(venue)
    entered_at = requested_at - timedelta(seconds=385)
    received_at = entered_at + timedelta(seconds=390, microseconds=late_microseconds)
    clock = [requested_at]

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0]

    monkeypatch.setattr(orchestration, "datetime", FixedDateTime)
    monkeypatch.setattr(engine, "_rollover_market_data_healthy", lambda _: True)
    engine.features.tokens[state.mint] = state
    original = copy.deepcopy(state)
    decision = make_decision(entered_at, state.mint)
    decision.configuration_fingerprint = engine.learning.configuration_fingerprint()

    async def fetch(addresses, **kwargs):
        assert not engine._event_lock.locked()
        assert kwargs["critical"] is False
        assert len(addresses) <= 100
        assert "300" not in engine.learning.observations[state.mint].checkpoints
        clock[0] = received_at
        return response

    monkeypatch.setattr(engine.http, "solana_multiple_accounts", fetch)
    try:
        assert engine.learning.register(
            decision, make_state(state.mint), live=True, evaluation_actionable=True
        )
        # Use the actual selector, RPC worker, validator and evidence persistence path.
        assert asyncio.run(engine._learning_reserve_tick()) is None
        assert engine._learning_refresh_status["requests"] == 1
        assert engine._learning_refresh_status["accepted_routes"] == 1
        saved = {}
        for lane, item in (
            ("discovery", engine.learning.observations[state.mint]),
            ("policy", policy_episode_for(engine.learning, state.mint)),
        ):
            checkpoint = item.checkpoints["300"]
            assert checkpoint.observed_at == received_at
            assert (checkpoint.net_return is None) == bool(late_microseconds)
            if late_microseconds:
                assert checkpoint.missing_reason == "checkpoint_window_elapsed"
                assert (
                    expiry_count(engine.learning.collection_diagnostics, lane, 300, "rpc_accepted")
                    == 1
                )
            else:
                assert checkpoint.missing_reason is None
                assert checkpoint.route_snapshot["requested_at"] == requested_at.isoformat()
            saved[lane] = checkpoint.model_dump_json()
        # A fresh later response and a restart cannot reopen the five-minute outcome.
        clock[0] = received_at + timedelta(seconds=1)
        engine._apply_learning_reserve_result(
            {state.mint: copy.copy(state)}, {state.mint: state}, response, clock[0]
        )
        restored = LearningEngine(engine.database, settings)
        assert (
            restored.observations[state.mint].checkpoints["300"].model_dump_json()
            == saved["discovery"]
        )
        assert (
            policy_episode_for(restored, state.mint).checkpoints["300"].model_dump_json()
            == saved["policy"]
        )
        assert engine.features.tokens[state.mint] == original
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


def test_large_expiry_counts_split_without_loss_and_each_part_can_resume(settings):
    import random

    engine = Orchestrator(settings)
    engine.diagnostics.enabled = True
    tracker = engine.learning.collection_diagnostics
    rng = random.Random(40)  # noqa: S311 - deterministic counter-size fixture
    tracker._expiry = {
        f"{lane}_{horizon}": {stage: rng.randrange(2**63 - 1) for stage in EXPIRY_RPC_STAGES}
        for lane in ("policy", "discovery")
        for horizon in (60, 300, 600, 900, 1200)
    }
    events = tracker.expiry_events()
    assert len(events) > 2
    restored = {}
    for event in events:
        assert len(encode(event, max_payload=MAX_EVENT_PAYLOAD)) <= MAX_EVENT_PAYLOAD
        for horizon, counts in zip(event["horizons"], event["last_rpc"], strict=True):
            restored[f"{event['lane']}_{horizon}"] = dict(zip(event["stages"], counts, strict=True))
    assert restored == tracker._expiry
    delivered = []
    try:
        for _ in range(len(events)):
            engine.diagnostics._take_events(0)
            for _ in range(7):
                engine.diagnostics.event({"kind": "proof"})
            engine._record_collection_detail_diagnostics()
            delivered.extend(e for e in engine.diagnostics.events if e["kind"] != "proof")
        assert len(delivered) == len(events)
        assert len({(e["lane"], tuple(e["horizons"])) for e in delivered}) == len(events)
        assert engine.diagnostics.dropped == 0
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


def test_detail_exports_fit_storage_and_yield_to_proof(settings, tmp_path):
    engine = Orchestrator(settings)
    recorder = engine.diagnostics
    recorder.enabled = True
    tracker = engine.learning.collection_diagnostics
    for lane in ("discovery", "policy"):
        for horizon in (60, 300, 600, 900, 1200):
            for stage in EXPIRY_RPC_STAGES:
                tracker.track(lane, horizon, stage)
                tracker._pending[lane, horizon, stage][0] = stage
                tracker.record(lane, horizon, "expired", trajectory_id=stage)
    recorder.observe_heartbeat_work(
        {
            name: 0.125
            for name in ("positions", "cache", "expiry", "coach", "ai", "profile", "season")
        }
    )
    try:
        for _ in range(8):
            recorder.event({"kind": "proof"})
        engine._record_collection_detail_diagnostics()
        assert all(event["kind"] == "proof" for event in recorder.events)
        assert recorder.dropped == 0
        recorder._take_events(0)
        engine._collect_diagnostics()
        store = DiagnosticsStore(tmp_path / "readback")
        try:
            import json

            assert store.append(json.loads(recorder.queue[-1]))
            events = [row["record"] for row in read_events(tmp_path / "readback", before=2e9)]
            assert len([e for e in events if e["kind"] == "collection_expiry"]) == 2
            assert len([e for e in events if e["kind"] == "heartbeat_work"]) == 1
            recorder._take_events(0)
            engine._record_collection_detail_diagnostics()
            assert not recorder.events
        finally:
            store.close()
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


@pytest.mark.parametrize("failure", [False, True])
def test_heartbeat_timing_joins_worker_and_preserves_failure(settings, monkeypatch, failure):
    engine = Orchestrator(settings)
    engine.diagnostics.enabled = True
    calls = []

    def tick(now):
        with _measure_heartbeat_work("positions"):
            calls.append("positions")
        with _measure_heartbeat_work("cache"):
            assert not engine.diagnostics.heartbeat_work_since_boot
            if failure:
                raise ValueError("isolated failure")
        return [], [], 0, 0

    async def stop(_delay):
        engine.stop_event.set()

    monkeypatch.setattr(engine, "_heartbeat_tick", tick)
    monkeypatch.setattr(engine, "_wait_for_stop", stop)
    try:
        asyncio.run(engine._heartbeat_loop())
        timing = engine.diagnostics.heartbeat_work_since_boot
        assert calls == ["positions"]
        assert timing["positions"][0] == timing["cache"][0] == 1
        assert ("profile" in timing) is not failure
        assert _HEARTBEAT_WORK.get() is None
        assert not engine._event_lock.locked()
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


def test_disabled_and_invalid_timing_is_ignored(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path, enabled=False)
    recorder.observe_heartbeat_work({"cache": 2})
    assert not recorder.heartbeat_work_since_boot
    recorder.enabled = True
    recorder.observe_heartbeat_work({"private-key": 2, "cache": float("nan"), "ai": -1})
    assert not recorder.heartbeat_work_since_boot


def test_cancelled_heartbeat_keeps_timing_owned_until_worker_finishes(settings, monkeypatch):
    from threading import Event

    engine = Orchestrator(settings)
    engine.diagnostics.enabled = True
    entered, release = Event(), Event()

    def tick(now):
        with _measure_heartbeat_work("positions"):
            entered.set()
            assert release.wait(5)
        return [], [], 0, 0

    monkeypatch.setattr(engine, "_heartbeat_tick", tick)

    async def scenario():
        task = asyncio.create_task(engine._heartbeat_loop())
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            for _ in range(2):
                task.cancel()
                await asyncio.sleep(0)
            assert not task.done() and engine._event_lock.locked()
            assert not engine.diagnostics.heartbeat_work_since_boot
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
        assert engine.diagnostics.heartbeat_work_since_boot["positions"][0] == 1
        assert not engine._event_lock.locked()
        assert _HEARTBEAT_WORK.get() is None

    try:
        asyncio.run(scenario())
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()
