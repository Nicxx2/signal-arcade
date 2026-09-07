from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.models import AiCriticAssessment, LearningEvidenceLane, LearningEvidenceStatus
from test_database import execution_episode

INDEXES = (
    "idx_ai_assessments_created",
    "idx_learning_evidence_retention",
    "idx_learning_evidence_trajectory",
)


def seed_ai(db):
    now = datetime.now(UTC)
    for i in range(35):
        db.save_ai_assessment(
            AiCriticAssessment(
                assessment_id=f"assessment-{i}",
                decision_id=f"decision-{i}",
                mint=f"mint-{i}",
                symbol="TEST",
                created_at=now + timedelta(seconds=i // 3),
                snapshot_at=now,
                mode="shadow",
                model_name="fixture",
                model_digest="digest",
                prompt_version="v1",
                schema_version="v1",
                input_sha256="fixture",
                latency_ms=10,
                valid=i % 3 != 0,
                baseline_action="enter",
                resolved_at=now if i % 2 else None,
                outcome_missing_reason="unknown" if i % 4 == 0 else None,
            )
        )


@pytest.mark.parametrize("limit", [0, 1, 7, 35, 5000])
def test_ai_index_upgrade_keeps_full_cohort_and_tied_order(tmp_path, limit):
    path = tmp_path / "old.sqlite3"
    db = Database(path)
    seed_ai(db)
    for name in INDEXES:
        db._conn.execute(f"DROP INDEX {name}")
    db._conn.commit()
    old = [
        AiCriticAssessment.model_validate_json(row[0])
        for row in db._conn.execute(
            "SELECT record_json FROM ai_critic_assessments ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
    ]
    db.set_setting("preserved-marker", {"unchanged": True})
    db.close()
    upgraded = Database(path)
    try:
        assert upgraded.list_ai_assessments(limit) == old
        assert upgraded.get_setting("preserved-marker") == {"unchanged": True}
        assert upgraded._conn.execute("PRAGMA user_version").fetchone()[0] == 15
        plan = [
            row[3]
            for row in upgraded._conn.execute(
                "EXPLAIN QUERY PLAN SELECT record_json FROM ai_critic_assessments "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        ]
        assert any("idx_ai_assessments_created" in step for step in plan)
        assert not any("TEMP B-TREE" in step for step in plan)
    finally:
        upgraded.close()


def test_ai_history_does_not_own_core_locks(tmp_path):
    db = Database(tmp_path / "locks.sqlite3")
    try:
        seed_ai(db)
        with ThreadPoolExecutor(max_workers=1) as worker, db._lock, db._reader_lock:
            assert len(worker.submit(db.list_ai_assessments, 5000).result(timeout=2)) == 35
    finally:
        db.close()


def test_retention_index_keeps_pending_and_exact_old_terminal_selection(tmp_path):
    db = Database(tmp_path / "retention.sqlite3")
    now = datetime.now(UTC)
    try:
        for lane in LearningEvidenceLane:
            for i in range(24):
                row = execution_episode(
                    now + timedelta(seconds=i // 4), episode_id=f"{lane.value}-{i}"
                )
                row.lane = lane
                row.status = [
                    LearningEvidenceStatus.PENDING,
                    LearningEvidenceStatus.COMPLETE,
                    LearningEvidenceStatus.UNAVAILABLE,
                    LearningEvidenceStatus.CANCELLED,
                ][i % 4]
                db.save_learning_evidence_episode(row)
        db._conn.execute("DROP INDEX idx_learning_evidence_retention")
        expected = []
        for lane in ("policy", "execution"):
            expected.extend(
                row[0]
                for row in db._conn.execute(
                    "SELECT episode_id FROM learning_evidence_episodes "
                    "INDEXED BY idx_learning_evidence_lane_time "
                    "WHERE lane=? AND status IN ('complete','unavailable','cancelled') "
                    "ORDER BY created_at DESC LIMIT -1 OFFSET 5",
                    (lane,),
                )
            )
        before = {r.episode_id: r for r in db.list_learning_evidence_episodes()}
        db._migrate()
        plan = [
            row[3]
            for row in db._conn.execute(
                "EXPLAIN QUERY PLAN SELECT episode_id FROM learning_evidence_episodes "
                "INDEXED BY idx_learning_evidence_retention "
                "WHERE lane=? AND status IN (?,?,?) "
                "ORDER BY created_at DESC,rowid DESC LIMIT -1 OFFSET ?",
                ("policy", "complete", "unavailable", "cancelled", 5),
            )
        ]
        assert any("COVERING INDEX idx_learning_evidence_retention" in step for step in plan)
        assert db.prune_learning_evidence(5) == expected
        assert {r.episode_id: r for r in db.list_learning_evidence_episodes()} == {
            key: value for key, value in before.items() if key not in expected
        }
        assert db.prune_learning_evidence(5) == []
    finally:
        db.close()


def test_index_upgrade_is_idempotent_and_newer_schema_is_untouched(tmp_path):
    path = tmp_path / "migration.sqlite3"
    db = Database(path)
    db._migrate()
    names = {
        row[0] for row in db._conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
    }
    assert set(INDEXES) <= names
    db._conn.execute("DROP INDEX idx_ai_assessments_created")
    db._conn.execute("PRAGMA user_version=999")
    db._conn.commit()
    db.close()
    with pytest.raises(RuntimeError, match="newer"):
        Database(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 999
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='idx_ai_assessments_created'"
            ).fetchone()
            is None
        )


def test_additive_index_failure_rolls_back_partial_index_work(tmp_path):
    path = tmp_path / "index-failure.sqlite3"
    db = Database(path)
    db.set_setting("marker", "retained")
    for name in INDEXES:
        db._conn.execute(f"DROP INDEX {name}")
    db._conn.execute("CREATE TABLE idx_learning_evidence_retention (value TEXT)")
    db._conn.commit()
    db.close()
    with pytest.raises(sqlite3.OperationalError, match="already a table"):
        Database(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 15
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='idx_ai_assessments_created'"
            ).fetchone()
            is None
        )
        assert (
            connection.execute("SELECT value_json FROM settings WHERE key='marker'").fetchone()[0]
            == '"retained"'
        )
