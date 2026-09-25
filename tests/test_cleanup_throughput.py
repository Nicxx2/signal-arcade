"""Retention progress must preserve exact recent cohorts and fair category budgets."""

# ruff: noqa: F811 -- shared pytest fixture

import random
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.models import EventKind, MarketEvent
from test_probe_retention import engine  # noqa: F401


def test_slow_equity_does_not_shrink_fast_raw_or_budget_lane(engine):
    engine._storage_history_chunk_rows = dict.fromkeys(engine._storage_history_chunk_rows, 20)
    engine._adapt_storage_history_chunks(
        {
            "raw_trades_query_seconds": 0.003,
            "raw_trades_completed_queries": 1,
            "equity_points_query_seconds": 0.06,
            "equity_points_query_budget_seconds": 0.047,
            "equity_points_query_budget_exhausted": 1,
        },
        {"raw_trades": 20, "equity_points": 0, "work_remaining": 1},
    )
    assert engine._storage_history_chunk_rows == {
        "raw_trades": 25,
        "non_entry_decisions": 20,
        "equity_points": 10,
    }
    assert engine._storage_maintenance_chunk_rows == 50


@pytest.mark.parametrize(
    "measurement",
    [
        {"query_seconds": 0.04, "query_budget_seconds": 0.002, "query_budget_exhausted": 1},
        {"query_seconds": 0.06, "query_busy": 1},
        {"query_seconds": float("nan"), "completed_queries": 1},
        {"query_seconds": -1, "completed_queries": 1},
        {"query_seconds": None, "completed_queries": 1},
        {"query_seconds": "unknown", "completed_queries": 1},
        {"lock_timeouts": 1},
        {},
    ],
)
def test_deferral_or_bad_measurement_does_not_tune_a_category(engine, measurement):
    engine._storage_history_chunk_rows["raw_trades"] = 20
    engine._adapt_storage_history_chunks(
        {f"raw_trades_{key}": value for key, value in measurement.items()}, {"raw_trades": 20}
    )
    assert engine._storage_history_chunk_rows["raw_trades"] == 20


@pytest.mark.parametrize("preserve", [0, 1, 3, 20, 40])
@pytest.mark.parametrize("all_tied", [True, False])
def test_budget_preserves_exact_newest_cohort_across_chunks(tmp_path, preserve, all_tied):
    database = Database(tmp_path / "cohort.sqlite3")
    now = datetime.now(UTC)
    events = [
        MarketEvent(
            event_id=f"id-{i:02d}",
            source="test",
            kind=EventKind.TRADE,
            mint="mint",
            received_at=now + timedelta(seconds=0 if all_tied else i // 3),
        )
        for i in range(20)
    ]
    random.Random(41).shuffle(events)  # noqa: S311 -- deterministic order regression
    protected = MarketEvent(
        event_id="create",
        source="test",
        kind=EventKind.CREATE,
        mint="mint",
        received_at=now - timedelta(days=2),
    )
    database.append_events([protected, *events])
    database.set_setting("protected-state", {"cash": 100})
    try:
        result = database.enforce_storage_budget(
            1,
            preserve_recent_events=preserve,
            max_rows_per_chunk=2,
            max_duration_seconds=5,
        )
        ordered = sorted(events, key=lambda e: (e.received_at, e.event_id))
        expected = ordered[-preserve:] if preserve else []
        assert result["raw_trades"] == len(events) - len(expected)
        assert {e.event_id for e in database.recent_events()} == {
            protected.event_id,
            *(e.event_id for e in expected),
        }
        assert database.get_setting("protected-state") == {"cash": 100}
    finally:
        database.close()


def test_budget_rotation_services_decisions_during_raw_backlog(tmp_path):
    database = Database(tmp_path / "fair.sqlite3")
    now = datetime.now(UTC).isoformat()
    with database._conn:
        database._conn.executemany(
            "INSERT INTO decisions VALUES (?, 'mint', ?, ?, '{}')",
            [(f"d{i}", "pass", now) for i in range(20)] + [("protected", "enter", now)],
        )
        database._conn.executemany(
            "INSERT INTO market_events VALUES "
            "(?, 'test', 'trade', 'mint', NULL, NULL, NULL, ?, 1, '{}')",
            [(f"r{i}", now) for i in range(20)],
        )
    try:
        result = database.enforce_storage_budget(
            1,
            preserve_recent_events=3,
            preserve_recent_non_entry_decisions=3,
            max_rows_per_pass=2,
            max_rows_per_chunk=2,
            category_offset=1,
        )
        assert result["non_entry_decisions"] == 2 and result["raw_trades"] == 0
        assert database._conn.execute(
            "SELECT 1 FROM decisions WHERE decision_id='protected'"
        ).fetchone()
    finally:
        database.close()


@pytest.mark.parametrize(
    "limits",
    [
        {"unknown": 1},
        {"raw_trades": 0},
        {"raw_trades": 51},
        {"equity_points": True},
        {"non_entry_decisions": 1.5},
    ],
)
def test_category_limits_reject_invalid_values_before_deletion(tmp_path, limits):
    database = Database(tmp_path / "limits.sqlite3")
    try:
        with pytest.raises(ValueError, match="category rows"):
            database.prune_history(
                datetime.now(UTC), max_rows_per_category=50, category_rows=limits
            )
    finally:
        database.close()


def test_category_row_limits_bound_each_query(tmp_path):
    database = Database(tmp_path / "rows.sqlite3")
    now = datetime.now(UTC)
    database.append_events(
        [
            MarketEvent(
                event_id=f"r{i}", source="test", kind=EventKind.TRADE, mint="m", received_at=now
            )
            for i in range(8)
        ]
    )
    for i in range(8):
        database.record_equity(i, i)
    try:
        result = database.prune_history(
            now + timedelta(seconds=1),
            max_rows_per_category=50,
            max_equity_points=1,
            category_rows={"raw_trades": 6, "equity_points": 1},
        )
        assert result["raw_trades"] == 6 and result["equity_points"] == 1
    finally:
        database.close()
