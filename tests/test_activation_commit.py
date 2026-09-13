"""Authority must not become visible before its complete durable commit."""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.intelligence.learning import LearningEngine
from signal_arcade.models import ChallengerSkill, LearningMode
from test_participation_progression import (  # noqa: F401
    activate_first,
    native_champion,
    progression,
    record_policy,
)


@pytest.mark.parametrize("failure", ["skill", "settings"])
def test_failed_upstream_join_preserves_authority_until_retry(progression, monkeypatch, failure):  # noqa: F811
    learner, database, settings = progression
    previous = activate_first(learner, ChallengerSkill.EXIT)
    candidate = native_champion(learner, ChallengerSkill.SIZING, datetime.now(UTC))
    for index in range(30):
        record_policy(learner, f"join-{index}", candidate.created_at + timedelta(seconds=index + 1))
    assert learner._skill_join_evidence(candidate, independent=True)["ready"]
    before = dict(learner.active_skill_versions)
    before_mode = learner.mode

    def reject(*args, **kwargs):
        raise RuntimeError("injected authority failure")

    with monkeypatch.context() as scoped:
        scoped.setattr(
            database,
            "save_challenger_skill_state" if failure == "skill" else "_upsert_settings",
            reject,
        )
        with pytest.raises(RuntimeError, match="injected authority failure"):
            learner._activate_skill(candidate)
    assert learner.active_skill_versions == before
    assert learner.mode == before_mode
    assert learner._current_skill_state(ChallengerSkill.EXIT).active_version == previous.version
    assert learner._current_skill_state(ChallengerSkill.SIZING).active_version is None
    assert database.get_setting("active_challenger_skills") == before
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    assert restarted.active_skill_versions == before
    restarted._activate_skill(candidate)
    assert restarted.active_skill_versions == {"sizing": candidate.version}
    assert database.get_setting("active_challenger_skills") == restarted.active_skill_versions
    assert database.get_setting("learning_mode") == restarted.mode.value


def test_failed_manual_activation_does_not_grant_consent(progression, monkeypatch):  # noqa: F811
    learner, database, _ = progression
    candidate = activate_first(learner, ChallengerSkill.EXIT)
    learner.set_participation(False)
    learner.consent_granted = False
    database.set_setting("challenger_consent_granted", False)
    monkeypatch.setattr(learner, "_skill_activation_candidate", lambda: candidate)

    def reject(rows, now):
        raise RuntimeError("injected manual commit failure")

    with monkeypatch.context() as scoped:
        scoped.setattr(database, "_upsert_settings", reject)
        with pytest.raises(RuntimeError, match="manual commit"):
            learner.set_mode(LearningMode.ACTIVE)
    assert learner.mode == LearningMode.SHADOW
    assert not learner.active_skill_versions
    assert not learner.consent_granted
    assert database.get_setting("challenger_consent_granted") is False
    learner.set_mode(LearningMode.ACTIVE)
    assert learner.consent_granted
    assert database.get_setting("challenger_consent_granted") is True
    assert database.get_setting("learning_mode") == LearningMode.ACTIVE.value


def test_failed_suspension_removes_all_affected_authority_and_retries(progression, monkeypatch):  # noqa: F811
    learner, database, _ = progression
    activate_first(learner, ChallengerSkill.EXIT)
    candidate = native_champion(learner, ChallengerSkill.SIZING, datetime.now(UTC))
    for index in range(30):
        record_policy(learner, f"join-{index}", candidate.created_at + timedelta(seconds=index + 1))
    learner._govern_skill_ensemble()
    for index in range(30):
        record_policy(
            learner, f"rejoin-{index}", candidate.created_at + timedelta(minutes=2, seconds=index)
        )
    learner._govern_skill_ensemble()
    assert set(learner.active_skill_versions) == {"sizing", "exit"}

    def reject(*args, **kwargs):
        raise RuntimeError("injected suspension failure")

    with monkeypatch.context() as scoped:
        scoped.setattr(database, "save_challenger_skill_state", reject)
        with pytest.raises(RuntimeError, match="suspension failure"):
            learner._suspend_skill(ChallengerSkill.SIZING, "degraded")
        assert not learner.active_skill_versions
        assert learner.mode == LearningMode.SHADOW
        assert learner._current_skill_state(ChallengerSkill.EXIT).active_version is None
        with pytest.raises(RuntimeError, match="suspension failure"):
            learner._activate_skill(candidate)
    learner._persist_revoked_authority()
    assert database.get_setting("active_challenger_skills") == {}
    assert database.get_setting("learning_mode") == LearningMode.SHADOW.value
    assert not learner._pending_authority_states


def test_sqlite_commit_failure_does_not_publish_an_upstream_join(progression):  # noqa: F811
    learner, database, settings = progression
    previous = activate_first(learner, ChallengerSkill.EXIT)
    candidate = native_champion(learner, ChallengerSkill.SIZING, datetime.now(UTC))
    for index in range(30):
        record_policy(
            learner, f"commit-{index}", candidate.created_at + timedelta(seconds=index + 1)
        )
    before = dict(learner.active_skill_versions)

    def deny_commit(action, operation, *args):
        return (
            sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_TRANSACTION and operation == "COMMIT"
            else sqlite3.SQLITE_OK
        )

    database._conn.set_authorizer(deny_commit)
    try:
        with pytest.raises(sqlite3.DatabaseError):
            learner._activate_skill(candidate)
    finally:
        database._conn.set_authorizer(None)
    assert not database._conn.in_transaction
    assert learner.active_skill_versions == before
    assert learner._current_skill_state(ChallengerSkill.EXIT).active_version == previous.version
    assert database.get_setting("active_challenger_skills") == before
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    assert restarted.active_skill_versions == before
    restarted._activate_skill(candidate)
    assert restarted.active_skill_versions == {"sizing": candidate.version}
