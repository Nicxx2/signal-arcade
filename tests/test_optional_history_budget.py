"""Optional housekeeping must yield without deleting unresolved evidence."""

import sqlite3
import time

import pytest
from signal_arcade.database import Database


@pytest.fixture
def database(tmp_path):
    value = Database(tmp_path / "optional.sqlite3")
    yield value
    value.close()


def seed(database, category, count, *, ties=False):
    with database._conn:
        for index in range(count):
            at = f"2026-01-01T00:00:{index:06d}" if not ties else "2026-01-01"
            resolved = None if index % 7 == 0 else at
            if category == "incidents":
                database._conn.execute(
                    "INSERT INTO operational_incidents VALUES(?,?,?,?,?,?,?,?,?)",
                    (str(index), "fixture", "warning", "fixture", at, at, 1, resolved, "{}"),
                )
            else:
                database._conn.execute(
                    "INSERT INTO ai_critic_assessments VALUES(?,?,?,?,?,?)",
                    (str(index), "fixture", at, 1, resolved, "{}"),
                )


def rows(database, category):
    query = (
        "SELECT * FROM operational_incidents ORDER BY 1"
        if category == "incidents"
        else "SELECT * FROM ai_critic_assessments ORDER BY 1"
    )
    return [tuple(row) for row in database._conn.execute(query)]


@pytest.mark.parametrize("category", ["incidents", "ai_assessments"])
@pytest.mark.parametrize("count,ties", [(0, False), (20, False), (6500, False), (6500, True)])
def test_bounded_selection_matches_existing_callers(database, tmp_path, category, count, ties):
    seed(database, category, count, ties=ties)
    before = rows(database, category)
    legacy = Database(tmp_path / "legacy.sqlite3")
    try:
        legacy._conn.execute("DROP INDEX IF EXISTS idx_incidents_resolved_seen")
        seed(legacy, category, count, ties=ties)
        method = legacy.prune_incidents if category == "incidents" else legacy.prune_ai_assessments
        expected = method(max_rows=50)
        timing = {}
        result = database.prune_optional_history(
            category, max_rows=50, max_duration_seconds=1, timing=timing
        )
        assert result == {
            "removed": expected,
            "completed": 1,
            "deferred": 0,
            "work_remaining": int(expected == 50),
        }
        retained = rows(database, category)
        assert retained == rows(legacy, category)
        resolved_index = 7 if category == "incidents" else 4
        assert {row for row in before if row[resolved_index] is None} <= set(retained)
        assert timing["completed_queries"] == 1
        assert not database._conn.in_transaction
    finally:
        legacy.close()


@pytest.mark.parametrize("category", ["incidents", "ai_assessments"])
@pytest.mark.parametrize("case", ["expired", "cancelled", "external_writer"])
def test_deferred_is_not_empty_or_completed(database, category, case):
    seed(database, category, 6500)
    before = rows(database, category)
    other = sqlite3.connect(database.path)
    statements = []
    try:
        database._conn.execute("PRAGMA busy_timeout=1200")
        database._conn.set_trace_callback(statements.append)
        if case == "external_writer":
            other.execute("BEGIN IMMEDIATE")
        start = time.monotonic()
        result = database.prune_optional_history(
            category,
            deadline=start - 1 if case == "expired" else start + 0.05,
            stop_requested=lambda: case == "cancelled",
        )
        assert time.monotonic() - start < 0.6
        assert result == {"removed": 0, "completed": 0, "deferred": 1, "work_remaining": 1}
        if case != "external_writer":
            assert not statements
        assert rows(database, category) == before
        assert database._conn.execute("PRAGMA busy_timeout").fetchone()[0] == 1200
        assert not database._conn.in_transaction
        other.rollback()
        database.set_setting("ordinary-write", True)
        assert database.get_setting("ordinary-write") is True
    finally:
        other.close()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("parameter", ["deadline", "max_duration_seconds"])
def test_invalid_bounds_rejected_before_sql(database, value, parameter):
    statements = []
    database._conn.set_trace_callback(statements.append)
    with pytest.raises(ValueError):
        database.prune_optional_history("incidents", **{parameter: value})
    assert not statements


@pytest.mark.parametrize("category", ["incidents", "ai_assessments"])
def test_representative_history_progresses_under_production_budget(database, category):
    seed(database, category, 25_000)
    before = rows(database, category)
    removed = 0
    for _ in range(5):
        result = database.prune_optional_history(category)
        removed += result["removed"]
    assert removed > 0, "bounded queries must make progress, not only time out safely"
    assert len(rows(database, category)) == len(before) - removed
    assert not database._conn.in_transaction


def test_incident_retention_index_avoids_sort_and_reopens_safely(database):
    seed(database, "incidents", 2500)
    before = rows(database, "incidents")
    plan = database._conn.execute(
        "EXPLAIN QUERY PLAN SELECT incident_id FROM operational_incidents "
        "WHERE resolved_at IS NOT NULL ORDER BY last_seen_at DESC LIMIT ? OFFSET ?",
        (50, 2000),
    ).fetchall()
    details = " ".join(row[3] for row in plan)
    assert "idx_incidents_resolved_seen" in details and "TEMP B-TREE" not in details
    path = database.path
    reopened = Database(path)
    try:
        assert rows(reopened, "incidents") == before
        assert reopened._conn.execute("PRAGMA user_version").fetchone()[0] == 16
    finally:
        reopened.close()
