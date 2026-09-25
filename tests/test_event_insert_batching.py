"""Fewer SQL calls must not split durability or change event identity/order semantics."""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.models import EventKind, MarketEvent


def event(index):
    return MarketEvent(
        event_id=f"e{index:05}",
        source="fixture",
        kind=EventKind.TRADE,
        mint="mint",
        slot=index,
        received_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=index),
        payload={"index": index},
    )


@pytest.mark.parametrize("size", [0, 1, 31, 32, 63, 64, 65, 129, 250, 2000])
def test_atomic_batch_ids_and_restart_at_statement_boundaries(tmp_path, size):
    path = tmp_path / "batch.sqlite3"
    database = Database(path)
    rows = [event(i) for i in range(size)]
    try:
        database._conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)
        database.append_event(event(0))  # existing duplicate
        statements = []
        database._conn.set_trace_callback(statements.append)
        inserted = (
            database.append_events([*rows, *rows[:2]]) if rows else database.append_events([])
        )
        database._conn.set_trace_callback(None)
        assert inserted == {row.event_id for row in rows} - {"e00000"}
        commits = [sql for sql in statements if sql == "COMMIT"]
        assert len(commits) == bool(rows)
        database.close()
        database = Database(path)
        saved = database.recent_events(limit=2100)
        assert [row.event_id for row in saved] == [f"e{i:05}" for i in range(max(size, 1))]
        assert [row.payload for row in saved] == [{"index": i} for i in range(max(size, 1))]
    finally:
        database.close()


@pytest.mark.parametrize("failure", ["serialization", "sql"])
def test_later_statement_failure_rolls_back_the_entire_batch(tmp_path, failure):
    database = Database(tmp_path / "rollback.sqlite3")
    rows = [event(i) for i in range(130)]
    try:
        database.append_event(event(1000))
        if failure == "serialization":
            rows[-1].payload["invalid"] = object()
            expected = TypeError
        else:
            database._conn.execute(
                "CREATE TRIGGER fail_late BEFORE INSERT ON market_events "
                "WHEN NEW.event_id='e00129' BEGIN SELECT RAISE(ABORT,'injected failure'); END"
            )
            expected = sqlite3.IntegrityError
        with pytest.raises(expected):
            database.append_events(rows)
        assert [row.event_id for row in database.recent_events()] == ["e01000"]
        assert not database._conn.in_transaction
        assert database._conn.execute("PRAGMA synchronous").fetchone()[0] == 2
    finally:
        database.close()


def test_duplicate_with_different_payload_keeps_first_committed_value(tmp_path):
    database = Database(tmp_path / "duplicates.sqlite3")
    first = event(0)
    duplicate = first.model_copy(update={"payload": {"index": "later"}})
    try:
        rows = [first, *[event(i) for i in range(1, 80)], duplicate]
        assert len(database.append_events(rows)) == 80
        assert next(
            row for row in database.recent_events() if row.event_id == first.event_id
        ).payload == {"index": 0}
    finally:
        database.close()
