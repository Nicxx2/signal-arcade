"""Structural calculations share the existing window, while live safety stays fresh."""

from collections import deque
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.intelligence import features
from signal_arcade.models import Side


def populated_engine():
    now = datetime.now(UTC)
    engine = features.FeatureEngine()
    state = features.TokenState(mint="window", creator="creator")
    state.trades = deque(
        (
            features.TradeObservation(
                received_at=now - timedelta(seconds=age),
                slot=index + 1,
                side=Side.SELL,
                user="seller",
                token_units=1_000,
                quote_lamports=1_000_000,
                price_sol=price,
                venue=venue,
            )
            for index, (age, price, venue) in enumerate(
                [
                    (301, 10, "pump_curve"),
                    (300, 2, "pump_curve"),
                    (60, 4, "pump_curve"),
                    (0, 3, "pump_curve"),
                    (-1, 100, "pump_curve"),
                    (0, 200, "pump_swap"),
                ]
            )
        ),
        maxlen=5_000,
    )
    engine.tokens[state.mint] = state
    return engine, state, now


def test_cache_hit_does_not_repeat_price_window_scans(monkeypatch):
    engine, state, now = populated_engine()
    calls = []
    original = features._momentum

    def momentum(trades):
        calls.append(len(trades))
        return original(trades)

    monkeypatch.setattr(features, "_momentum", momentum)
    first = engine.snapshot(state.mint, now)
    second = engine.snapshot(state.mint, now + timedelta(milliseconds=100))
    assert first is not None and second is not None
    assert len(calls) == 2, "identical cached trade windows were scanned again"
    assert first.values["momentum_1m"].value == second.values["momentum_1m"].value == -0.25
    assert first.values["momentum_5m"].value == second.values["momentum_5m"].value == 0.5


@pytest.mark.parametrize("change", ["expired", "backwards", "venue", "creator"])
def test_window_refresh_and_live_creator_flags_keep_their_boundaries(change):
    engine, state, now = populated_engine()
    first = engine.snapshot(state.mint, now)
    cached = state.rolling_trade_metrics
    if change == "expired":
        now += timedelta(seconds=1)
    elif change == "backwards":
        now -= timedelta(seconds=1)
    elif change == "venue":
        state.venue = "pump_swap"
    else:
        state.creator = "seller"
        now += timedelta(milliseconds=100)
    snapshot = engine.snapshot(state.mint, now)
    assert snapshot is not None and first is not None
    rolling = state.rolling_trade_metrics
    assert (rolling is cached) == (change == "creator")
    assert snapshot.values["momentum_1m"].value == features._momentum(rolling.trades_1m)
    assert snapshot.values["momentum_5m"].value == features._momentum(rolling.trades_5m)
    assert snapshot.values["drawdown_5m"].value == features._drawdown(rolling.trades_5m)
    if change == "creator":
        assert "creator_sold_recently" not in first.hard_flags
        assert "creator_sold_recently" in snapshot.hard_flags
