from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from signal_arcade.database import Database
from signal_arcade.models import FillReceipt, OrderStatus, PaperOrder, Side
from signal_arcade.orchestrator import Orchestrator
from test_broker import make_broker


def save_trade(db, mint, at, profit=10):
    receipts = []
    for side, delta, value in ((Side.BUY, 0, 100), (Side.SELL, 300, 100 + profit)):
        when = at + timedelta(seconds=delta)
        order = PaperOrder(
            order_id=f"{mint}-{side.value}-order",
            mint=mint,
            symbol=mint,
            side=side,
            status=OrderStatus.FILLED,
            created_at=when,
            fill_after=when,
            filled_at=when,
        )
        fill = FillReceipt(
            fill_id=f"{mint}-{side.value}-fill",
            order_id=order.order_id,
            mint=mint,
            symbol=mint,
            side=side,
            filled_at=when,
            token_units=100,
            gross_sol_lamports=value,
            net_sol_lamports=value,
            protocol_fee_lamports=2,
            network_fee_lamports=3,
            price_impact_fraction=0,
            latency_ms=0,
            source_event_id="fixture",
            venue="pump_curve",
            position_opened_at=at if side == Side.SELL else None,
        )
        db.save_order(order)
        db.save_fill(fill)
        receipts.append(fill)
    return receipts


def test_restart_summary_and_leaderboard_ignore_ui_cap_and_cross_page_entries(
    settings, monkeypatch
):
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    at = datetime.now(UTC) - timedelta(hours=3)
    for i in range(12):
        save_trade(database, str(i), at + timedelta(minutes=i), profit=i - 5)
    original_iterator = database.iter_fill_contexts
    monkeypatch.setattr(database, "iter_fill_contexts", lambda: original_iterator(page_size=3))
    monkeypatch.setattr(
        database, "list_fills", lambda *args: pytest.fail("UI limit used for authority")
    )
    restarted = make_broker(database, settings)
    assert restarted.traded_mints == {str(i) for i in range(12)}
    assert restarted.chronology_issues() == []
    summary = restarted.season_summary()
    assert summary["total_fees_minor"] == 120
    assert summary["closed_trades"] == 12
    assert summary["wins"] == 6 and summary["losses"] == 5 and summary["break_even"] == 1
    assert summary["execution_audit_issue_count"] == 0
    for sort, expected in (("profit", [6, 5]), ("loss", [-5, -4])):
        board = Orchestrator.leaderboard(
            SimpleNamespace(database=database, broker=broker),
            sort=sort,
            limit=2,
            positions=[],
            quote_currency="SOL",
            quote_decimals=9,
        )
        assert board["available_rows"] == 12
        assert [row["pnl_minor"] for row in board["rows"]] == expected
        assert board["summary"]["total_fees_minor"] == 120
        assert board["summary"]["total_realized_pnl_minor"] == 6
    database.close()


def test_fill_snapshot_survives_concurrent_rollover_without_owning_core_locks(settings):
    database = Database(settings.database_path)
    at = datetime.now(UTC)
    for mint in ("a", "b", "c"):
        save_trade(database, mint, at)
    iterator = database.iter_fill_contexts(page_size=1)
    first = next(iterator)
    with database._lock, database._reader_lock, database._conn:
        database._conn.execute("DELETE FROM fills")
        remaining = list(iterator)
    assert len([first, *remaining]) == 6
    assert all(entry is not None for _, _, entry, _ in remaining)
    assert list(database.iter_fill_contexts()) == []
    database.close()


@pytest.mark.parametrize("page_size", [0, -1, 1001])
def test_fill_iterator_rejects_invalid_page_limits(settings, page_size):
    database = Database(settings.database_path)
    with pytest.raises(ValueError, match="page size"):
        list(database.iter_fill_contexts(page_size=page_size))
    database.close()


@pytest.mark.parametrize("malformed", [False, True])
def test_fill_reader_releases_snapshot_after_close_or_decode_failure(settings, malformed):
    from pydantic import ValidationError

    database = Database(settings.database_path)
    save_trade(database, "first", datetime.now(UTC))
    if malformed:
        with database._lock, database._conn:
            database._conn.execute("UPDATE fills SET record_json='{}' WHERE side='buy'")
    iterator = database.iter_fill_contexts(page_size=1)
    if malformed:
        with pytest.raises(ValidationError):
            next(iterator)
    else:
        next(iterator)
        iterator.close()
    save_trade(database, "later", datetime.now(UTC))
    # A leaked read transaction would prevent truncating the WAL after the new writes.
    assert database._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0
    database.close()
