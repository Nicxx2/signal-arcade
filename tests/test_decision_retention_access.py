"""Exact retained cohorts and age ties survive the non-entry access-path change."""

import random
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database


def insert(db, key, at, action="pass"):
    db._conn.execute(
        "INSERT INTO decisions(decision_id,mint,action,created_at,record_json) VALUES(?,?,?,?,?)",
        (key, "m", action, at, "{}"),
    )


def current(db):
    return [
        row[0]
        for row in db._conn.execute(
            "SELECT decision_id FROM decisions WHERE action!='enter' "
            "ORDER BY created_at,decision_id"
        )
    ]


@pytest.mark.parametrize("preserve", [0, 1, 7, 59, 60, 90])
@pytest.mark.parametrize("ties", [1, 8, 60])
def test_budget_exact_rows_with_late_arrivals_and_restart(tmp_path, preserve, ties):
    path = tmp_path / "decisions.sqlite3"
    db = Database(path)
    rows = list(range(60))
    random.Random(721).shuffle(rows)  # noqa: S311 -- deterministic insertion order
    with db._conn:
        for i in rows:
            insert(db, f"d{i:03}", f"{i // ties:03}", ("pass", "watch", "abstain")[i % 3])
        insert(db, "protected", "000", "enter")
    try:
        for arrival in (None, ("late", "000"), ("new", "999")):
            if arrival:
                with db._conn:
                    insert(db, *arrival)
            before = current(db)
            expected = min(7, max(0, len(before) - preserve))
            result = db.enforce_storage_budget(
                1,
                preserve_recent_non_entry_decisions=preserve,
                max_rows_per_pass=7,
                max_rows_per_chunk=7,
                max_duration_seconds=10,
            )
            assert result["non_entry_decisions"] == expected
            assert current(db) == before[expected:]
            assert db._conn.execute(
                "SELECT 1 FROM decisions WHERE decision_id='protected'"
            ).fetchone()
            db.close()
            db = Database(path)
    finally:
        db.close()


def test_age_ties_match_previous_descending_timestamp_access(tmp_path):
    db = Database(tmp_path / "ties.sqlite3")
    now = datetime.now(UTC)
    try:
        with db._conn:
            for i in range(40):
                insert(db, f"d{(i * 7) % 41:03}", (now - timedelta(days=2)).isoformat())
            insert(db, "protected", (now - timedelta(days=3)).isoformat(), "enter")
        # The original descending timestamp index scans rowid DESC within ASC time ties.
        reference = [
            row[0]
            for row in db._conn.execute(
                "SELECT decision_id FROM decisions INDEXED BY idx_decisions_created "
                "WHERE action!='enter' AND created_at<? ORDER BY created_at ASC LIMIT 7",
                (now.isoformat(),),
            )
        ]
        before = set(current(db))
        db.prune_history(now, non_entry_decision_before=now, max_rows_per_category=7)
        assert before - set(current(db)) == set(reference)
    finally:
        db.close()


def index_names(db):
    return [
        row[1]
        for row in db._conn.execute("PRAGMA index_list(decisions)")
        if row[1].startswith("idx_decisions_nonentry_time_")
    ]


def test_additive_index_upgrade_rotation_and_rollback(tmp_path):
    path = tmp_path / "upgrade.sqlite3"
    db = Database(path)
    name = index_names(db)[0]
    db._conn.execute(f'DROP INDEX "{name}"')  # noqa: S608 -- database-generated identifier
    db.close()
    db = Database(path)
    try:
        assert len(index_names(db)) == 1
        assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 16
        original_name = index_names(db)[0]
        with db._conn:
            insert(db, "original", "000")
        with pytest.raises(RuntimeError, match="rollback"), db._conn:
            db._clear_paper_tables()
            assert len(index_names(db)) == 1
            raise RuntimeError("rollback")
        assert index_names(db) == [original_name]
        assert current(db) == ["original"]
        with db._conn:
            db._clear_paper_tables()
        assert len(index_names(db)) == 1 and index_names(db)[0] != original_name
        assert db.retired_decision_tables()
        db.close()
        db = Database(path)
        assert len(index_names(db)) == 1
        assert not current(db)
    finally:
        db.close()


def test_interrupted_budget_does_not_commit_or_advance_a_watermark(tmp_path):
    db = Database(tmp_path / "interrupted.sqlite3")
    try:
        with db._conn:
            for i in range(100):
                insert(db, str(i), "000")
        before = current(db)
        result = db.enforce_storage_budget(1, stop_requested=lambda: True)
        assert result["non_entry_decisions"] == 0
        assert current(db) == before
        assert not db._conn.in_transaction
        result = db.enforce_storage_budget(
            1,
            preserve_recent_non_entry_decisions=7,
            max_rows_per_pass=10,
            max_rows_per_chunk=10,
            max_duration_seconds=10,
        )
        assert result["non_entry_decisions"] == 10
        assert current(db) == before[10:]
    finally:
        db.close()
