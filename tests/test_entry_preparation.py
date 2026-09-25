"""One joined preparation worker preserves decisions, evidence clocks and ownership."""

# ruff: noqa: F811 -- shared fixture

import asyncio
from datetime import timedelta
from threading import Event
from unittest.mock import AsyncMock

import pytest
import signal_arcade.orchestrator as orchestrator_module
from signal_arcade.models import DecisionAction, EventKind, MarketEvent, RiskMode
from signal_arcade.strategy import (
    SUPPORTED_BASELINE_VERSIONS,
    integrity_policy_for_baseline,
    strategy_fingerprint_payload,
)
from test_activity_evidence import NOW, snapshot_with, trade
from test_learning import make_decision
from test_probe_retention import engine  # noqa: F401


@pytest.fixture
def candidate(engine, monkeypatch):
    _, state, snapshot = snapshot_with([trade(20_000_000, wallet="buyer")])
    engine.features.tokens[state.mint] = state
    engine.running = True
    monkeypatch.setattr(engine.features, "apply", lambda _: state)
    monkeypatch.setattr(engine.features, "snapshot", lambda *_a, **_k: snapshot)
    monkeypatch.setattr(engine, "_event_regresses_verified_route", lambda _: False)
    monkeypatch.setattr(engine, "_accept_event_order", lambda *_: True)
    monkeypatch.setattr(engine, "_integrity_learning_window_complete", lambda *_: True)
    monkeypatch.setattr(engine, "_should_record_decision", lambda _: False)
    monkeypatch.setattr(engine.ai_lab, "enqueue_shadow", lambda *_: None)
    monkeypatch.setattr(engine.ai_lab, "assess_guarded", AsyncMock(side_effect=lambda d, _: d))
    registered = []
    monkeypatch.setattr(engine.learning, "register", lambda d, *_a, **_k: registered.append(d))
    monkeypatch.setattr(
        engine.learning,
        "assess",
        lambda d, **_k: d.model_copy(update={"action": DecisionAction.PASS}),
    )
    event = MarketEvent(
        event_id="prepare", source="fixture", kind=EventKind.TRADE, mint=state.mint, received_at=NOW
    )
    return engine, snapshot, event, registered


@pytest.mark.parametrize("diagnostics", [False, True])
def test_candidate_preparation_uses_one_executor_round_trip(candidate, monkeypatch, diagnostics):
    engine, snapshot, event, registered = candidate
    engine.diagnostics.enabled = diagnostics
    calls, order = [], []
    joined = orchestrator_module._joined_to_thread
    timed = orchestrator_module._timed_to_thread
    preparing = False

    def planned_order_size_sol(*_a, **_k):
        order.append("size")
        return 0.01

    def _evaluate_baseline_with_size(actual, size, price):
        order.append("evaluate")
        assert actual.model_dump(
            exclude={"values": {"integrity_window_complete"}}
        ) == snapshot.model_dump(exclude={"values": {"integrity_window_complete"}})
        assert size == 0.01
        return make_decision(NOW + timedelta(seconds=2), event.mint).model_copy(
            update={"feature_snapshot": actual}
        )

    def entry_blocker(decision, **_k):
        order.append("actionability")
        assert decision.season_id == engine.broker.season_id
        assert decision.configuration_fingerprint == engine._configuration_fingerprint()
        return None

    async def traced(function, *args, **kwargs):
        if preparing:
            calls.append(function.__name__)
        return await joined(function, *args, **kwargs)

    async def measured(recorder, phase, function, *args, **kwargs):
        nonlocal preparing
        if phase != "event_candidate":
            return await timed(recorder, phase, function, *args, **kwargs)
        assert function == engine._prepare_baseline_decision
        preparing = True
        try:
            return await timed(recorder, phase, function, *args, **kwargs)
        finally:
            preparing = False

    monkeypatch.setattr(engine.broker, "planned_order_size_sol", planned_order_size_sol)
    monkeypatch.setattr(engine, "_evaluate_baseline_with_size", _evaluate_baseline_with_size)
    monkeypatch.setattr(engine.broker, "entry_blocker", entry_blocker)
    monkeypatch.setattr(orchestrator_module, "_joined_to_thread", traced)
    monkeypatch.setattr(orchestrator_module, "_timed_to_thread", measured)
    assert asyncio.run(engine._handle_persisted_event(event))
    assert len(calls) == 1
    assert order == ["size", "evaluate", "actionability"]
    assert len(registered) == 1 and registered[0].action == DecisionAction.ENTER
    assert registered[0].feature_snapshot.model_dump(
        exclude={"values": {"integrity_window_complete"}}
    ) == snapshot.model_dump(exclude={"values": {"integrity_window_complete"}})
    assert registered[0].created_at == NOW + timedelta(seconds=2)
    assert registered[0].feature_snapshot.values["buy_ratio_5m"].as_of == NOW


@pytest.mark.parametrize("version", sorted(SUPPORTED_BASELINE_VERSIONS))
@pytest.mark.parametrize("mode", list(RiskMode))
@pytest.mark.parametrize("scenario", ["normal", "dust", "missing"])
def test_preparation_matches_previous_policy_and_broker_checks(
    engine, monkeypatch, version, mode, scenario
):
    engine.risk_mode = mode
    strategy = strategy_fingerprint_payload()
    strategy.update(
        baseline_version=version, integrity_policy_version=integrity_policy_for_baseline(version)
    )
    monkeypatch.setattr(engine, "_active_strategy_versions", lambda: strategy)
    snapshot = make_decision(NOW, "parity").feature_snapshot
    if scenario == "dust":
        snapshot.values["meaningful_volume_ratio"].value = 0.01
        snapshot.values["meaningful_wallet_ratio"].value = 0.01
    elif scenario == "missing":
        del snapshot.values["meaningful_volume_ratio"]
    original = snapshot.model_dump(mode="json")
    price = 100.0
    size = engine.broker.planned_order_size_sol(mode, sol_usd_price=price)
    expected = engine._evaluate_baseline_with_size(snapshot, size, price).model_copy(
        update={
            "season_id": engine.broker.season_id,
            "season_profile_fingerprint": engine.broker.season_profile.get("profile_fingerprint")
            if engine.broker.season_profile is not None
            else None,
            "configuration_fingerprint": engine._configuration_fingerprint(),
        }
    )
    actionable = (
        expected.action == DecisionAction.ENTER
        and engine.broker.entry_blocker(expected, sol_usd_price=price) is None
    )
    actual, actual_actionable = engine._prepare_baseline_decision(snapshot, price)
    assert actual.model_dump(exclude={"decision_id", "created_at"}) == expected.model_dump(
        exclude={"decision_id", "created_at"}
    )
    assert actual_actionable == actionable
    assert snapshot.model_dump(mode="json") == original


@pytest.mark.parametrize("action", [DecisionAction.PASS, DecisionAction.ABSTAIN])
def test_nonentry_preparation_does_not_query_entry_permission(engine, monkeypatch, action):
    decision = make_decision(NOW, "not-entry").model_copy(update={"action": action})
    monkeypatch.setattr(engine, "_evaluate_baseline_with_size", lambda *_: decision)
    monkeypatch.setattr(
        engine.broker,
        "entry_blocker",
        lambda *_a, **_k: pytest.fail("non-entry actionability check"),
    )
    actual, actionable = engine._prepare_baseline_decision(decision.feature_snapshot, None)
    assert actual.action == action and not actionable


@pytest.mark.parametrize("worker_error", [False, True])
def test_cancelled_preparation_keeps_market_boundary_until_worker_exits(
    candidate, monkeypatch, worker_error
):
    engine, snapshot, event, registered = candidate
    entered, release, exited = Event(), Event(), Event()

    def blocked(*_):
        entered.set()
        try:
            assert release.wait(5)
            if worker_error:
                raise RuntimeError("injected preparation error")
            return make_decision(NOW, snapshot.mint), True
        finally:
            exited.set()

    monkeypatch.setattr(engine, "_prepare_baseline_decision", blocked)

    async def exercise():
        task = asyncio.create_task(engine._handle_persisted_event(event))
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            assert engine._event_lock.locked() and not task.done()
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 3)
        assert exited.is_set() and not engine._event_lock.locked()
        assert not registered

    asyncio.run(exercise())


@pytest.mark.parametrize("phase", ["size", "evaluate", "permission"])
def test_preparation_failure_cannot_enroll_or_apply_partial_work(candidate, monkeypatch, phase):
    engine, snapshot, event, registered = candidate
    monkeypatch.setattr(engine.broker, "planned_order_size_sol", lambda *_a, **_k: 0.01)
    monkeypatch.setattr(
        engine,
        "_evaluate_baseline_with_size",
        lambda *_: make_decision(NOW, snapshot.mint),
    )
    monkeypatch.setattr(engine.broker, "entry_blocker", lambda *_a, **_k: None)

    def fail(*_a, **_k):
        raise RuntimeError("injected preparation failure")

    owner, name = {
        "size": (engine.broker, "planned_order_size_sol"),
        "evaluate": (engine, "_evaluate_baseline_with_size"),
        "permission": (engine.broker, "entry_blocker"),
    }[phase]
    monkeypatch.setattr(owner, name, fail)
    with pytest.raises(RuntimeError, match="injected preparation failure"):
        asyncio.run(engine._handle_persisted_event(event))
    assert not engine._event_lock.locked() and not registered
    engine.ai_lab.assess_guarded.assert_not_awaited()


def test_blocked_entry_retains_baseline_but_not_actionable_proof(candidate, monkeypatch):
    engine, snapshot, event, _ = candidate
    baseline = make_decision(NOW, snapshot.mint)
    monkeypatch.setattr(engine, "_evaluate_baseline_with_size", lambda *_: baseline)
    monkeypatch.setattr(engine.broker, "entry_blocker", lambda *_a, **_k: "exposure_limit")
    captured = []

    def register(decision, *_a, **kwargs):
        captured.append((decision, kwargs))

    def assess(decision, **kwargs):
        assert not kwargs["baseline_actionable"]
        return decision.model_copy(update={"action": DecisionAction.PASS})

    monkeypatch.setattr(engine.learning, "register", register)
    monkeypatch.setattr(engine.learning, "assess", assess)
    assert asyncio.run(engine._handle_persisted_event(event))
    assert len(captured) == 1
    assert captured[0][0].action == DecisionAction.ENTER
    assert captured[0][1]["evaluation_actionable"] is False
    engine.ai_lab.assess_guarded.assert_not_awaited()
