"""Exercise configurable coverage against real receipts; fitted qualification is a fixture."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.intelligence.coverage_policy import artifact_minimum, saved_minimum
from signal_arcade.intelligence.learning import (
    CHALLENGER_SKILL_SCHEMA_VERSION,
    FEATURE_SCHEMA_VERSION,
    MANIPULATION_FEATURE_NAMES,
    SIZING_FEATURE_NAMES,
    LearningEngine,
    _challenger_cohort_key,
)
from signal_arcade.models import ChallengerSkill, ChallengerSkillArtifact
from signal_arcade.strategy import BASELINE_VERSION
from test_coach_lifecycle import coach_lifecycle, crowned_coach  # noqa: F401
from test_learning import _supported_coach_hypothesis, qualified_model
from test_participation_progression import progression, record_policy  # noqa: F401


def candidate(learner, skill, name="candidate", *, fresh=True, prediction=-0.2, coverage=0.65):
    at = datetime.now(UTC) + timedelta(seconds=1)
    cutoff = at if fresh else at - timedelta(days=1)
    if skill == ChallengerSkill.ENTRY:
        model = qualified_model(name, prediction, 80).model_copy(
            update={
                "created_at": at,
                "training_cutoff_at": cutoff,
                "configuration_fingerprint": learner.configuration_fingerprint(),
            }
        )
        learner._publish_entry_artifact(
            model,
            baseline_version=BASELINE_VERSION,
            evidence_started_at=cutoff,
            evidence_ended_at=at,
        )
        return learner.skill_artifacts[f"challenger-skill-v2-entry-{model.version}"]
    names = (
        SIZING_FEATURE_NAMES
        if skill == ChallengerSkill.SIZING
        else (MANIPULATION_FEATURE_NAMES if skill == ChallengerSkill.MANIPULATION else ())
    )
    artifact = ChallengerSkillArtifact(
        version=name,
        schema_version=CHALLENGER_SKILL_SCHEMA_VERSION,
        skill=skill,
        created_at=at,
        training_cutoff_at=cutoff,
        risk_mode=learner.current_risk_mode,
        configuration_fingerprint=learner.configuration_fingerprint(),
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        feature_names=list(names),
        qualified=True,
        metrics={
            "outcome_availability": coverage,
            "policy_outcome_availability": coverage,
            "validation_availability_fraction": coverage,
        },
        parameters={"selected_horizon_seconds": 300, "baseline_horizon_seconds": 600}
        if skill == ChallengerSkill.EXIT
        else {
            "means": [0.0] * len(names),
            "scales": [1.0] * len(names),
            "coefficients": [
                0.5 if skill == ChallengerSkill.SIZING else prediction,
                *([0.0] * len(names)),
            ],
        },
    )
    cohort = _challenger_cohort_key(
        artifact.risk_mode,
        artifact.configuration_fingerprint,
        artifact.baseline_version,
        artifact.feature_schema_version,
    )
    learner._register_skill_artifact(artifact, cohort)
    return artifact


def evidence(learner, artifact, *, usable, count=60, prefix="proof"):
    for index in range(count):
        episode = record_policy(
            learner, f"{prefix}-{index}", artifact.created_at + timedelta(minutes=10, seconds=index)
        )
        if index >= usable:
            for checkpoint in episode.checkpoints.values():
                checkpoint.net_return = None
                checkpoint.exit_value_lamports = None
            for trial in episode.size_trials.values():
                for checkpoint in trial.checkpoints.values():
                    checkpoint.exit_value_lamports = None
            learner.database.save_learning_evidence_episode(episode)


@pytest.mark.parametrize("skill", list(ChallengerSkill))
@pytest.mark.parametrize("percent", [55, 60, 65, 70])
def test_all_skills_use_selected_requirement_and_keep_absolute_samples(progression, skill, percent):  # noqa: F811
    learner, _, _ = progression
    if percent != 70:
        learner.set_coverage_policy(percent, 0)
    artifact = candidate(learner, skill)
    assert artifact_minimum(artifact) == percent / 100
    # Entry additionally needs its operational sample minimum of 80.
    count = 100 if skill == ChallengerSkill.ENTRY else 60
    usable = count * percent // 100
    evidence(learner, artifact, usable=usable, count=count)
    if skill == ChallengerSkill.ENTRY:
        assert learner._entry_coverage_ready(artifact)
    else:
        proof = learner._skill_join_evidence(artifact, independent=True)
        assert proof["ready"] and proof["observed_count"] == count
        assert proof["minimum_availability_fraction"] == percent / 100
    learner.set_participation(True)
    assert learner.active_skill_versions == {skill.value: artifact.version}


@pytest.mark.parametrize("skill", list(ChallengerSkill))
@pytest.mark.parametrize("percent", [55, 65])
def test_prechange_validation_does_not_gain_a_first_crown(progression, skill, percent):  # noqa: F811
    learner, _, _ = progression
    learner.set_coverage_policy(percent, 0)
    artifact = candidate(learner, skill, fresh=False)
    assert not artifact.qualified
    assert not learner._current_skill_state(skill).champion_version
    assert artifact.hyperparameters["coverage_fresh_validation"] is False


def test_raise_revokes_insufficient_champion_atomically_and_lower_does_not_revive(progression):  # noqa: F811
    learner, database, settings = progression
    learner.set_coverage_policy(65, 0)
    artifact = candidate(learner, ChallengerSkill.SIZING)
    evidence(learner, artifact, usable=39)
    learner.set_participation(True)
    frozen = artifact.model_dump()
    assert learner.active_skill_versions
    learner.set_coverage_policy(70, 1)
    assert not learner.active_skill_versions
    assert (
        learner._current_skill_state(artifact.skill).suspension_reason == "coverage_policy_changed"
    )
    learner.set_coverage_policy(60, 2)
    learner._govern_skill_ensemble()
    assert not learner.active_skill_versions
    assert learner.skill_artifacts[artifact.version].model_dump() == frozen
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    assert not restarted.active_skill_versions
    assert restarted.auto_participation and restarted.consent_granted


def test_native_battle_freezes_requirement_and_raise_closes_without_retry(progression):  # noqa: F811
    learner, database, settings = progression
    candidate(learner, ChallengerSkill.ENTRY, "old-champion", prediction=0.2)
    learner.set_coverage_policy(65, 0)
    contender = candidate(learner, ChallengerSkill.ENTRY, "new-contender")
    state = learner._current_skill_state(ChallengerSkill.ENTRY)
    assert state.testing_version == contender.version
    assert saved_minimum(state.last_tournament) == 0.65
    learner.set_coverage_policy(60, 1)
    assert saved_minimum(state.last_tournament) == 0.65
    learner.set_coverage_policy(70, 2)
    state = learner._current_skill_state(ChallengerSkill.ENTRY)
    assert state.testing_version is None
    assert state.last_tournament["result"] == "coverage_policy_changed"
    learner.set_coverage_policy(65, 3)
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    assert restarted._current_skill_state(ChallengerSkill.ENTRY).testing_version is None


def test_failed_recovery_keeps_its_fixed_rows_after_setting_toggle(progression):  # noqa: F811
    learner, _, _ = progression
    learner.set_coverage_policy(65, 0)
    artifact = candidate(learner, ChallengerSkill.SIZING)
    evidence(learner, artifact, usable=60)
    learner.set_participation(True)
    learner._suspend_skill(artifact.skill, "unverifiable")
    # Move beyond the previously created receipts and suspension boundary.
    later = artifact.model_copy(update={"created_at": artifact.created_at + timedelta(hours=1)})
    evidence(learner, later, usable=0, prefix="recovery")
    learner._govern_skill_ensemble()
    state = learner._current_skill_state(artifact.skill)
    recovery = state.activation_proof["recovery"]
    assert recovery["status"] == "failed"
    original = recovery.copy()
    learner.set_coverage_policy(60, 1)
    learner.set_coverage_policy(65, 2)
    learner._govern_skill_ensemble()
    assert learner._current_skill_state(artifact.skill).activation_proof["recovery"] == original
    assert not learner.active_skill_versions


@pytest.mark.parametrize("percent", [55, 60, 65, 70])
@pytest.mark.parametrize("skill", list(ChallengerSkill))
def test_one_missing_outcome_below_requirement_still_blocks(progression, percent, skill):  # noqa: F811
    learner, _, _ = progression
    if percent != 70:
        learner.set_coverage_policy(percent, 0)
    artifact = candidate(learner, skill)
    count = 100 if skill == ChallengerSkill.ENTRY else 60
    evidence(learner, artifact, usable=count * percent // 100 - 1, count=count)
    if skill == ChallengerSkill.ENTRY:
        assert not learner._entry_coverage_ready(artifact)
    else:
        assert not learner._skill_join_evidence(artifact, independent=True)["ready"]
    learner.set_participation(True)
    assert not learner.active_skill_versions


@pytest.mark.parametrize("percent", [55, 60])
def test_lower_coverage_does_not_lower_sample_minimum(progression, percent):  # noqa: F811
    learner, _, _ = progression
    learner.set_coverage_policy(percent, 0)
    artifact = candidate(learner, ChallengerSkill.SIZING)
    evidence(learner, artifact, usable=29, count=29)
    proof = learner._skill_join_evidence(artifact, independent=True)
    assert proof["availability_fraction"] == 1 and not proof["ready"]


@pytest.mark.parametrize("offset,state", [(-1, "unverifiable"), (0, "healthy")])
@pytest.mark.parametrize("percent", [55, 65])
@pytest.mark.parametrize("skill", list(ChallengerSkill))
def test_health_uses_new_artifact_rule_without_reclassifying_missing_rows(
    progression,  # noqa: F811
    offset,
    state,
    percent,
    skill,
):
    learner, _, _ = progression
    learner.set_coverage_policy(percent, 0)
    artifact = candidate(learner, skill)
    evidence(learner, artifact, usable=100, count=100)
    learner.set_participation(True)
    assert learner.active_skill_versions == {skill.value: artifact.version}
    later = artifact.model_copy(update={"created_at": artifact.created_at + timedelta(hours=1)})
    usable = 60 * percent // 100 + offset
    evidence(learner, later, usable=usable, prefix="health")
    health = learner._skill_health(artifact.skill, artifact.version)
    assert health["state"] == state
    assert health["observed_count"] == 60 and health["usable_count"] == usable
    assert health["minimum_availability_fraction"] == percent / 100


def test_raising_closes_collecting_recovery_without_discarding_rows(progression):  # noqa: F811
    learner, _, _ = progression
    learner.set_coverage_policy(65, 0)
    artifact = candidate(learner, ChallengerSkill.SIZING)
    evidence(learner, artifact, usable=60)
    learner.set_participation(True)
    learner._suspend_skill(artifact.skill, "unverifiable")
    later = artifact.model_copy(update={"created_at": artifact.created_at + timedelta(hours=1)})
    evidence(learner, later, usable=5, count=5, prefix="recovery")
    rows = learner._current_skill_state(artifact.skill).activation_proof["recovery"]["rows"]
    learner.set_coverage_policy(70, 1)
    learner.set_coverage_policy(65, 2)
    recovery = learner._current_skill_state(artifact.skill).activation_proof["recovery"]
    assert recovery["rows"] == rows and recovery["status"] == "policy_changed"
    assert not learner._skill_recovery_proof(learner._current_skill_state(artifact.skill))["ready"]


def test_failed_raise_does_not_partially_revoke_authority(progression, monkeypatch):  # noqa: F811
    learner, database, settings = progression
    learner.set_coverage_policy(65, 0)
    artifact = candidate(learner, ChallengerSkill.SIZING)
    evidence(learner, artifact, usable=39)
    learner.set_participation(True)
    original = learner._current_skill_state(artifact.skill).model_dump()
    with monkeypatch.context() as patch:

        def fail(*args, **kwargs):
            raise RuntimeError("disk full simulation")

        patch.setattr(database, "_upsert_settings", fail)
        with pytest.raises(RuntimeError, match="disk full"):
            learner.set_coverage_policy(70, 1)
    assert learner.coverage_policy.percent == 65
    assert learner._current_skill_state(artifact.skill).model_dump() == original
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    assert restarted.active_skill_versions == {"sizing": artifact.version}
    assert restarted.coverage_policy.percent == 65


@pytest.mark.parametrize("percent", [55, 60])
def test_coach_champion_keeps_70_and_mixed_battle_is_shared_70(coach_lifecycle, percent):  # noqa: F811
    learner, _, _ = coach_lifecycle
    version = crowned_coach(learner, ChallengerSkill.ENTRY)
    learner.set_coverage_policy(percent, 0)
    coach = learner.skill_artifacts[version]
    assert learner._coverage_minimum(coach) == 0.70
    contender = candidate(learner, ChallengerSkill.ENTRY, "native-versus-coach")
    state = learner._current_skill_state(ChallengerSkill.ENTRY)
    assert state.testing_version == contender.version
    assert saved_minimum(state.last_tournament) == 0.70
    assert state._battle_replay["minimum_coverage"] == 0.70


@pytest.mark.parametrize("percent", [55, 60])
def test_low_coverage_battle_still_exhausts_original_observed_budget(
    progression,  # noqa: F811
    monkeypatch,
    percent,
):
    learner, _, _ = progression
    candidate(learner, ChallengerSkill.ENTRY, "champion", prediction=0.2)
    learner.set_coverage_policy(percent, 0)
    contender = candidate(learner, ChallengerSkill.ENTRY, "challenger")
    with monkeypatch.context() as patch:
        patch.setattr(learner, "_advance_entry_tournaments", lambda: None)
        evidence(learner, contender, usable=0, count=172)
    learner._advance_entry_tournaments()
    state = learner._current_skill_state(ChallengerSkill.ENTRY)
    assert state.testing_version is None
    assert state.last_tournament["result"] == "inconclusive"
    assert state.last_tournament["maximum_common_observed"] == 172
    assert state.last_tournament["common_observed_count"] == 172
    assert state.last_tournament["common_usable_count"] == 0


def test_stricter_current_gate_does_not_rewrite_saved_artifact_checks(progression):  # noqa: F811
    learner, _, _ = progression
    learner.set_coverage_policy(65, 0)
    artifact = candidate(learner, ChallengerSkill.SIZING)
    learner.set_coverage_policy(70, 1)
    report = next(s for s in learner.skill_statuses() if s["skill"] == "sizing")
    assert report["latest_candidate"]["minimum_outcome_coverage"] == 0.65
    assert report["gates"][-1]["id"] == "sizing_current_coverage_policy"
    assert report["gates"][-1]["state"] == "not_met"
    assert artifact.qualified


def test_new_battle_excludes_observations_before_its_own_start(progression):  # noqa: F811
    learner, _, _ = progression
    candidate(learner, ChallengerSkill.ENTRY, "champion", prediction=0.2)
    learner.set_coverage_policy(65, 0)
    contender = candidate(learner, ChallengerSkill.ENTRY, "challenger")
    state = learner._current_skill_state(ChallengerSkill.ENTRY)
    boundary = contender.created_at + timedelta(minutes=10)
    state.last_tournament["coverage_effective_at"] = boundary.isoformat()
    record_policy(learner, "before-start", boundary - timedelta(microseconds=1))
    learner._advance_entry_tournaments()
    assert state.last_tournament["common_observed_count"] == 0
    record_policy(learner, "at-start", boundary)
    learner._advance_entry_tournaments()
    assert state.last_tournament["common_observed_count"] == 1


def test_corrupt_recovery_requirement_cannot_publish_infinite_threshold(progression):  # noqa: F811
    learner, _, _ = progression
    learner.set_coverage_policy(65, 0)
    artifact = candidate(learner, ChallengerSkill.SIZING)
    evidence(learner, artifact, usable=60)
    learner.set_participation(True)
    learner._suspend_skill(artifact.skill, "unverifiable")
    later = artifact.model_copy(update={"created_at": artifact.created_at + timedelta(hours=1)})
    evidence(learner, later, usable=5, count=5, prefix="recovery")
    state = learner._current_skill_state(artifact.skill)
    recovery = state.activation_proof["recovery"]
    recovery["coverage_minimum_percent"] = "invalid"
    original = json.dumps(recovery, sort_keys=True)
    assert learner._skill_recovery_proof(state) == {"ready": False}
    assert json.dumps(recovery, sort_keys=True, allow_nan=False) == original
    assert learner.skill_suspension_summary(state)["minimum_availability_fraction"] is None


@pytest.mark.parametrize("skill", list(ChallengerSkill))
@pytest.mark.parametrize("percent", [55, 65])
def test_stricter_activation_contract_survives_lowering_health_and_recovery(
    progression,  # noqa: F811
    skill,
    percent,
):
    learner, database, settings = progression
    learner.set_coverage_policy(percent, 0)
    artifact = candidate(learner, skill, coverage=0.8)
    learner.set_coverage_policy(70, 1)
    evidence(learner, artifact, usable=100, count=100)
    learner.set_participation(True)
    state = learner._current_skill_state(artifact.skill)
    assert learner.active_skill_versions == {skill.value: artifact.version}
    assert saved_minimum(state.activation_proof) == 0.70
    learner.set_coverage_policy(percent, 2)
    later = artifact.model_copy(update={"created_at": artifact.created_at + timedelta(hours=1)})
    evidence(learner, later, usable=39, prefix="health")
    health = learner._skill_health(artifact.skill, artifact.version)
    assert health["minimum_availability_fraction"] == 0.70
    assert health["state"] == "unverifiable"
    learner._govern_skill_ensemble()
    assert not learner.active_skill_versions
    later = artifact.model_copy(update={"created_at": artifact.created_at + timedelta(hours=2)})
    evidence(learner, later, usable=39, prefix="recovery")
    learner._govern_skill_ensemble()
    state = learner._current_skill_state(artifact.skill)
    assert saved_minimum(state.activation_proof["recovery"]) == 0.70
    assert state.activation_proof["recovery"]["status"] == "failed"
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    assert not restarted.active_skill_versions
    assert saved_minimum(restarted._current_skill_state(artifact.skill).activation_proof) == 0.70


def test_manual_support_retains_its_saved_coverage_after_restart(progression):  # noqa: F811
    learner, database, settings = progression
    learner.set_coverage_policy(65, 0)
    entry = candidate(learner, ChallengerSkill.ENTRY, "manual-entry")
    artifact = candidate(learner, ChallengerSkill.SIZING, coverage=0.8)
    learner.set_coverage_policy(70, 1)
    learner._activate_skill(entry, grant_consent=True)
    learner._activate_skill(artifact, grant_consent=True)
    assert not learner.auto_participation
    learner.set_coverage_policy(65, 2)
    assert (
        learner._skill_health(artifact.skill, artifact.version)["minimum_availability_fraction"]
        == 0.70
    )
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    assert restarted.active_skill_versions == {"entry": entry.version, "sizing": artifact.version}
    assert (
        restarted._skill_health(artifact.skill, artifact.version)["minimum_availability_fraction"]
        == 0.70
    )


@pytest.mark.parametrize("skill", list(ChallengerSkill))
def test_raising_keeps_champions_whose_fitted_and_activation_proof_pass(progression, skill):  # noqa: F811
    learner, database, settings = progression
    learner.set_coverage_policy(65, 0)
    artifact = candidate(learner, skill, coverage=0.8)
    evidence(learner, artifact, usable=100, count=100)
    learner.set_participation(True)
    before = artifact.model_dump()
    learner.set_coverage_policy(70, 1)
    assert learner.active_skill_versions == {skill.value: artifact.version}
    assert learner._skill_health(skill, artifact.version)["minimum_availability_fraction"] == 0.70
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    assert restarted.active_skill_versions == {skill.value: artifact.version}
    assert restarted.skill_artifacts[artifact.version].model_dump() == before


@pytest.mark.parametrize("percent", [55, 60])
def test_coach_challenger_against_native_also_freezes_both_sides_at_70(coach_lifecycle, percent):  # noqa: F811
    learner, _, _ = coach_lifecycle
    learner.set_coverage_policy(percent, 0)
    native = candidate(learner, ChallengerSkill.ENTRY)
    version, result = learner.seed_coach_candidate(_supported_coach_hypothesis(datetime.now(UTC)))
    assert result == "handed_off" and version
    state = learner._current_skill_state(ChallengerSkill.ENTRY)
    assert state.champion_version == native.version and state.testing_version == version
    assert saved_minimum(state.last_tournament) == 0.70
    assert state._battle_replay["minimum_coverage"] == 0.70


@pytest.mark.parametrize("independent", [True, False])
def test_corrupt_native_entry_activation_policy_cannot_keep_authority(progression, independent):  # noqa: F811
    learner, database, settings = progression
    learner.set_coverage_policy(65, 0)
    artifact = candidate(learner, ChallengerSkill.ENTRY)
    evidence(learner, artifact, usable=100, count=100)
    if independent:
        learner.set_participation(True)
    else:
        learner._activate_skill(artifact, grant_consent=True)
    assert learner.active_skill_versions == {"entry": artifact.version}
    state = learner._current_skill_state(artifact.skill)
    state.activation_proof["coverage_minimum_percent"] = "invalid"
    assert not learner._valid_activation_proof(state, artifact, {})
    assert learner._skill_health(artifact.skill, artifact.version)["state"] == "suspended"
    database.save_challenger_skill_state(state)
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    assert not restarted.active_skill_versions
    learner._govern_skill_ensemble()
    assert not learner.active_skill_versions
