"""Attribute cleanup cost without changing deadlines or committed evidence."""

import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import signal_arcade.database as database_module
from signal_arcade.database import Database
from signal_arcade.models import EventKind, MarketEvent


@pytest.mark.parametrize("fail_commit", [False, True])
def test_execute_and_transaction_exit_are_separate_and_count_only_commits(
    tmp_path, monkeypatch, fail_commit
):
    db = Database(tmp_path / "cost.sqlite3")
    now = datetime.now(UTC)
    db.append_event(MarketEvent(event_id="old", source="test", kind=EventKind.TRADE, mint="m"))
    conn = db._conn
    clock = [0.0]

    class TimedConnection:
        def __getattr__(self, name):
            return getattr(conn, name)

        def __enter__(self):
            conn.__enter__()
            return self

        def execute(self, sql, *args):
            result = conn.execute(sql, *args)
            if sql.startswith("DELETE"):
                clock[0] += 0.002
            return result

        def __exit__(self, *args):
            clock[0] += 0.065
            if fail_commit:
                conn.rollback()
                error = sqlite3.OperationalError("fixture commit failure")
                error.sqlite_errorcode = sqlite3.SQLITE_BUSY
                raise error
            return conn.__exit__(*args)

    try:
        monkeypatch.setattr(db, "_conn", TimedConnection())
        monkeypatch.setattr(database_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
        timing = {}
        result = db.prune_history(now + timedelta(days=1), max_duration_seconds=0.05, timing=timing)
        assert timing["raw_trades_execute_seconds"] == pytest.approx(0.002)
        assert timing["raw_trades_transaction_exit_seconds"] == pytest.approx(0.065)
        assert timing["raw_trades_query_seconds"] == pytest.approx(0.067)
        assert timing["raw_trades_committed_rows"] == result["raw_trades"] == int(not fail_commit)
        assert timing["raw_trades_completed_queries"] == int(not fail_commit)
        assert conn.execute("SELECT COUNT(*) FROM market_events").fetchone()[0] == int(fail_commit)
        assert not conn.in_transaction
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        monkeypatch.undo()
        db.close()
