"""Boundary audits for the additive lookup and frozen coverage report."""

import sqlite3
from datetime import UTC, datetime

import pytest
from signal_arcade.database import Database
from signal_arcade.intelligence.learning import _entry_family_proof_gates
from signal_arcade.models import ChallengerSkill, RiskMode
from test_order_evidence_lookup import order, policy
from test_participation_progression import record_policy
from test_v1104_training_history import training_fixture


@pytest.mark.parametrize(
    "percent,usable", [(70, 699), (70, 700), (70, 701), (55, 549), (55, 550), (55, 551)]
)
def test_fitted_report_uses_filtered_tail_and_exact_coverage_gate(settings, percent, usable):
    learner, database, _ = training_fixture(settings, count=1030)
    try:
        if percent != 70:
            learner.set_coverage_policy(percent, 0)
        for index in range(1030):
            item = learner.observations[f"row-{index}"]
            if index < 1008 - usable:
                checkpoint = item.checkpoints["300"]
                checkpoint.net_return = None
                checkpoint.missing_reason = "executable_exit_quote_unavailable"
                checkpoint.route_snapshot = {
                    "quote_failure_reason": (
                        "fees exceed sell proceeds"
                        if index < 8
                        else "sell output exceeds real quote reserves"
                    )
                }
            if 1008 <= index < 1012:
                item.risk_mode = RiskMode.AGGRESSIVE
            elif 1012 <= index < 1016:
                item.configuration_fingerprint = "different"
            elif 1016 <= index < 1020:
                item.features.pop("opportunity")
            elif 1020 <= index < 1024:
                item.source_mode = "demo"
            elif 1024 <= index < 1028:
                item.checkpoints["600"] = item.checkpoints.pop("300").model_copy(
                    update={"horizon_seconds": 600}
                )
            elif index >= 1028:
                record_policy(learner, item.mint, item.created_at)
                assert learner._observation_has_policy_twin(item)
        job = learner.prepare_next_training()
        assert job is not None
        learner.fit_training_job(job)
        assert learner.finish_training_job(job)
        artifacts = [
            a
            for a in database.list_challenger_artifacts()
            if a.skill in (ChallengerSkill.ENTRY, ChallengerSkill.MANIPULATION)
        ]
        assert len(artifacts) == 3
        for artifact in artifacts:
            assert artifact.sample_count == usable
            assert artifact.metrics["coverage_resolved"] == 1000
            assert artifact.metrics["coverage_usable"] == usable
            assert artifact.metrics["coverage_quote_liquidity"] == 1000 - usable
            # The eight oldest eligible rows fall outside the fixed window. Excluded
            # recent cohorts, incomplete features and Policy twins cannot displace it.
            assert artifact.metrics["coverage_quote_fees"] == 0
            assert artifact.metrics["outcome_availability"] == usable / 1000
            if artifact.skill == ChallengerSkill.ENTRY:
                gates = {g["id"]: g for g in _entry_family_proof_gates(artifact)}
                assert gates["entry_outcome_availability"]["state"] == (
                    "passed" if usable >= percent * 10 else "not_met"
                )
                assert gates["entry_outcome_availability"]["target"] == percent / 100
                assert not artifact.qualified  # Coverage cannot replace independent Policy proof.
    finally:
        database.close()


def test_busy_order_write_rolls_back_then_retries_with_measurement_enabled(tmp_path):
    from signal_arcade.work_timing import WORK_DETAIL

    database = Database(tmp_path / "busy.sqlite3")
    now = datetime.now(UTC)
    episode = policy(now, "one")
    database.save_learning_evidence_episode(episode)
    database._conn.execute("PRAGMA busy_timeout=1")
    other = sqlite3.connect(database.path)
    detail = {}
    token = WORK_DETAIL.set(detail)
    try:
        other.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            database.save_order(order(now))
        assert database.list_orders() == []
        assert database.list_learning_evidence_episodes() == [episode]
        other.rollback()
        database.save_order(order(now))
        assert database.learning_evidence_for_decision("shared").order_id == "order"
        assert detail["order_save"][0] == detail["order_lock"][0] == 2
        assert detail["order_lookup"][0] == 1
    finally:
        WORK_DETAIL.reset(token)
        other.close()
        database.close()


@pytest.mark.parametrize("decision", ["quoted'\"$.decision_id", "é\x00nested", ""])
def test_index_tracks_updated_json_without_stale_decision_matches(tmp_path, decision):
    database = Database(tmp_path / "updated.sqlite3")
    now = datetime.now(UTC)
    try:
        episode = policy(now, "one")
        database.save_learning_evidence_episode(episode)
        changed = episode.model_copy(update={"decision_id": decision})
        database.save_learning_evidence_episode(changed)
        assert database.learning_evidence_for_decision("shared") is None
        assert database.learning_evidence_for_decision(decision) == changed
        database.save_order(order(now, decision))
        expected = "order" if decision else None
        assert database.learning_evidence_for_decision(decision).order_id == expected
        assert database._conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        database.close()


def test_denied_index_creation_preserves_records_and_retries_cleanly(tmp_path, monkeypatch):
    path = tmp_path / "migration.sqlite3"
    database = Database(path)
    episode = policy(datetime.now(UTC), "one")
    database.save_learning_evidence_episode(episode)
    database.set_setting("challenger_consent_granted", True)
    database._conn.execute("DROP INDEX idx_learning_evidence_decision")
    database.close()
    connect = sqlite3.connect
    opened = []

    def protected_connect(*args, **kwargs):
        connection = connect(*args, **kwargs)
        opened.append(connection)
        connection.set_authorizer(
            lambda action, name, *_: (
                sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_CREATE_INDEX
                and name == "idx_learning_evidence_decision"
                else sqlite3.SQLITE_OK
            )
        )
        return connection

    monkeypatch.setattr(sqlite3, "connect", protected_connect)
    try:
        with pytest.raises(sqlite3.DatabaseError, match="authorized"):
            Database(path)
    finally:
        monkeypatch.undo()
        for connection in opened:
            connection.close()
    with connect(path) as check:
        assert check.execute("PRAGMA user_version").fetchone()[0] == 16
        assert (
            check.execute("SELECT record_json FROM learning_evidence_episodes").fetchone()[0]
            == episode.model_dump_json()
        )
        assert (
            check.execute(
                "SELECT 1 FROM sqlite_master WHERE name='idx_learning_evidence_decision'"
            ).fetchone()
            is None
        )
    database = Database(path)
    try:
        assert database.get_setting("challenger_consent_granted") is True
        assert database.list_learning_evidence_episodes() == [episode]
        assert database._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='idx_learning_evidence_decision'"
        ).fetchone()
    finally:
        database.close()
