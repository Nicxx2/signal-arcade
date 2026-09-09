"""Avoid repeated valuation without skipping a new market fact or durable risk state."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.intelligence.features import TokenState
from signal_arcade.models import EventKind, QuoteCurrency, RiskMode, Side
from signal_arcade.paper.broker import PaperBroker
from test_broker import make_broker, make_decision, make_features


def _update(broker, path, **kwargs):
    if path == "clock":
        kwargs.pop("event_kind")
        return broker.reassess_and_process_due_orders(**kwargs)
    return broker.on_market_state(**kwargs)


@pytest.fixture
def held(settings):
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    state = TokenState(
        mint="mint",
        symbol="TEST",
        last_event_at=now,
        last_reserve_at=now,
        last_reserve_event_id="entry",
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
        real_quote_reserves=20_000_000_000,
    )
    assert broker.submit_decision(make_decision(now))
    assert broker.process_due_orders(
        state=state,
        features=make_features(now),
        source_event_id="entry",
        now=now,
        mode=RiskMode.BALANCED,
    )
    try:
        yield broker, database, state, now + timedelta(seconds=1)
    finally:
        database.close()


@pytest.mark.parametrize("route", ["valid", "stale", "empty", "conversion"])
@pytest.mark.parametrize("path", ["market", "clock"])
def test_market_update_values_held_position_once_and_saves_assessment(
    path, held, monkeypatch, route
):
    broker, database, state, now = held
    state.last_event_at = state.last_reserve_at = now
    features = make_features(now)
    if route == "stale":
        features.hard_flags.append("stale_market_data")
    elif route == "empty":
        state.real_quote_reserves = 0
    elif route == "conversion":
        broker.quote_currency = QuoteCurrency.USDC
    marks, saves = [], []
    real_mark, real_save = broker._mark_position, database.save_position

    def mark(*args, **kwargs):
        marks.append(1)
        return real_mark(*args, **kwargs)

    def save(position):
        saves.append(position.model_dump(mode="json"))
        return real_save(position)

    monkeypatch.setattr(broker, "_mark_position", mark)
    monkeypatch.setattr(database, "save_position", save)
    assert (
        _update(
            broker,
            path,
            state=state,
            features=features,
            event_kind=EventKind.TRADE,
            source_event_id="tick",
            now=now,
            mode=RiskMode.BALANCED,
            soft_hold_seconds=300,
            soft_hold_participant={"kind": "champion", "skill": "exit", "version": "exit-v1"},
        )
        == []
    )
    assert len(marks) == 1
    assert len(saves) == 2  # Fresh mark plus the new exit assessment; neither is omitted.
    position = broker.positions["mint"]
    assert saves[-1] == position.model_dump(mode="json")
    assert position.exit_assessment.strategy_participant["version"] == "exit-v1"
    season = database.current_paper_season()
    assert season["strategy_usage"]["skills_observed"] == ["exit"]
    if route != "valid":
        assert not position.mark_is_executable
        assert not broker.has_pending_for("mint", Side.SELL)


@pytest.mark.parametrize("path", ["market", "clock"])
def test_same_timestamp_new_reserves_and_standalone_order_processing_still_refresh(path, held):
    broker, _database, state, now = held
    state.last_event_at = state.last_reserve_at = now
    arguments = dict(
        state=state,
        features=make_features(now),
        source_event_id="tick",
        now=now,
        mode=RiskMode.BALANCED,
    )
    _update(broker, path, **arguments, event_kind=EventKind.TRADE)
    first = broker.positions["mint"].last_mark_lamports
    state.virtual_quote_reserves += 100_000_000
    _update(broker, path, **arguments, event_kind=EventKind.TRADE)
    second = broker.positions["mint"].last_mark_lamports
    assert second > first
    state.virtual_quote_reserves += 100_000_000
    broker.process_due_orders(**arguments)
    assert broker.positions["mint"].last_mark_lamports > second


@pytest.mark.parametrize("failure_at", [1, 2])
@pytest.mark.parametrize("path", ["market", "clock"])
def test_failed_mark_or_assessment_never_continues_to_fill(path, held, monkeypatch, failure_at):
    broker, database, state, now = held
    original = database.save_position
    calls = 0

    def save(position):
        nonlocal calls
        calls += 1
        if calls == failure_at:
            raise RuntimeError("position persistence failed")
        return original(position)

    monkeypatch.setattr(database, "save_position", save)
    cash = broker.cash_lamports
    with pytest.raises(RuntimeError, match="position persistence failed"):
        _update(
            broker,
            path,
            state=state,
            features=make_features(now),
            event_kind=EventKind.TRADE,
            source_event_id="tick",
            now=now,
            mode=RiskMode.BALANCED,
        )
    assert broker.cash_lamports == cash == database.ledger_balance("cash")
    assert len(database.list_fills()) == 1
    assert not broker.has_pending_for("mint", Side.SELL)


@pytest.mark.parametrize("path", ["market", "clock"])
def test_recovered_route_peak_and_assessment_survive_restart(path, held):
    broker, database, state, now = held
    state.real_quote_reserves = 0
    arguments = dict(state=state, source_event_id="tick", now=now, mode=RiskMode.BALANCED)
    _update(broker, path, **arguments, features=make_features(now), event_kind=EventKind.TRADE)
    assert not broker.positions["mint"].mark_is_executable
    broker.positions["mint"].peak_mark_lamports = 10**15
    state.real_quote_reserves = 20_000_000_000
    state.last_event_at = state.last_reserve_at = now
    _update(broker, path, **arguments, features=make_features(now), event_kind=EventKind.TRADE)
    position = broker.positions["mint"]
    assert position.mark_is_executable
    assert position.peak_mark_lamports == position.last_mark_lamports
    restored = PaperBroker(database, broker.settings).positions["mint"]
    assert restored == position


@pytest.mark.parametrize("path", ["market", "clock"])
def test_combined_market_path_defers_future_reserve_without_filling_pending_buy(path, held):
    broker, database, entry_state, now = held
    state = deepcopy(entry_state)
    state.mint = "other"
    reserve_at = now + timedelta(seconds=1)
    state.last_event_at = state.last_reserve_at = reserve_at
    state.last_reserve_event_id = "future-other"
    order = broker.submit_decision(make_decision(now, "other"))
    assert order is not None
    cash = broker.cash_lamports
    assert (
        _update(
            broker,
            path,
            state=state,
            features=make_features(now, "other"),
            event_kind=EventKind.TRADE,
            source_event_id="future-other",
            now=now,
            mode=RiskMode.BALANCED,
        )
        == []
    )
    assert order.order_id in broker.pending
    assert "other" not in broker.positions
    assert cash == broker.cash_lamports == database.ledger_balance("cash")
    receipts = _update(
        broker,
        path,
        state=state,
        features=make_features(reserve_at, "other"),
        event_kind=EventKind.TRADE,
        source_event_id="future-other",
        now=reserve_at,
        mode=RiskMode.BALANCED,
    )
    assert len(receipts) == 1
    assert receipts[0].reserve_snapshot.observed_at == reserve_at
    assert order.order_id not in broker.pending
    assert broker.cash_lamports == database.ledger_balance("cash")
