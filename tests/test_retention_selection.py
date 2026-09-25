"""Budget deletion preserves an exact total order despite ties and concurrent arrivals."""

import random

import pytest
from signal_arcade.database import Database


def insert_rows(database, rows):
    with database._conn:
        database._conn.executemany(
            "INSERT INTO market_events VALUES "
            "(?, 'fixture', ?, 'mint', NULL, NULL, NULL, ?, 1, '{}')",
            rows,
        )


def trade_ids(database):
    return [
        row[0]
        for row in database._conn.execute(
            "SELECT event_id FROM market_events WHERE kind='trade' ORDER BY received_at,event_id"
        )
    ]


@pytest.mark.parametrize("preserve", [0, 1, 17, 60, 90])
@pytest.mark.parametrize("tie_size", [1, 3, 17, 60])
def test_exact_budget_cohort_after_late_insert_and_restart(tmp_path, preserve, tie_size):
    path = tmp_path / "total-order.sqlite3"
    database = Database(path)
    rows = [(f"event-{i:03}", "trade", f"{i // tie_size:03}") for i in range(60)]
    random.Random(472).shuffle(rows)  # noqa: S311 -- deterministic insertion order
    insert_rows(database, [*rows, ("protected", "create", "000")])
    try:
        for arrival in [None, ("late", "trade", "000"), ("newest", "trade", "999")]:
            if arrival is not None:
                insert_rows(database, [arrival])
            before = trade_ids(database)
            to_remove = before[: min(7, max(0, len(before) - preserve))]
            result = database.enforce_storage_budget(
                1,
                preserve_recent_events=preserve,
                max_rows_per_pass=7,
                max_rows_per_chunk=7,
                max_duration_seconds=10,
            )
            assert result["raw_trades"] == len(to_remove)
            assert trade_ids(database) == before[len(to_remove) :]
            assert database._conn.execute(
                "SELECT 1 FROM market_events WHERE event_id='protected'"
            ).fetchone()
            database.close()
            database = Database(path)
    finally:
        database.close()


def test_old_chunk_does_not_repeat_retained_cohort_count(tmp_path, monkeypatch):
    database = Database(tmp_path / "vm-work.sqlite3")
    insert_rows(database, [(f"e{i:05}", "trade", f"{i // 5:05}") for i in range(30_000)])
    original = database._retention_transaction
    measured = []

    def transaction(query, parameters, deadline, stop_requested):
        # Count VM work separately from the production cooperative deadline handler.
        # Roll back the measurement; the real transaction still uses that handler.
        callbacks = []
        database._conn.set_progress_handler(lambda: callbacks.append(1) or 0, 500)
        try:
            database._conn.execute("BEGIN")
            removed = database._conn.execute(query, parameters).rowcount
        finally:
            database._conn.set_progress_handler(None, 0)
            database._conn.rollback()
        measured.append((removed, len(callbacks) * 500))
        return original(query, parameters, deadline, stop_requested)

    monkeypatch.setattr(database, "_retention_transaction", transaction)
    try:
        result = database.enforce_storage_budget(
            1, max_rows_per_pass=50, max_rows_per_chunk=50, max_duration_seconds=10
        )
        assert result["raw_trades"] == 50
        assert len(measured) == 1 and measured[0][0] == 50
        # The prior duplicate selection used >120k VM steps; allow broad version margin.
        assert measured[0][1] < 90_000
    finally:
        database.close()
