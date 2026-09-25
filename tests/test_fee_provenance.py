"""New receipt audit inputs preserve old quotes, accounts and rollback readers."""

import copy
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel, ValidationError, create_model
from signal_arcade.database import Database
from signal_arcade.intelligence.features import TokenState
from signal_arcade.models import FillReceipt, QuoteCurrency, Side
from signal_arcade.paper.broker import PaperBroker
from signal_arcade.paper.curve_math import quote_sell
from signal_arcade.paper.receipt_audit import fee_quote_replay_status
from test_broker import make_decision, make_features


def filled_pair(settings, venue, components, lp, currency=QuoteCurrency.SOL):
    database = Database(settings.database_path)
    broker = PaperBroker(database, settings)
    broker.initialize(currency, 10_000_000_000)
    now = datetime.now(UTC)
    state = TokenState(
        mint="mint",
        symbol="TEST",
        venue=venue,
        last_event_at=now,
        last_reserve_at=now,
        last_reserve_event_id="entry",
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
        real_quote_reserves=20_000_000_000,
        fee_bps=sum(components) if components is not None else 0,
        reserve_fee_components=components,
        reserve_lp_fee_bps=lp,
    )
    buy_order = broker.submit_decision(make_decision(now), sol_usd_price=150)
    assert buy_order is not None
    buy = broker._fill(buy_order, state, make_features(now), "entry", now, 150)
    assert buy is not None
    position = broker.positions["mint"]
    now += timedelta(seconds=1)
    state.last_event_at = state.last_reserve_at = now
    assert broker.schedule_profile_transition_exits(now) == 1
    sell_order = next(order for order in broker.pending.values() if order.side == Side.SELL)
    if lp:
        # LP fees remain in the pool, so the exact required vault balance is less
        # than gross. Record this boundary rather than testing only ample liquidity.
        gross = quote_sell(
            virtual_token_reserves=state.virtual_token_reserves,
            virtual_sol_reserves=state.virtual_quote_reserves,
            token_units=position.token_units,
            fee_bps=state.fee_bps,
            network_fee_lamports=settings.network_fee_lamports + settings.priority_fee_lamports,
            fee_components=components,
            lp_fee_bps=lp,
        ).curve_sol_lamports
        state.real_quote_reserves = gross - (gross * lp + 9999) // 10000
    sell = broker._fill(sell_order, state, make_features(now), "exit", now, 150)
    assert sell is not None
    return broker, database, buy, buy_order, sell, sell_order


@pytest.mark.parametrize("venue", ["pump_curve", "pump_swap"])
@pytest.mark.parametrize(
    "components,lp",
    [(None, 0), ((0, 0, 0), 0), ((25, 100), 0), ((3, 5, 75), 3), ((10, 10, 10), 10)],
)
@pytest.mark.parametrize("currency", [QuoteCurrency.SOL, QuoteCurrency.USDC])
def test_new_receipts_replay_both_sides_without_changing_accounting(
    settings, venue, components, lp, currency
):
    broker, database, buy, buy_order, sell, sell_order = filled_pair(
        settings, venue, components, lp, currency
    )
    try:
        assert fee_quote_replay_status(buy, buy_order) == "matched"
        assert fee_quote_replay_status(sell, sell_order) == "matched"
        assert buy.execution_fee_provenance["rounding"] == "aggregate"
        assert buy.execution_fee_provenance["fee_components"] is None
        assert buy.execution_fee_provenance["lp_fee_bps"] == 0
        assert sell.execution_fee_provenance["fee_components"] == (
            list(components) if components is not None else None
        )
        assert sell.execution_fee_provenance["source"] == (
            "observed_event" if components is not None else "configured_fallback"
        )
        assert broker.cash_lamports == database.ledger_balance("cash")
        assert not broker.positions
        assert not broker.chronology_issues()
        for receipt in database.list_fills():
            original = buy if receipt.side == Side.BUY else sell
            assert receipt.model_dump(mode="json") == original.model_dump(mode="json")
        restored = PaperBroker(database, settings)
        assert restored.cash_lamports == broker.cash_lamports
        assert not restored.positions
        assert not restored.chronology_issues()
    finally:
        database.close()


def test_receipt_provenance_is_detached_and_older_reader_ignores_only_outer_extension(settings):
    _, database, buy, buy_order, sell, sell_order = filled_pair(
        settings, "pump_curve", (25, 100), 0
    )
    try:
        previous_reader = create_model(
            "PreviousFillReceipt",
            __base__=BaseModel,
            **{
                name: (field.annotation, copy.deepcopy(field))
                for name, field in FillReceipt.model_fields.items()
                if name != "execution_fee_provenance"
            },
        )
        original = sell.model_dump(mode="json")
        assert previous_reader.model_validate(original).model_dump(mode="json") == {
            key: value for key, value in original.items() if key != "execution_fee_provenance"
        }
        incompatible = copy.deepcopy(original)
        incompatible["reserve_snapshot"]["fee_components"] = [25, 100]
        with pytest.raises(ValidationError):
            previous_reader.model_validate(incompatible)
        sell.execution_fee_provenance["fee_components"][0] = 999
        saved = next(row for row in database.list_fills() if row.side == Side.SELL)
        assert saved.execution_fee_provenance["fee_components"] == [25, 100]
        assert fee_quote_replay_status(saved, sell_order) == "matched"
        assert fee_quote_replay_status(buy, buy_order) == "matched"
    finally:
        database.close()


@pytest.mark.parametrize(
    "metadata,expected",
    [
        (None, "unavailable"),
        ("broken", "unavailable"),
        ({"version": 2}, "unavailable"),
        ({"version": True}, "unavailable"),
        ({"version": 1}, "invalid_inputs"),
    ],
)
def test_missing_unknown_or_damaged_optional_metadata_does_not_hide_a_receipt(
    settings, metadata, expected
):
    _, database, buy, order, _, _ = filled_pair(settings, "pump_curve", (25, 100), 0)
    try:
        raw = buy.model_dump(mode="json")
        raw["execution_fee_provenance"] = metadata
        restored = FillReceipt.model_validate(raw)
        assert restored.net_sol_lamports == buy.net_sol_lamports
        assert fee_quote_replay_status(restored, order) == expected
    finally:
        database.close()


@pytest.mark.parametrize(
    "change",
    ["sum", "lp", "bool", "buy_components", "source", "amount", "missing_order", "wrong_order"],
)
def test_quote_replay_never_verifies_incomplete_or_inconsistent_inputs(settings, change):
    _, database, buy, buy_order, sell, sell_order = filled_pair(
        settings, "pump_curve", (25, 100), 0
    )
    try:
        receipt, order = (buy, buy_order) if change == "buy_components" else (sell, sell_order)
        receipt = receipt.model_copy(deep=True)
        recipe = receipt.execution_fee_provenance
        expected = "invalid_inputs"
        if change == "sum":
            recipe["fee_components"] = [1, 2]
        elif change == "lp":
            recipe["lp_fee_bps"] = 7
        elif change == "bool":
            recipe["fee_components"] = [True, 124]
        elif change == "buy_components":
            recipe.update(rounding="components", fee_components=[25, 100])
        elif change == "source":
            recipe["source"] = "invented"
        elif change == "amount":
            receipt.protocol_fee_lamports += 1
            expected = "mismatch"
        elif change == "missing_order":
            order, expected = None, "unavailable"
        else:
            order = order.model_copy(update={"order_id": "different"})
        assert fee_quote_replay_status(receipt, order) == expected
    finally:
        database.close()
