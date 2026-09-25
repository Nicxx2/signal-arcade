"""Order/evidence linkage must survive lookup optimization and failed writes."""

import sqlite3
import time
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.models import LearningEvidenceLane, PaperOrder, Side
from test_database import execution_episode


def policy(now, identity, *, decision="shared", lane=LearningEvidenceLane.POLICY):
    return execution_episode(now, episode_id=identity).model_copy(
        update={
            "lane": lane,
            "trajectory_key": identity,
            "idempotency_key": identity,
            "decision_id": decision,
        }
    )


def order(now, decision="shared"):
    return PaperOrder(
        order_id="order",
        decision_id=decision,
        mint="mint",
        symbol="M",
        side=Side.BUY,
        requested_sol_lamports=100,
        created_at=now,
        fill_after=now,
    )


@pytest.mark.parametrize("decision", [None, "", "absent", "shared"])
def test_order_updates_and_missing_links_survive_restart(tmp_path, decision):
    path = tmp_path / "orders.sqlite3"
    db = Database(path)
    now = datetime.now(UTC)
    original = policy(now, "one")
    db.save_learning_evidence_episode(original)
    pending = order(now, decision)
    try:
        db.save_order(pending)
        db.save_order(pending)
        assert db.list_orders() == [pending]
    finally:
        db.close()
    db = Database(path)
    try:
        expected = (
            original.model_copy(update={"order_id": "order"}) if decision == "shared" else original
        )
        assert db.list_learning_evidence_episodes() == [expected]
        assert db.list_orders() == [pending]
    finally:
        db.close()


def test_duplicate_decisions_preserve_writer_and_chronological_reader_selection(tmp_path):
    db = Database(tmp_path / "duplicates.sqlite3")
    now = datetime.now(UTC)
    try:
        # Writer's existing trajectory-index order differs from the chronological reader.
        for row in (
            policy(now, "z-earliest"),
            policy(now + timedelta(seconds=1), "a-later"),
            policy(now - timedelta(seconds=1), "0-other-lane", lane=LearningEvidenceLane.EXECUTION),
        ):
            db.save_learning_evidence_episode(row)
        db.save_order(order(now))
        linked = [
            r.episode_id for r in db.list_learning_evidence_episodes() if r.order_id == "order"
        ]
        assert linked == ["a-later"]
        assert db.learning_evidence_for_decision("shared").episode_id == "z-earliest"
        assert db.learning_evidence_for_decision("absent") is None
    finally:
        db.close()


@pytest.mark.parametrize("failure", ["link", "commit"])
def test_order_and_link_rollback_together_and_retry(tmp_path, monkeypatch, failure):
    db = Database(tmp_path / "atomic.sqlite3")
    now = datetime.now(UTC)
    original = policy(now, "one")
    db.save_learning_evidence_episode(original)
    connection = db._conn
    try:
        if failure == "link":
            connection.execute(
                "CREATE TEMP TRIGGER deny_link BEFORE UPDATE ON learning_evidence_episodes "
                "BEGIN SELECT RAISE(ABORT, 'link failed'); END"
            )
        else:

            class FailCommit:
                def __enter__(self):
                    return connection.__enter__()

                def __exit__(self, *_args):
                    connection.rollback()
                    raise sqlite3.OperationalError("commit failed")

                def execute(self, *args):
                    return connection.execute(*args)

            monkeypatch.setattr(db, "_conn", FailCommit())
        with pytest.raises(sqlite3.Error):
            db.save_order(order(now))
        assert db.list_orders() == []
        assert db.list_learning_evidence_episodes() == [original]
        monkeypatch.undo()
        connection.execute("DROP TRIGGER IF EXISTS deny_link")
        db.save_order(order(now))
        assert db.list_learning_evidence_episodes()[0].order_id == "order"
    finally:
        monkeypatch.undo()
        db.close()


def test_upgrade_index_bounds_lookup_work_without_rewriting_evidence(tmp_path):
    path = tmp_path / "large-history.sqlite3"
    db = Database(path)
    now = datetime.now(UTC)
    rows = []
    for i in range(5000):
        record = policy(now, f"trajectory-{i:05}", decision=f"decision-{i}")
        record.features = {f"feature-{n}": 0.5 for n in range(64)}
        rows.append(
            (
                record.episode_id,
                record.idempotency_key,
                record.lane.value,
                record.trajectory_key,
                record.mint,
                record.created_at.isoformat(),
                record.status.value,
                record.model_dump_json(),
            )
        )
    db._conn.executemany("INSERT INTO learning_evidence_episodes VALUES(?,?,?,?,?,?,?,?)", rows)
    db._conn.commit()
    db._conn.execute("DROP INDEX idx_learning_evidence_decision")
    query = (
        "SELECT record_json FROM learning_evidence_episodes WHERE lane='policy' "
        "AND json_extract(record_json,'$.decision_id')=? ORDER BY trajectory_key LIMIT 1"
    )

    def measured(connection, decision):
        calls = []
        connection.set_progress_handler(lambda: calls.append(1) or 0, 100)
        try:
            started = time.perf_counter()
            result = connection.execute(query, (decision,)).fetchone()
            return result[0] if result else None, len(calls) * 100, time.perf_counter() - started
        finally:
            connection.set_progress_handler(None, 0)

    before = {key: measured(db._conn, key) for key in ("decision-4999", "absent")}
    db.close()
    started = time.perf_counter()
    db = Database(path)
    upgrade_seconds = time.perf_counter() - started
    try:
        after = {key: measured(db._conn, key) for key in before}
        for key in before:
            assert before[key][0] == after[key][0]
            assert before[key][1] > 10000
            assert after[key][1] < 500
        assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 16
        assert [
            tuple(r)
            for r in db._conn.execute(
                "SELECT * FROM learning_evidence_episodes ORDER BY episode_id"
            )
        ] == rows
        print(
            {
                "upgrade_seconds": upgrade_seconds,
                "before": {k: v[1:] for k, v in before.items()},
                "after": {k: v[1:] for k, v in after.items()},
            }
        )
    finally:
        db.close()


def test_equal_time_reader_ties_keep_insertion_order_after_index(tmp_path):
    db = Database(tmp_path / "equal-time.sqlite3")
    now = datetime.now(UTC)
    try:
        for name in ("z-first", "a-second"):
            db.save_learning_evidence_episode(policy(now, name))
        assert db.learning_evidence_for_decision("shared").episode_id == "z-first"
        db.save_order(order(now))
        assert [
            r.episode_id for r in db.list_learning_evidence_episodes() if r.order_id == "order"
        ] == ["a-second"]
    finally:
        db.close()


def test_execution_fill_duplicates_keep_preceding_index_order_across_restart(tmp_path):
    path = tmp_path / "fill-duplicates.sqlite3"
    db = Database(path)
    now = datetime.now(UTC)
    try:
        for identity, decision, seconds in (
            ("z-first", "z", -10),
            ("a-first", None, 2),
            ("a-second", None, 2),
            ("a-earlier", "a", -20),
        ):
            row = policy(
                now + timedelta(seconds=seconds),
                identity,
                decision=decision,
                lane=LearningEvidenceLane.EXECUTION,
            )
            db.save_learning_evidence_episode(row)
        db.save_learning_evidence_episode(policy(now - timedelta(days=1), "other-lane"))
        legacy = db._reader_conn.execute(
            "SELECT record_json FROM learning_evidence_episodes "
            "INDEXED BY idx_learning_evidence_decision WHERE lane='execution' "
            "AND json_extract(record_json,'$.entry_fill_id')=? LIMIT 1",
            ("entry-fill",),
        ).fetchone()[0]
        assert db.execution_evidence_for_entry_fill("entry-fill").model_dump_json() == legacy
        assert db.execution_evidence_for_entry_fill("entry-fill").episode_id == "a-first"
        assert db.execution_evidence_for_entry_fill("missing") is None
        # The preceding image has no ORDER BY. Its natural traversal through the new
        # index must also preserve the winner if that image is used for rollback.
        assert (
            db._reader_conn.execute(
                "SELECT record_json FROM learning_evidence_episodes WHERE lane='execution' "
                "AND json_extract(record_json,'$.entry_fill_id')=? LIMIT 1",
                ("entry-fill",),
            ).fetchone()[0]
            == legacy
        )
    finally:
        db.close()
    db = Database(path)
    try:
        assert db.execution_evidence_for_entry_fill("entry-fill").model_dump_json() == legacy
        assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 16
    finally:
        db.close()


def test_actual_broker_readers_bound_work_for_first_last_and_missing_references(tmp_path):
    db = Database(tmp_path / "reader-cost.sqlite3")
    now = datetime.now(UTC)
    try:
        rows = []
        for lane in LearningEvidenceLane:
            for index in range(1500):
                record = policy(
                    now + timedelta(seconds=index),
                    f"{lane.value}-{index}",
                    decision=f"decision-{index}",
                    lane=lane,
                ).model_copy(update={"entry_fill_id": f"fill-{index}"})
                record.features = {f"feature-{n}": 0.5 for n in range(64)}
                rows.append(
                    (
                        record.episode_id,
                        record.idempotency_key,
                        record.lane.value,
                        record.trajectory_key,
                        record.mint,
                        record.created_at.isoformat(),
                        record.status.value,
                        record.model_dump_json(),
                    )
                )
        with db._conn:
            db._conn.executemany(
                "INSERT INTO learning_evidence_episodes VALUES(?,?,?,?,?,?,?,?)",
                rows,
            )
        # Reopen the preceding schema-16 layout with populated execution evidence.
        # The upgrade adds an access path without rewriting saved receipts.
        db._conn.execute("DROP INDEX idx_execution_evidence_entry_fill")
        path = db.path
        db.close()
        db = Database(path)
        assert [
            tuple(row)
            for row in db._reader_conn.execute(
                "SELECT * FROM learning_evidence_episodes ORDER BY rowid"
            )
        ] == rows
        for reader, prefix, lane in (
            (db.learning_evidence_for_decision, "decision", "policy"),
            (db.execution_evidence_for_entry_fill, "fill", "execution"),
        ):
            for index in (0, 1499, 2000):
                steps = []
                db._reader_conn.set_progress_handler(lambda steps=steps: steps.append(1) or 0, 100)
                try:
                    found = reader(f"{prefix}-{index}")
                finally:
                    db._reader_conn.set_progress_handler(None, 0)
                # Includes first-use statement/schema preparation as well as the lookup.
                assert len(steps) * 100 < 1000
                if index == 2000:
                    assert found is None
                else:
                    assert found.episode_id == f"{lane}-{index}"
    finally:
        db.close()
