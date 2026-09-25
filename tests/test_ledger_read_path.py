"""A covering access path changes neither accounting nor transactional visibility."""

import sqlite3

import pytest
from signal_arcade.database import Database


def append(connection, account, debit, credit):
    connection.execute(
        "INSERT INTO ledger_entries(tx_id,created_at,account,debit_lamports,credit_lamports,memo) "
        "VALUES('fixture','2026-01-01T00:00:00+00:00',?,?,?,'memo')",
        (account, debit, credit),
    )


@pytest.mark.parametrize("account", ["cash", "inventory", "absent", "' OR 1=1 --"])
def test_ledger_index_preserves_exact_sum_and_restart(tmp_path, account):
    path = tmp_path / "ledger.sqlite3"
    db = Database(path)
    try:
        with db._lock, db._conn:
            for name, debit, credit in (
                ("cash", 9_000_000_000, 0),
                ("inventory", 12345, 678),
                ("cash", 0, 1_000_005_000),
                ("cash", 4500, 0),
                ("cash", 0, 4500),
            ):
                append(db._conn, name, debit, credit)
        expected = db._reader_conn.execute(
            "SELECT COALESCE(SUM(debit_lamports-credit_lamports),0) "
            "FROM ledger_entries NOT INDEXED WHERE account=?",
            (account,),
        ).fetchone()[0]
        assert db.ledger_balance(account) == expected
        plan = db._reader_conn.execute(
            "EXPLAIN QUERY PLAN SELECT SUM(debit_lamports-credit_lamports) "
            "FROM ledger_entries WHERE account=?",
            (account,),
        ).fetchall()
        assert any("COVERING INDEX idx_ledger_account_balance" in str(row[3]) for row in plan)
    finally:
        db.close()
    db = Database(path)
    try:
        assert db.ledger_balance(account) == expected
        assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 16
    finally:
        db.close()


def test_reader_sees_only_committed_balances_and_no_stale_value_after_rollback(tmp_path):
    db = Database(tmp_path / "visibility.sqlite3")
    try:
        with db._lock, db._conn:
            append(db._conn, "cash", 100, 0)
        with pytest.raises(RuntimeError), db._lock, db._conn:
            append(db._conn, "cash", 50, 0)
            assert db.ledger_balance("cash") == 100
            raise RuntimeError("rollback")
        assert db.ledger_balance("cash") == 100
        with db._lock, db._conn:
            append(db._conn, "cash", 0, 40)
        assert db.ledger_balance("cash") == 60
        with db._lock, db._conn:
            db._conn.execute("DELETE FROM ledger_entries")
        assert db.ledger_balance("cash") == 0
    finally:
        db.close()


def test_ledger_integer_sum_order_is_preserved(tmp_path):
    db = Database(tmp_path / "integer.sqlite3")
    try:
        with db._lock, db._conn:
            append(db._conn, "cash", 2**63 - 1, 0)
            append(db._conn, "cash", 0, 2**63 - 1)
            append(db._conn, "cash", 1, 0)
        assert db.ledger_balance("cash") == 1
        with db._lock, db._conn:
            append(db._conn, "cash", 2**63 - 1, 0)
        with pytest.raises(sqlite3.OperationalError, match="integer overflow"):
            db.ledger_balance("cash")
    finally:
        db.close()


def test_existing_schema_rebuilds_only_missing_access_path(tmp_path):
    path = tmp_path / "existing.sqlite3"
    db = Database(path)
    with db._lock, db._conn:
        append(db._conn, "cash", 550, 20)
        db._conn.execute("DROP INDEX idx_ledger_account_balance")
    db.close()
    db = Database(path)
    try:
        assert db.ledger_balance("cash") == 530
        assert db._conn.execute("PRAGMA index_info(idx_ledger_account_balance)").fetchall()
    finally:
        db.close()
