"""Descriptive entry evidence must not add work to priority market updates."""

# ruff: noqa: F811 -- shared engine fixture

import asyncio

import pytest
from signal_arcade.intelligence import features as feature_module
from signal_arcade.intelligence.activity import ACTIVITY_UNITS
from signal_arcade.models import EventKind, MarketEvent
from test_activity_evidence import NOW, snapshot_with, trade
from test_probe_retention import engine, position  # noqa: F401


@pytest.mark.parametrize("path", ["held", "paused_held", "pending", "candidate"])
def test_market_dispatch_keeps_entry_evidence_without_scanning_held_or_pending_activity(
    engine, monkeypatch, path
):
    _, state, expected = snapshot_with([trade(20_000_000, wallet="buyer")])
    state.rolling_trade_metrics = None
    engine.features.tokens[state.mint] = state
    engine.running = path != "paused_held"
    if path in {"held", "paused_held"}:
        engine.broker.positions[state.mint] = position(state.mint)
    monkeypatch.setattr(engine.broker, "has_pending_for", lambda *_: path == "pending")
    monkeypatch.setattr(engine.features, "apply", lambda _: state)
    monkeypatch.setattr(engine, "_event_regresses_verified_route", lambda _: False)
    monkeypatch.setattr(engine, "_accept_event_order", lambda *_: True)
    activity_calls, market_calls = [], []
    original = feature_module.activity_metrics

    def activity(trades, at):
        activity_calls.append(at)
        return original(trades, at)

    def market(**kwargs):
        market_calls.append(kwargs)
        return []

    monkeypatch.setattr(feature_module, "activity_metrics", activity)
    monkeypatch.setattr(engine.broker, "on_market_state", market)
    monkeypatch.setattr(engine.broker, "observe_market_state", market)
    event = MarketEvent(
        event_id="activity-dispatch",
        source="test",
        kind=EventKind.TRADE,
        mint=state.mint,
        received_at=NOW,
    )
    assert asyncio.run(engine._handle_persisted_event(event))
    saved = engine.database.list_decisions(10)
    if path == "candidate":
        assert not market_calls
        assert activity_calls == [NOW]
        assert len(saved) == 1
        actual = saved[0].feature_snapshot
        assert ACTIVITY_UNITS.keys() <= actual.values.keys()
        assert actual.values["meaningful_trade_count_5m"].value == 1
    else:
        assert activity_calls == [] and not saved
        assert len(market_calls) == 1
        actual = market_calls[0]["features"]
        assert not (ACTIVITY_UNITS.keys() & actual.values.keys())
        assert market_calls[0]["now"] == NOW
        assert market_calls[0]["state"] is state
    # Core trading/exit evidence must be identical with or without the descriptive fields.
    assert {
        key: value
        for key, value in actual.values.items()
        if key not in ACTIVITY_UNITS and key != "integrity_window_complete"
    } == {key: value for key, value in expected.values.items() if key not in ACTIVITY_UNITS}
    assert actual.hard_flags == expected.hard_flags
    assert actual.data_confidence == expected.data_confidence
