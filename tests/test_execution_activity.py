from datetime import timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.intelligence.execution_activity import build_execution_activity
from signal_arcade.models import ChallengerEvaluationReceipt, FillReceipt, PaperOrder, Side
from test_champion_impact import NOW, comparison, report, rows_for
from test_learning import make_decision


def example():
    at = NOW - timedelta(minutes=10)
    decision = make_decision(at, "test-mint").model_copy(
        update={
            "season_id": "season",
            "season_profile_fingerprint": "profile",
            "configuration_fingerprint": "config",
        }
    )
    receipt = ChallengerEvaluationReceipt(
        artifact_version="champion-manipulation",
        skill="manipulation",
        evaluated_at=at,
        in_distribution=False,
        proposed_action="veto",
        baseline_actionable=True,
        parameters={
            "applied": False,
            "policy_origin_status": "recorded",
            "policy_origin_relation": "later_attempt",
            "policy_origin_at": (at - timedelta(minutes=1)).isoformat(),
        },
    )
    decision.challenger_assessments = {"manipulation": receipt.model_dump(mode="json")}
    entry = FillReceipt(
        fill_id="buy",
        order_id="order",
        mint=decision.mint,
        symbol="TEST",
        side="buy",
        filled_at=at + timedelta(seconds=1),
        token_units=100,
        gross_sol_lamports=100,
        protocol_fee_lamports=1,
        network_fee_lamports=1,
        net_sol_lamports=102,
        price_impact_fraction=0,
        latency_ms=1,
        source_event_id="event",
        venue="pump_curve",
    )
    close = entry.model_copy(
        update={
            "fill_id": "sell",
            "order_id": "sell-order",
            "side": Side.SELL,
            "filled_at": at + timedelta(minutes=2),
            "position_opened_at": entry.filled_at,
            "account_net_minor": 95,
        }
    )
    return entry, close, decision


def result(rows):
    return build_execution_activity(
        rows,
        versions={"manipulation": "champion-manipulation"},
        since=NOW - timedelta(hours=1),
        season_id="season",
        profile="profile",
        configuration="config",
        now=NOW,
    )["skills"][0]


def test_actual_fallback_preserves_loss_and_does_not_credit_unapplied_veto():
    row = example()
    original = [x.model_dump() for x in row]
    summary = result([row, row])
    assert summary["observed_count"] == summary["fallback"] == summary["later_fallback"] == 1
    assert summary["outcomes"][0]["net_minor"] == -7
    assert summary["outcomes"][0]["winning_count"] == 0
    assert [x.model_dump() for x in row] == original


def test_applied_supported_entry_is_counted_separately_from_fallback():
    entry, close, decision = example()
    receipt = decision.challenger_assessments["manipulation"]
    receipt.update(in_distribution=True, proposed_action="support")
    receipt["parameters"]["applied"] = True
    summary = result([(entry, close, decision)])
    assert summary["supported_entry"] == 1
    assert summary["fallback"] == summary["later_fallback"] == summary["unknown"] == 0
    assert summary["outcomes"][0]["category"] == "supported_entry"
    assert summary["outcomes"][0]["net_minor"] == -7


@pytest.mark.parametrize("case", ["missing", "wrong_version", "wrong_clock", "applied_veto"])
def test_unknown_receipts_do_not_invent_support_or_profit(case):
    entry, close, decision = example()
    receipt = decision.challenger_assessments["manipulation"]
    if case == "missing":
        decision.challenger_assessments.clear()
    elif case == "wrong_version":
        receipt["artifact_version"] = "replacement"
    elif case == "wrong_clock":
        receipt["evaluated_at"] = NOW.isoformat()
    else:
        receipt["in_distribution"] = True
        receipt["parameters"]["applied"] = True
    summary = result([(entry, close, decision)])
    assert summary["unknown"] == 1
    assert summary["outcomes"] == []


@pytest.mark.parametrize("case", ["open", "currency", "units", "future", "wrong_position"])
def test_only_exact_complete_paper_pairs_produce_results(case):
    entry, close, decision = example()
    if case == "open":
        close = None
    elif case == "currency":
        close.account_currency = "USDC"
    elif case == "units":
        close.token_units -= 1
    elif case == "future":
        close.filled_at = NOW + timedelta(seconds=1)
    else:
        close.position_opened_at -= timedelta(seconds=1)
    group = result([(entry, close, decision)])["outcomes"][0]
    assert group["closed_count"] == 0 and group["unresolved_count"] == 1


@pytest.mark.parametrize(
    "field",
    [
        "season_id",
        "season_profile_fingerprint",
        "configuration_fingerprint",
    ],
)
def test_context_changes_cannot_inherit_entry_results(field):
    entry, close, decision = example()
    setattr(decision, field, "other")
    assert result([(entry, close, decision)])["observed_count"] == 0


@pytest.mark.parametrize("reverse", [True, False])
def test_exact_parent_lookup_survives_window_boundary_duplicate_and_restart(tmp_path, reverse):
    entry, close, decision = example()
    path = tmp_path / "audit.sqlite3"
    db = Database(path)
    db.save_decision(decision)
    order = PaperOrder(
        order_id=entry.order_id,
        mint=entry.mint,
        symbol=entry.symbol,
        side="buy",
        decision_id=decision.decision_id,
        requested_sol_lamports=102,
        created_at=decision.created_at,
        fill_after=entry.filled_at,
    )
    db.save_order(order)
    db.save_order(order.model_copy(update={"order_id": close.order_id, "side": Side.SELL}))
    db.save_fill(entry)
    db.save_fill(close)
    db.close()
    db = Database(path)
    try:
        fills = [entry, close] if reverse else [close, entry]
        assert db.entry_receipt_sample(fills + [close]) == [(entry, close, decision)]
        assert db.entry_receipt_sample([close]) == [(entry, close, decision)]
        duplicate_close = close.model_copy(update={"fill_id": "other-close"})
        assert db.entry_receipt_sample([close, duplicate_close]) == [(entry, None, decision)]
        with pytest.raises(ValueError):
            db.entry_receipt_sample([entry] * 31)
        query = db._reader_conn.execute(
            "EXPLAIN QUERY PLAN SELECT record_json FROM fills "
            "WHERE mint=? AND side='buy' AND filled_at=? LIMIT 2",
            (entry.mint, entry.filled_at.isoformat()),
        ).fetchall()
        assert any("idx_fills_mint_side_time" in str(r[3]) for r in query)
        db.save_order(order.model_copy(update={"order_id": "ambiguous-order"}))
        db.save_fill(
            entry.model_copy(
                update={
                    "fill_id": "ambiguous-buy",
                    "order_id": "ambiguous-order",
                }
            )
        )
        assert db.entry_receipt_sample([close]) == []
    finally:
        db.close()


def test_policy_action_counts_preserve_missing_and_do_not_count_pending_as_failures():
    rows, versions = rows_for(("manipulation",), count=4)
    rows[0].challenger_evaluations[versions["manipulation"]].proposed_action = "veto"
    rows[1].challenger_evaluations[versions["manipulation"]].in_distribution = False
    rows[2].challenger_evaluations.clear()
    rows[3].status = "pending"
    rows[3].checkpoints.clear()
    value = comparison(report(rows, versions), "manipulation")
    assert value["actions"] == {
        "supported_entry": 0,
        "supported_veto": 1,
        "fallback": 1,
        "unavailable": 1,
    }
    assert value["pending_count"] == 1
    assert value["cash_reference_mean"] == 0
