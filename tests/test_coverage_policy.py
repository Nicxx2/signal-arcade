"""Coverage policy transitions must never manufacture evidence or permission."""

from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.intelligence.coverage_policy import (
    SETTING_KEY,
    CoveragePolicy,
    artifact_minimum,
    meets_current,
    read_policy,
    saved_minimum,
)
from signal_arcade.intelligence.learning import LearningEngine, _skill_qualification_gates
from signal_arcade.models import ChallengerSkill
from test_participation_progression import activate_first, progression  # noqa: F401
from test_v1104_training_history import training_fixture


@pytest.mark.parametrize("percent", [70, 65, 60, 55])
def test_policy_round_trip_and_legacy_default(percent):
    policy = CoveragePolicy(percent, 3, datetime.now(UTC))
    assert read_policy(policy.record()) == policy
    assert read_policy({}) == CoveragePolicy()
    assert CoveragePolicy().metadata() == {}
    assert saved_minimum({}) == 0.70


def test_fifty_five_requires_versioned_proof_and_old_reader_fails_closed(monkeypatch):
    from signal_arcade.intelligence import coverage_policy

    at = datetime.now(UTC)
    record = CoveragePolicy(55, 1, at).record()
    assert saved_minimum(record) == 0.55
    with pytest.raises(ValueError, match="legacy"):
        read_policy(CoveragePolicy(55).record())
    # Emulate the preceding reader's allowed values; never reinterpret 55 as 60/70.
    monkeypatch.setattr(coverage_policy, "PERCENTAGES", (70, 65, 60))
    assert saved_minimum(record) == float("inf")
    assert saved_minimum(CoveragePolicy(60, 2, at).record()) == 0.60


@pytest.mark.parametrize("invalid", [True, False, 0, 20, 54, 56, 64, 71, 55.0, "55", None])
def test_setting_rejects_invalid_values_without_writes(progression, invalid):  # noqa: F811
    learner, database, _ = progression
    before = learner.coverage_settings_status()
    with pytest.raises(ValueError):
        learner.set_coverage_policy(invalid, 0)
    assert learner.coverage_settings_status() == before
    assert database.get_setting(SETTING_KEY) is None


@pytest.mark.parametrize("percent", [55, 65])
def test_noop_conflict_restart_and_evidence_identity(progression, percent):  # noqa: F811
    learner, database, settings = progression
    fingerprint = learner.configuration_fingerprint()
    learner.set_coverage_policy(70, 0)
    assert database.get_setting(SETTING_KEY) is None
    learner.set_coverage_policy(percent, 0)
    saved = learner.coverage_policy
    learner.set_coverage_policy(percent, 1)
    assert learner.coverage_policy == saved
    with pytest.raises(ValueError, match="refresh"):
        learner.set_coverage_policy(60, 0)
    restarted = LearningEngine(database, settings, configuration_fingerprint=lambda: fingerprint)
    assert restarted.coverage_policy == saved
    assert restarted.configuration_fingerprint() == fingerprint
    assert not restarted.consent_granted and not restarted.auto_participation


@pytest.mark.parametrize("percent", [55, 65])
def test_failed_save_keeps_memory_database_and_authority(progression, monkeypatch, percent):  # noqa: F811
    learner, database, _ = progression
    artifact = activate_first(learner, ChallengerSkill.SIZING)
    before = learner.coverage_settings_status()
    state_before = learner._current_skill_state(artifact.skill).model_dump()

    def fail(*args, **kwargs):
        raise RuntimeError("simulated storage failure")

    monkeypatch.setattr(database, "_upsert_settings", fail)
    with pytest.raises(RuntimeError, match="storage failure"):
        learner.set_coverage_policy(percent, 0)
    assert learner.coverage_settings_status() == before
    assert database.get_setting(SETTING_KEY) is None
    assert learner._current_skill_state(artifact.skill).model_dump() == state_before
    assert learner.active_skill_versions == {"sizing": artifact.version}


@pytest.mark.parametrize("percent", [55, 60])
def test_lower_setting_preserves_active_and_saved_proof(progression, percent):  # noqa: F811
    learner, _, _ = progression
    artifact = activate_first(learner, ChallengerSkill.SIZING)
    frozen = artifact.model_dump()
    learner.set_coverage_policy(percent, 0)
    assert artifact.model_dump() == frozen
    assert learner._coverage_minimum(artifact) == 0.70
    assert learner.active_skill_versions == {"sizing": artifact.version}
    assert learner.consent_granted and learner.auto_participation
    coverage_gate = next(
        g
        for g in _skill_qualification_gates(artifact.skill, artifact)
        if g["id"].endswith("outcome_availability")
    )
    assert coverage_gate["target"] == 0.70


@pytest.mark.parametrize("percent", [55, 65])
def test_policy_change_fences_training_including_aba(settings, percent):
    learner, database, _ = training_fixture(settings, count=100)
    job = learner.prepare_next_training()
    assert job is not None
    learner.set_coverage_policy(percent, 0)
    learner.set_coverage_policy(70, 1)
    assert learner.training_job_stale(job, ())
    assert job.workspace.coverage_policy == CoveragePolicy()
    assert not learner.finish_training_job(job)
    database.close()


@pytest.mark.parametrize("invalid", [{}, "65", {"coverage_minimum_percent": 65}])
def test_corrupt_persisted_policy_is_visible_and_repairable(settings, invalid):
    database = Database(settings.database_path)
    database.set_setting(SETTING_KEY, invalid)
    learner = LearningEngine(database, settings)
    assert learner.coverage_policy_error
    assert learner.coverage_policy.percent == 70
    learner.set_coverage_policy(70, 0)
    assert learner.coverage_policy_error is None
    assert read_policy(database.get_setting(SETTING_KEY)).percent == 70
    database.close()


@pytest.mark.parametrize("percent", [55, 65])
def test_fresh_validation_is_required_after_user_change(percent):
    at = datetime.now(UTC)
    policy = CoveragePolicy(percent, 1, at)
    assert not policy.fresh(None)
    assert not policy.fresh(at - timedelta(microseconds=1))
    assert policy.fresh(at)
    assert policy.fresh(at + timedelta(microseconds=1))


@pytest.mark.parametrize(
    "percent,coverage,expected",
    [(65, 0.649, False), (65, 0.65, True), (70, 0.699, False), (70, 0.7, True)],
)
def test_stricter_current_requirement_checks_real_metrics(progression, percent, coverage, expected):  # noqa: F811
    learner, _, _ = progression
    old = activate_first(learner, ChallengerSkill.SIZING)
    candidate = old.model_copy(
        deep=True,
        update={
            "hyperparameters": CoveragePolicy(60, 1, datetime.now(UTC)).metadata(),
            "metrics": {"outcome_availability": coverage},
        },
    )
    assert artifact_minimum(candidate) == 0.60
    assert meets_current(candidate, percent / 100) is expected
    assert candidate.qualified
