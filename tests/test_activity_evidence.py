"""Descriptive value flow must stay separate from strategy and learned authority."""

from collections import deque
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.intelligence import features as feature_module
from signal_arcade.intelligence.activity import ACTIVITY_UNITS, activity_metrics
from signal_arcade.intelligence.decision import DecisionEngine
from signal_arcade.intelligence.features import FeatureEngine, TokenState, TradeObservation
from signal_arcade.intelligence.learning import _feature_vector
from signal_arcade.models import RISK_LIMITS, DataValue, RiskMode, Side
from signal_arcade.paper.exit_policy import assess_exit
from signal_arcade.strategy import SUPPORTED_BASELINE_VERSIONS
from test_exit_policy import position

NOW = datetime(2026, 9, 20, 12, tzinfo=UTC)


def trade(amount, *, side=Side.BUY, wallet="wallet", age=0, venue="pump_curve"):
    return TradeObservation(
        received_at=NOW - timedelta(seconds=age),
        slot=1,
        side=side,
        user=wallet,
        token_units=1,
        quote_lamports=amount,
        price_sol=max(0, amount) / 1_000_000_000,
        venue=venue,
        signature="test",
    )


def snapshot_with(trades):
    engine = FeatureEngine()
    state = TokenState(
        mint="mint",
        created_at=NOW - timedelta(minutes=10),
        last_event_at=NOW,
        virtual_quote_reserves=30_000_000_000,
        virtual_token_reserves=1_000_000_000_000_000,
        trades=deque(trades, maxlen=3600),
    )
    engine.tokens[state.mint] = state
    snapshot = engine.snapshot("mint", NOW)
    assert snapshot is not None
    return engine, state, snapshot


def test_dust_count_and_buy_count_do_not_masquerade_as_value_flow():
    rows = [trade(1000, wallet="dust") for _ in range(90)]
    rows.extend(
        [trade(1_000_000_000, side=Side.SELL, wallet="seller"), trade(10_000_000, wallet="buyer")]
    )
    metrics = activity_metrics(rows, NOW)
    assert metrics["buy_quote_volume_ratio_5m"][0] < 0.011
    assert metrics["signed_net_quote_flow_ratio_5m"][0] < -0.97
    assert metrics["meaningful_trade_count_5m"][0] == 2
    assert metrics["meaningful_trade_wallet_count_5m"][0] == 2
    assert metrics["net_buy_wallet_count_5m"][0] == 1


def test_repeated_dust_and_round_trips_are_not_single_meaningful_trades_or_net_buyers():
    rows = [
        trade(1_000_000, wallet="dust", side=Side.BUY if i % 2 else Side.SELL) for i in range(40)
    ]
    metrics = activity_metrics(rows, NOW)
    assert metrics["meaningful_trade_wallet_count_5m"][0] == 0
    assert metrics["net_buy_wallet_count_5m"][0] == 0
    assert metrics["signed_net_quote_flow_ratio_5m"][0] == 0
    rows.extend(
        [trade(1_000_000_000, wallet="loop"), trade(1_000_000_000, wallet="loop", side=Side.SELL)]
    )
    metrics = activity_metrics(rows, NOW)
    assert metrics["meaningful_trade_wallet_count_5m"][0] == 1
    assert metrics["net_buy_wallet_count_5m"][0] == 0


@pytest.mark.parametrize("amount", [0, -1])
def test_incomplete_amounts_remain_unknown_even_when_most_rows_have_values(amount):
    metrics = activity_metrics([trade(20_000_000) for _ in range(99)] + [trade(amount)], NOW)
    assert metrics["trade_amount_coverage_5m"] == (0.99, 1.0, None)
    assert all(
        value[0] is None for key, value in metrics.items() if key != "trade_amount_coverage_5m"
    )


@pytest.mark.parametrize("wallet", ["unknown", ""])
def test_unknown_wallet_does_not_erase_observed_amounts_or_invent_participation(wallet):
    metrics = activity_metrics([trade(20_000_000, wallet=wallet)], NOW)
    assert metrics["buy_quote_volume_ratio_5m"] == (1.0, 1.0, None)
    assert metrics["meaningful_trade_count_5m"][0] == 1
    assert metrics["meaningful_trade_wallet_count_5m"][0] is None
    assert metrics["net_buy_wallet_count_5m"][0] is None
    assert all(value[0] is None for value in activity_metrics([], NOW).values())


def test_time_amount_venue_cache_and_buffer_boundaries():
    rows = [
        trade(9_999_999),
        trade(10_000_000, age=60),
        trade(10_000_000, age=60.001),
        trade(10_000_000, age=300),
        trade(10_000_000, age=300.001),
        trade(10_000_000, age=-1),
        trade(10_000_000, venue="pump_swap"),
    ]
    engine, state, snapshot = snapshot_with(rows)
    assert snapshot.values["meaningful_trade_count_1m"].value == 1
    assert snapshot.values["meaningful_trade_count_5m"].value == 3
    state.trades.append(trade(10_000_000))
    cached = engine.snapshot("mint", NOW + timedelta(milliseconds=500))
    assert cached.values["meaningful_trade_count_5m"].value == 3
    assert cached.values["meaningful_trade_count_5m"].as_of == NOW
    assert cached.values["meaningful_trade_count_5m"].freshness_seconds == 0.5
    state.last_evicted_trade = trade(10_000_000)
    assert engine.snapshot("mint", NOW).values["trade_buffer_saturated"].value is True
    state.quote_mint = "unsupported"
    assert all(engine.snapshot("mint", NOW).values[name].value is None for name in ACTIVITY_UNITS)
    state.venue = "pump_swap"
    state.quote_mint = "So11111111111111111111111111111111111111112"
    changed = engine.snapshot("mint", NOW)
    assert changed.values["meaningful_trade_count_5m"].value == 1
    expired = engine.snapshot("mint", NOW + timedelta(seconds=302))
    assert all(expired.values[name].value is None for name in ACTIVITY_UNITS)


def test_dashboard_and_position_marks_skip_activity_work_without_hiding_decision_evidence(
    monkeypatch,
):
    engine, state, _ = snapshot_with([trade(20_000_000, age=59.8)])
    state.rolling_trade_metrics = None
    calls = []
    original = feature_module.activity_metrics

    def measured(trades, at):
        calls.append(at)
        return original(trades, at)

    monkeypatch.setattr(feature_module, "activity_metrics", measured)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(feature_module, "datetime", Clock)
    assert not (engine.list_snapshots()[0].values.keys() & ACTIVITY_UNITS.keys())
    assert not (engine.position_snapshot("mint", NOW).values.keys() & ACTIVITY_UNITS.keys())
    assert not (
        engine.snapshot("mint", NOW, include_activity=False).values.keys() & ACTIVITY_UNITS.keys()
    )
    assert calls == []
    # A later full decision must use the original cached window's time, not move its
    # 60-second boundary while retaining that window's other fields and timestamp.
    decision = engine.snapshot("mint", NOW + timedelta(milliseconds=500))
    assert decision.values["meaningful_trade_count_1m"].value == 1
    assert decision.values["meaningful_trade_count_1m"].as_of == NOW
    assert calls == [NOW]
    engine.snapshot("mint", NOW + timedelta(milliseconds=600))
    assert calls == [NOW]
    # A previously collected window does not leak optional fields into a priority read.
    priority = engine.snapshot("mint", NOW + timedelta(milliseconds=500), include_activity=False)
    assert (
        priority.model_dump()
        == decision.model_copy(
            update={
                "values": {
                    key: value
                    for key, value in decision.values.items()
                    if key not in ACTIVITY_UNITS
                }
            }
        ).model_dump()
    )
    assert calls == [NOW]


@pytest.mark.parametrize("version", sorted(SUPPORTED_BASELINE_VERSIONS))
@pytest.mark.parametrize("mode", list(RiskMode))
def test_observational_metrics_do_not_change_any_baseline_or_learning_vector(version, mode):
    _, _, snapshot = snapshot_with(
        [
            trade(
                10_000_000 + i * 111_111,
                wallet=f"w{i}",
                age=i,
                side=Side.BUY if i % 3 else Side.SELL,
            )
            for i in range(40)
        ]
    )
    snapshot.values["integrity_window_complete"] = DataValue(
        value=True, unit="boolean", as_of=NOW, sources=["test"], quality=1, freshness_seconds=0
    )
    legacy = snapshot.model_copy(deep=True)
    for key in ACTIVITY_UNITS:
        del legacy.values[key]
    engine = DecisionEngine()
    before = engine.evaluate(legacy, mode, baseline_version=version)
    after = engine.evaluate(snapshot, mode, baseline_version=version)
    for field in (
        "action",
        "score",
        "reasons",
        "blockers",
        "integrity_assessment",
        "sizing_assessment",
    ):
        assert getattr(before, field) == getattr(after, field)
    assert _feature_vector(before) is not None
    assert _feature_vector(before) == _feature_vector(after)
    held = position(NOW, age_seconds=RISK_LIMITS[mode].max_hold_seconds + 1)
    held.baseline_version_at_entry = version
    assert assess_exit(
        position=held, features=legacy, now=NOW, limits=RISK_LIMITS[mode]
    ) == assess_exit(position=held, features=snapshot, now=NOW, limits=RISK_LIMITS[mode])
