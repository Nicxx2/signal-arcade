from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.models import PaperOrder, QuoteCurrency, RiskMode, Side
from signal_arcade.paper.broker import PaperBroker
from test_broker import make_current_decision


@pytest.mark.parametrize("mode", list(RiskMode))
@pytest.mark.parametrize("quote", list(QuoteCurrency))
@pytest.mark.parametrize("change", ["cash_spent", "cash_reserved"])
def test_sizing_reuses_only_this_call_and_submission_rechecks(
    settings, monkeypatch, mode, quote, change
):
    db = Database(settings.database_path)
    broker = PaperBroker(db, settings)
    starting = 10_000_000_000 if quote == QuoteCurrency.SOL else 400_000_000
    broker.initialize(quote, starting)
    price = None if quote == QuoteCurrency.SOL else 140.0
    now = datetime.now(UTC)
    decision = make_current_decision(now, "fresh-gates")
    decision.risk_mode = mode
    calls = []
    original = broker.snapshot

    def snapshot(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(result)
        return result

    monkeypatch.setattr(broker, "snapshot", snapshot)
    try:
        first = broker.plan_entry_size(decision, sol_usd_price=price)
        assert len(calls) == 1
        if change == "cash_spent":
            db.append_ledger(
                "cash-consumed",
                [("cash", 0, starting, "fixture"), ("fixture", starting, 0, "fixture")],
            )
        else:
            broker.pending["reserved"] = PaperOrder(
                order_id="reserved",
                mint="other",
                symbol="OTHER",
                side=Side.BUY,
                requested_sol_lamports=1_000_000_000,
                reserved_account_minor=starting,
                created_at=now,
                fill_after=now + timedelta(seconds=30),
            )
        second = broker.plan_entry_size(decision, sol_usd_price=price)
        assert len(calls) == 2
        assert second.selected_size_sol < first.selected_size_sol
        assert "available_cash" in second.constraints
        # A previously planned size cannot bypass the fresh submission gate.
        decision.planned_order_size_sol = first.selected_size_sol
        decision.sizing_assessment = first
        order, blocker = broker.submit_decision_with_reason(decision, sol_usd_price=price)
        assert order is None and blocker is not None
        assert len(calls) > 2
        assert not db.list_fills()
    finally:
        db.close()


def test_sizing_uninitialized_and_missing_conversion_remain_supported(settings):
    db = Database(settings.database_path)
    broker = PaperBroker(db, settings)
    decision = make_current_decision(datetime.now(UTC), "unknown-conversion")
    try:
        assert broker.plan_entry_size(decision).selected_size_sol > 0
        assert broker.entry_blocker(decision) is not None
        broker.initialize(QuoteCurrency.USDC, 400_000_000)
        assert broker.plan_entry_size(decision, sol_usd_price=None).selected_size_sol > 0
        assert broker.entry_blocker(decision, sol_usd_price=None) is not None
    finally:
        db.close()
