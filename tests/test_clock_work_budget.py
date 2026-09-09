"""Clock updates preserve durable exit evidence without revaluing the same state."""

import asyncio
from datetime import timedelta

import pytest
from signal_arcade.intelligence.reserve_refresh import validated_learning_state
from signal_arcade.models import RiskMode
from signal_arcade.orchestrator import Orchestrator
from test_broker import make_decision, make_features
from test_broker_work_budget import held  # noqa: F401
from test_v1104_refresh import route_fixture


def test_real_heartbeat_marks_held_position_once(held, monkeypatch):  # noqa: F811
    broker, database, state, now = held
    engine = Orchestrator(broker.settings)
    engine.broker = broker
    engine.risk_mode = RiskMode.BALANCED
    engine.running = True
    state.last_event_at = state.last_reserve_at = now
    engine.features.tokens[state.mint] = state
    calls = []
    original = broker._mark_position

    def mark(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(broker, "_mark_position", mark)
    try:
        engine._heartbeat_tick(now)
        assert len(calls) == 1
        restored = database.list_positions()[0]
        assert restored == broker.positions[state.mint]
        assert restored.exit_assessment is not None
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


@pytest.mark.parametrize("venue", ["pump_curve", "pump_swap"])
def test_real_watchdog_marks_once_and_preserves_verified_route(held, monkeypatch, venue):  # noqa: F811
    broker, database, _, _ = held
    state, result, decoder, now = route_fixture(venue)
    verified = validated_learning_state(state, result, decoder, requested_at=now, observed_at=now)
    engine = Orchestrator(broker.settings)
    engine.broker = broker
    engine.risk_mode = RiskMode.BALANCED
    engine.running = True
    engine.features.tokens[state.mint] = state
    assert broker.submit_decision(make_decision(now, state.mint))
    assert broker.process_due_orders(
        state=verified,
        features=make_features(now, state.mint),
        source_event_id="entry",
        now=now,
        mode=RiskMode.BALANCED,
    )
    calls = []
    original = broker._mark_position

    def mark(*args, **kwargs):
        calls.append(args[0].mint)
        return original(*args, **kwargs)

    monkeypatch.setattr(broker, "_mark_position", mark)
    targets = [t for t in engine._position_watchdog_targets()[0] if t["mint"] == state.mint]
    try:
        _, refreshed, slot = engine._apply_position_watchdog_result(
            targets,
            result,
            now + timedelta(seconds=1),
        )
        assert refreshed == {state.mint}
        assert slot == 101
        assert calls == [state.mint]
        saved = next(p for p in database.list_positions() if p.mint == state.mint)
        assert saved == broker.positions[state.mint]
        assert saved.exit_assessment is not None
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()
