from __future__ import annotations

import asyncio
import copy
import json
import time
from datetime import timedelta
from types import SimpleNamespace

import pytest
from signal_arcade.diagnostics_store import DiagnosticsStore, read_page
from signal_arcade.intelligence.features import TokenState
from signal_arcade.intelligence.learning import LearningEngine
from signal_arcade.models import LearningObservationStatus
from signal_arcade.orchestrator import Orchestrator
from test_v1104_refresh import route_fixture, scheduler_fixture


@pytest.mark.parametrize("fresh", [False, True])
def test_last_chance_checkpoints_precede_new_work_without_taking_other_lanes_share(fresh):
    engine, states, now = scheduler_fixture()
    channel = "cache" if fresh else "rpc"
    if not fresh:
        for state in states.values():
            state.last_reserve_at = now - timedelta(minutes=5)
    for lane in ("policy", "discovery"):
        mint = f"{lane}-0"
        item = engine.evidence_episodes[mint] if lane == "policy" else engine.observations[mint]
        setattr(
            item, "entry_at" if lane == "policy" else "created_at", now - timedelta(seconds=145)
        )
        engine._checkpoint_served[channel][mint] = 0
    engine._checkpoint_turn[channel] = 20
    selected = LearningEngine.due_checkpoint_mints(engine, states, now, limit=4, fresh=fresh)
    assert selected[0] == "policy-0"
    assert selected[3] == "discovery-0"
    assert len(set(selected)) == 4
    assert sum(mint.startswith("policy") for mint in selected) == 3


def test_expired_checkpoint_gets_no_extra_time_or_rpc_priority():
    engine, states, now = scheduler_fixture()
    for state in states.values():
        state.last_reserve_at = now - timedelta(minutes=5)
    engine.observations["discovery-0"].created_at = now - timedelta(seconds=151)
    selected = LearningEngine.due_checkpoint_mints(engine, states, now, limit=48, fresh=False)
    assert "discovery-0" not in selected
    assert len(selected) == 47


def test_urgent_failures_still_rotate_within_their_lane():
    engine, states, now = scheduler_fixture()
    for state in states.values():
        state.last_reserve_at = now - timedelta(minutes=5)
    for episode in engine.evidence_episodes.values():
        episode.entry_at = now - timedelta(seconds=140)
    selected = [
        LearningEngine.due_checkpoint_mints(engine, states, now, limit=1, fresh=False)[0]
        for _ in range(16)
    ]
    assert len(set(selected)) == 16
    assert sum(mint.startswith("discovery") for mint in selected) == 4


@pytest.mark.parametrize("fresh", [False, True])
@pytest.mark.parametrize("discovery_age", [134.999999, 135, 150, 150.000001])
def test_shared_mint_uses_earliest_eligible_clock_without_taking_another_lane_share(
    fresh, discovery_age
):
    engine, states, now = scheduler_fixture()
    channel = "cache" if fresh else "rpc"
    if not fresh:
        for state in states.values():
            state.last_reserve_at = now - timedelta(minutes=5)
    shared = "policy-0"
    engine.observations[shared] = SimpleNamespace(
        mint=shared,
        created_at=now - timedelta(seconds=discovery_age),
        status=LearningObservationStatus.PENDING,
        checkpoints={},
    )
    engine._checkpoint_served[channel][shared] = 0
    engine._checkpoint_turn[channel] = 20
    original_clocks = (
        engine.observations[shared].created_at,
        engine.evidence_episodes[shared].entry_at,
    )

    selected = LearningEngine.due_checkpoint_mints(engine, states, now, limit=4, fresh=fresh)

    if 135 <= discovery_age <= 150:
        assert selected[0] == shared
        assert selected.count(shared) == 1
    else:
        assert shared not in selected, "Neither a nonurgent nor expired clock grants priority"
    assert len(selected) == len(set(selected)) == 4
    assert sum(mint.startswith("policy") for mint in selected) == 3
    assert selected[-1].startswith("discovery")
    assert original_clocks == (
        engine.observations[shared].created_at,
        engine.evidence_episodes[shared].entry_at,
    )
    assert not engine.observations[shared].checkpoints


def test_diagnostics_retries_after_lock_deferral_without_false_loss(settings, monkeypatch):
    import signal_arcade.orchestrator as orchestration

    engine = Orchestrator(settings)
    engine.diagnostics.enabled = True
    clock = [time.monotonic()]
    monkeypatch.setattr(
        orchestration,
        "time",
        SimpleNamespace(monotonic=lambda: clock[0], process_time=time.process_time),
    )

    async def scenario():
        await engine._event_lock.acquire()
        engine._record_pipeline_recent("processed", lag_seconds=0.5, critical=True)
        waits = 0

        async def next_cycle(delay):
            nonlocal waits
            assert delay == 5
            waits += 1
            if waits == 1:
                clock[0] += 61
            elif waits == 2:
                assert engine.diagnostics.sequence == 0
                assert engine.diagnostics.cursor.serial == 0
                assert engine.diagnostics.dropped == 0
                assert engine.diagnostics.collection_deferred == 1
                engine._event_lock.release()
                engine._record_pipeline_recent("processed", lag_seconds=0.1)
                clock[0] += 5
            else:
                engine.stop_event.set()

        monkeypatch.setattr(engine, "_wait_for_stop", next_cycle)
        await engine._diagnostics_loop()
        assert engine.diagnostics.sequence == 1
        record = json.loads(engine.diagnostics.queue[-1])
        assert record["pipeline"]["processed"] == 2
        assert record["pipeline"]["critical_count"] == 1
        assert record["gauges"]["diagnostics_deferred"] == 1
        assert "recording_gap" not in record["flags"]

    try:
        asyncio.run(scenario())
    finally:
        engine.database.close()


@pytest.mark.parametrize(
    "reason",
    [
        "disabled",
        "demo",
        "maintenance",
        "market_boundary",
        "pending_sell",
        "queue_pressure",
        "processing_lag",
        "market_unhealthy",
    ],
)
def test_refresh_deferrals_preserve_all_existing_safety_guards(settings, monkeypatch, reason):
    engine = Orchestrator(settings)
    engine.demo_mode = False
    settings.learning_reserve_refresh_enabled = True
    monkeypatch.setattr(engine, "_rollover_market_data_healthy", lambda _: True)
    if reason == "disabled":
        settings.learning_reserve_refresh_enabled = False
    elif reason == "demo":
        engine.demo_mode = True
    elif reason == "maintenance":
        engine._maintenance_requested = True
    elif reason == "market_boundary":
        engine.event_queue.begin_boundary(0)
    elif reason == "pending_sell":
        monkeypatch.setattr(engine, "_has_pending_sell", lambda: True)
    elif reason == "queue_pressure":
        monkeypatch.setattr(engine.event_queue, "qsize", lambda: settings.event_queue_max * 0.05)
    elif reason == "processing_lag":
        engine.last_processing_lag_seconds = 1
    else:
        monkeypatch.setattr(engine, "_rollover_market_data_healthy", lambda _: False)
    monkeypatch.setattr(
        engine.learning, "due_checkpoint_mints", lambda *a, **kw: pytest.fail("no acquisition")
    )
    try:
        assert engine._learning_reserve_blocked_reason() == reason
        assert not engine._learning_reserve_can_run()
        asyncio.run(engine._learning_reserve_tick())
        assert engine._learning_refresh_status["deferred"][reason] == 1
        assert engine._learning_refresh_status["blocked_reason"] == reason
        assert engine._learning_refresh_status["requests"] == 0
        assert engine._learning_refresh_status["state"] != "fetching"
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


@pytest.mark.parametrize("change", ["pressure", "learner", "none"])
def test_refresh_result_guard_and_durable_diagnostics(settings, monkeypatch, tmp_path, change):
    engine = Orchestrator(settings)
    engine.diagnostics.enabled = True
    engine.demo_mode = False
    settings.learning_reserve_refresh_enabled = True
    monkeypatch.setattr(engine, "_rollover_market_data_healthy", lambda _: True)
    state, response, _decoder, _now = route_fixture()
    engine.features.tokens[state.mint] = state
    original = copy.deepcopy(state)
    learner = engine.learning
    monkeypatch.setattr(learner, "due_checkpoint_mints", lambda *a, **kw: [state.mint])
    accepted = []
    monkeypatch.setattr(
        learner, "observe_market", lambda state, *a, **kw: accepted.append(state) or 1
    )
    engine._learning_refresh_status["last_error"] = "TimeoutError"

    async def fetch(addresses, **kwargs):
        assert len(addresses) <= 100
        assert not engine._event_lock.locked(), "RPC must stay outside the market boundary"
        assert kwargs["critical"] is False
        if change == "pressure":
            engine.last_processing_lag_seconds = 1
        elif change == "learner":
            engine.learning = copy.copy(learner)
        return response

    monkeypatch.setattr(engine.http, "solana_multiple_accounts", fetch)
    try:
        asyncio.run(engine._learning_reserve_tick())
        status = engine._learning_refresh_status
        assert status["requests"] == status["selected_routes"] == 1
        assert status["last_request_seconds"] >= 0
        if change == "none":
            assert len(accepted) == 1
            assert status["state"] == "idle"
            assert status["last_error"] is None
            assert status["blocked_reason"] is None
        else:
            assert not accepted
            reason = "processing_lag" if change == "pressure" else "context_changed"
            assert status["blocked_reason"] == reason
            assert status["state"] == "yielding"
            assert status["deferred"][reason] == 1
        assert engine.features.tokens[state.mint] == original
        engine._collect_diagnostics()
        record = json.loads(engine.diagnostics.queue[-1])
        store = DiagnosticsStore(tmp_path / "readback")
        try:
            assert store.append(record)
            stored = read_page(tmp_path / "readback", tier=0)[0]["record"]
            detail = stored["gauges"]["learning_refresh"]
            assert detail["requests"] == 1
            assert detail["accepted"] == (1 if change == "none" else 0)
            assert detail["discarded_batches"] == (0 if change == "none" else 1)
            assert detail["blocked"] == status["blocked_reason"]
        finally:
            store.close()
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


def test_collection_error_is_not_misreported_as_lock_deferral(settings, monkeypatch):
    import signal_arcade.orchestrator as orchestration

    engine = Orchestrator(settings)
    engine.diagnostics.enabled = True
    clock = [time.monotonic()]
    monkeypatch.setattr(
        orchestration,
        "time",
        SimpleNamespace(monotonic=lambda: clock[0], process_time=time.process_time),
    )

    def fail_collection():
        raise TimeoutError("injected collector failure after acquiring boundary")

    monkeypatch.setattr(engine, "_collect_diagnostics", fail_collection)

    async def next_cycle(_delay):
        clock[0] += 61
        if engine.diagnostics.dropped:
            engine.stop_event.set()

    monkeypatch.setattr(engine, "_wait_for_stop", next_cycle)
    try:
        asyncio.run(engine._diagnostics_loop())
        assert engine.diagnostics.dropped == 1
        assert engine.diagnostics.collection_deferred == 0
        assert not engine._event_lock.locked()
    finally:
        engine.database.close()


def test_cancelled_diagnostic_collection_cannot_claim_the_market_lock(settings, monkeypatch):
    import signal_arcade.orchestrator as orchestration

    engine = Orchestrator(settings)
    engine.diagnostics.enabled = True
    clock = [time.monotonic()]
    monkeypatch.setattr(
        orchestration,
        "time",
        SimpleNamespace(monotonic=lambda: clock[0], process_time=time.process_time),
    )

    async def scenario():
        waiting = asyncio.Event()
        await engine._event_lock.acquire()

        async def next_cycle(_delay):
            clock[0] += 61
            waiting.set()

        monkeypatch.setattr(engine, "_wait_for_stop", next_cycle)
        task = asyncio.create_task(engine._diagnostics_loop())
        await waiting.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert engine._event_lock.locked()
        engine._event_lock.release()
        await asyncio.wait_for(engine._event_lock.acquire(), timeout=0.1)
        engine._event_lock.release()
        assert not engine.diagnostics.queue
        assert engine.diagnostics.dropped == 0

    try:
        asyncio.run(scenario())
    finally:
        engine.database.close()


def test_invalid_rpc_identity_frees_next_slot_and_repaired_identity_retries(settings, monkeypatch):
    engine = Orchestrator(settings)
    engine.demo_mode = False
    settings.learning_reserve_refresh_enabled = True
    settings.learning_reserve_refresh_batch_size = 1
    monkeypatch.setattr(engine, "_rollover_market_data_healthy", lambda _: True)
    broken, first_response, _decoder, now = route_fixture(seed=60)
    valid, second_response, _decoder, _now = route_fixture(seed=61)
    original_curve = broken.curve_address
    broken.curve_address = ""
    for state, age in ((broken, 145), (valid, 80)):
        state.last_reserve_at = now - timedelta(minutes=5)
        engine.features.tokens[state.mint] = state
        engine.learning.observations[state.mint] = SimpleNamespace(
            mint=state.mint,
            created_at=now - timedelta(seconds=age),
            status=LearningObservationStatus.PENDING,
            checkpoints={},
        )
    accepted = []
    monkeypatch.setattr(
        engine.learning, "observe_market", lambda state, *a, **kw: accepted.append(state.mint) or 1
    )

    async def fetch(_addresses, **_kwargs):
        return {
            "slot": 101,
            "accounts": {**first_response["accounts"], **second_response["accounts"]},
        }

    monkeypatch.setattr(engine.http, "solana_multiple_accounts", fetch)
    try:
        asyncio.run(engine._learning_reserve_tick())
        assert broken.mint in engine._learning_invalid_routes
        assert engine._learning_refresh_status["requests"] == 0
        asyncio.run(engine._learning_reserve_tick())
        assert accepted == [valid.mint]
        assert not engine.learning.observations[broken.mint].checkpoints
        broken.curve_address = original_curve
        asyncio.run(engine._learning_reserve_tick())
        assert accepted == [valid.mint, broken.mint]
        assert broken.mint not in engine._learning_invalid_routes
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


def test_rpc_exclusion_cannot_suppress_a_fresh_cached_checkpoint():
    engine, states, now = scheduler_fixture()
    excluded = set(states)
    assert LearningEngine.due_checkpoint_mints(
        engine, states, now, limit=4, fresh=True, excluded_mints=excluded
    )
    for state in states.values():
        state.last_reserve_at = now - timedelta(minutes=5)
    assert not LearningEngine.due_checkpoint_mints(
        engine, states, now, limit=4, fresh=False, excluded_mints=excluded
    )
    assert len(engine.observations) == len(engine.evidence_episodes) == 24


def test_invalid_identity_cache_is_bounded_and_prunes_removed_tokens(settings, monkeypatch):
    engine = Orchestrator(settings)
    engine.demo_mode = False
    settings.learning_reserve_refresh_enabled = True
    monkeypatch.setattr(engine, "_rollover_market_data_healthy", lambda _: True)
    mints = [f"invalid-mint-{index}" for index in range(150)]
    engine.features.tokens.update({mint: TokenState(mint=mint) for mint in mints})
    batches = iter([mints[offset : offset + 20] for offset in range(0, 150, 20)])
    monkeypatch.setattr(engine.learning, "due_checkpoint_mints", lambda *a, **kw: next(batches, []))
    try:
        for _ in range(8):
            asyncio.run(engine._learning_reserve_tick())
        assert len(engine._learning_invalid_routes) == 128
        assert mints[0] not in engine._learning_invalid_routes
        assert engine._learning_refresh_status["requests"] == 0
        del engine.features.tokens[mints[-1]]
        asyncio.run(engine._learning_reserve_tick())
        assert len(engine._learning_invalid_routes) == 127
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


@pytest.mark.parametrize("failure", ["provider_unavailable", "missing_account"])
def test_transient_refresh_failure_does_not_cache_a_valid_identity(settings, monkeypatch, failure):
    engine = Orchestrator(settings)
    engine.demo_mode = False
    settings.learning_reserve_refresh_enabled = True
    monkeypatch.setattr(engine, "_rollover_market_data_healthy", lambda _: True)
    state, response, _decoder, now = route_fixture()
    state.last_reserve_at = now - timedelta(minutes=5)
    original = copy.deepcopy(state)
    engine.features.tokens[state.mint] = state
    engine.learning.observations[state.mint] = SimpleNamespace(
        mint=state.mint,
        created_at=now - timedelta(seconds=65),
        status=LearningObservationStatus.PENDING,
        checkpoints={},
    )
    accepted = []
    monkeypatch.setattr(
        engine.learning, "observe_market", lambda state, *a, **kw: accepted.append(state.mint) or 1
    )
    failed = None if failure == "provider_unavailable" else {**response, "accounts": {}}
    responses = iter([failed, response])

    async def fetch(_addresses, **_kwargs):
        return next(responses)

    monkeypatch.setattr(engine.http, "solana_multiple_accounts", fetch)
    try:
        asyncio.run(engine._learning_reserve_tick())
        assert not accepted
        assert not engine._learning_invalid_routes
        assert sum(engine._learning_refresh_status["rejected"].values()) == 1
        assert not engine.learning.observations[state.mint].checkpoints
        asyncio.run(engine._learning_reserve_tick())
        assert accepted == [state.mint]
        assert engine._learning_refresh_status["requests"] == 2
        assert engine._learning_refresh_status["state"] == "idle"
        assert not engine._learning_invalid_routes
        assert engine.features.tokens[state.mint] == original
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()
