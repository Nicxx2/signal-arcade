"""Sparse dashboard lanes must not scan the burst-sized decision journal."""

from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.models import Decision, DecisionAction, DecisionScore, FeatureSnapshot, RiskMode


def decision(index, action, *, at=None):
    return Decision(
        decision_id=f"row-{index}",
        mint=f"mint-{index}",
        symbol="TEST",
        created_at=at or datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=index),
        action=action,
        risk_mode=RiskMode.BALANCED,
        reasons=[],
        blockers=[],
        score=DecisionScore(
            opportunity=0, danger=0, execution=0, confidence=0, net_edge_index=0, composite=0
        ),
        feature_snapshot=FeatureSnapshot(
            mint=f"mint-{index}",
            symbol="TEST",
            name="Test",
            venue="pump_curve",
            values={},
            data_confidence=0,
        ),
    )


def populate(database, count=2000, *, dense=False):
    rows = [
        decision(
            i,
            DecisionAction.ENTER
            if i < 3
            else DecisionAction.WATCH
            if dense
            else DecisionAction.PASS,
        )
        for i in range(count)
    ]
    with database._lock, database._conn:
        database._conn.executemany(
            "INSERT INTO decisions VALUES(?,?,?,?,?)",
            [
                (
                    r.decision_id,
                    r.mint,
                    r.action.value,
                    r.created_at.isoformat(),
                    r.model_dump_json(),
                )
                for r in rows
            ],
        )


def index_names(database):
    return [
        row[1]
        for row in database._conn.execute("PRAGMA index_list(decisions)")
        if row[1].startswith("idx_decisions_action_time_")
    ]


@pytest.mark.parametrize("dense", [False, True])
def test_sparse_lane_is_bounded_and_preserves_the_original_result(tmp_path, dense):
    database = Database(tmp_path / "journal.sqlite3")
    try:
        populate(database, dense=dense)
        expected = database._reader_conn.execute(
            "SELECT record_json FROM decisions WHERE action IN ('enter','watch') "
            "ORDER BY created_at DESC,rowid ASC LIMIT 50"
        ).fetchall()
        instructions = 0

        def step():
            nonlocal instructions
            instructions += 1
            return 0

        database._reader_conn.set_progress_handler(step, 1)
        try:
            actual = database.list_decisions_by_actions(("enter", "watch"), 50)
        finally:
            database._reader_conn.set_progress_handler(None, 0)
        assert [row.model_dump_json() for row in actual] == [row[0] for row in expected]
        # Work follows the lane limit, not all 1,997 later decisions, positive or negative.
        assert instructions < (5000 if dense else 1000)
    finally:
        database.close()


@pytest.mark.parametrize(
    "actions", [("watch", "enter"), ("enter", "enter", "watch"), ("watch",), (), ("' OR 1=1 --",)]
)
@pytest.mark.parametrize("limit", [0, 1, 5, 50])
def test_lane_merge_matches_history_including_timestamp_ties(tmp_path, actions, limit):
    database = Database(tmp_path / "ties.sqlite3")
    try:
        at = datetime(2026, 1, 1, tzinfo=UTC)
        for i in range(18):
            database.save_decision(decision(i, list(DecisionAction)[i % 4], at=at))
        selected = set(actions)
        expected = [row for row in database.list_decisions(100) if row.action in selected][:limit]
        assert database.list_decisions_by_actions(actions, limit) == expected
        assert database.list_decisions_by_actions(actions, -1) == []
    finally:
        database.close()


def test_index_survives_rotation_reopen_and_rollback(tmp_path):
    path = tmp_path / "rotation.sqlite3"
    database = Database(path)
    try:
        populate(database, 5)
        original = index_names(database)
        assert len(original) == 1
        with pytest.raises(RuntimeError), database._lock, database._conn:
            database._clear_paper_tables()
            assert index_names(database) != original
            raise RuntimeError("rollback")
        assert index_names(database) == original
        assert len(database.list_decisions_by_actions(("enter",), 50)) == 3
        with database._lock, database._conn:
            database._clear_paper_tables()
        rotated = index_names(database)
        assert len(rotated) == 1 and rotated != original
        assert database.list_decisions_by_actions(("enter",), 50) == []
    finally:
        database.close()
    database = Database(path)
    try:
        assert index_names(database) == rotated
        database.save_decision(decision(20, DecisionAction.WATCH))
        assert [r.decision_id for r in database.list_decisions_by_actions(("watch",))] == ["row-20"]
        # Simulate an existing schema-16 install that has never had this optional index.
        with database._conn:
            database._conn.execute(f"DROP INDEX {rotated[0]}")  # noqa: S608 - generated index
    finally:
        database.close()
    database = Database(path)
    try:
        assert len(index_names(database)) == 1
        assert database.list_decisions_by_actions(("watch",))[0].decision_id == "row-20"
    finally:
        database.close()


def test_inflight_history_read_keeps_one_season_when_writer_rotates(tmp_path):
    database = Database(tmp_path / "overlap.sqlite3")
    try:
        populate(database, 5)
        old = database.list_decisions_by_actions(("enter", "watch"))
        # Pin a WAL reader snapshot before a separate writer rotates the season.
        # All action lanes must remain in that snapshot; the next read sees the new one.
        with database._reader_lock:
            database._reader_conn.execute("BEGIN")
            try:
                assert database.list_decisions_by_actions(("enter", "watch")) == old
                with database._lock, database._conn:
                    database._clear_paper_tables()
                fresh = decision(20, DecisionAction.WATCH)
                database.save_decision(fresh)
                assert database.list_decisions_by_actions(("enter", "watch")) == old
            finally:
                database._reader_conn.execute("ROLLBACK")
        assert database.list_decisions_by_actions(("enter", "watch")) == [fresh]
    finally:
        database.close()
