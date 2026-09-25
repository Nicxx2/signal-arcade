"""The lowest opt-in requirement changes coverage, never proof or authority history."""

from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.intelligence.coverage_policy import (
    CoveragePolicy,
    meets_current,
    saved_minimum,
    validation_current,
)
from signal_arcade.intelligence.learning import LearningEngine
from signal_arcade.models import ChallengerSkill
from test_coverage_lifecycle import candidate, evidence
from test_exit_context import contextual_artifact
from test_participation_progression import progression, record_policy  # noqa: F401


@pytest.mark.parametrize(
    "skill,metric",
    [
        (ChallengerSkill.ENTRY, "outcome_availability"),
        (ChallengerSkill.ENTRY, "policy_outcome_availability"),
        (ChallengerSkill.MANIPULATION, "outcome_availability"),
        (ChallengerSkill.MANIPULATION, "policy_outcome_availability"),
        (ChallengerSkill.SIZING, "outcome_availability"),
        (ChallengerSkill.EXIT, "validation_availability_fraction"),
        (ChallengerSkill.EXIT, "reference_availability_fraction"),
    ],
)
def test_raising_saved_55_proof_checks_each_required_cohort(progression, skill, metric):  # noqa: F811
    learner, _, _ = progression
    learner.set_coverage_policy(55, 0)
    artifact = contextual_artifact() if skill == ChallengerSkill.EXIT else candidate(learner, skill)
    artifact = artifact.model_copy(
        deep=True,
        update={
            "hyperparameters": learner.coverage_policy.metadata(),
            "metrics": {
                "outcome_availability": 0.60,
                "policy_outcome_availability": 0.60,
                "validation_availability_fraction": 0.60,
                "reference_availability_fraction": 0.60,
            },
        },
    )
    original = artifact.model_dump()
    assert meets_current(artifact, 0.60)
    # A strong companion cohort must not hide missing, insufficient or corrupt proof.
    # Copies deliberately bypass model validation to exercise this authority boundary.
    for invalid in (None, 0.599, True, "0.60", float("nan"), float("inf"), 1.01):
        metrics = {**artifact.metrics, metric: invalid}
        if invalid is None:
            metrics.pop(metric)
        damaged = artifact.model_copy(update={"metrics": metrics})
        assert not meets_current(damaged, 0.60), (metric, invalid)
    assert artifact.model_dump() == original
    assert artifact.qualified and saved_minimum(artifact.hyperparameters) == 0.55


def test_damaged_55_policy_metadata_never_falls_back_to_legacy_authority():
    artifact = contextual_artifact()
    policy = CoveragePolicy(55, 1, datetime.now(UTC))
    record = {**policy.metadata(), "coverage_fresh_validation": True}
    artifact = artifact.model_copy(
        update={"hyperparameters": record, "training_cutoff_at": policy.effective_at}
    )
    assert validation_current(artifact)
    for field, invalid in (
        ("coverage_policy_version", "unknown"),
        ("coverage_minimum_percent", 55.0),
        ("coverage_revision", True),
        ("coverage_revision", 0),
        ("coverage_effective_at", None),
        ("coverage_effective_at", "2026-09-20T09:00:00"),
    ):
        damaged = artifact.model_copy(update={"hyperparameters": {**record, field: invalid}})
        assert saved_minimum(damaged.hyperparameters) == float("inf")
        assert not validation_current(damaged)
        assert not meets_current(damaged, 0.55)
    for missing in policy.record():
        partial = {key: value for key, value in record.items() if key != missing}
        damaged = artifact.model_copy(update={"hyperparameters": partial})
        assert not validation_current(damaged)
        assert not meets_current(damaged, 0.55)


@pytest.mark.parametrize("skill", list(ChallengerSkill))
def test_raise_from_55_revokes_insufficient_support_and_lower_does_not_revive(progression, skill):  # noqa: F811
    learner, database, settings = progression
    learner.set_coverage_policy(55, 0)
    artifact = candidate(learner, skill, coverage=0.55)
    # Activation uses the latest 60 Policy rows: 73 usable followed by 27 missing
    # leaves exactly 33/60 usable, while Entry also has its 80 resolved observations.
    evidence(learner, artifact, usable=73, count=100)
    assert learner._skill_join_evidence(artifact, independent=True)["availability_fraction"] == 0.55
    learner.set_participation(True)
    assert learner.active_skill_versions == {skill.value: artifact.version}
    # Native Entry initially activates from fitted proof and operational coverage.
    # Exercise its actual post-activation health window before raising the setting.
    later = artifact.model_copy(update={"created_at": artifact.created_at + timedelta(hours=1)})
    evidence(learner, later, usable=33, count=60, prefix="health")
    health = learner._skill_health(skill, artifact.version)
    assert health["state"] == "healthy" and health["availability_fraction"] == 0.55
    original = artifact.model_dump()
    learner.set_coverage_policy(60, 1)
    assert not learner.active_skill_versions
    learner.set_coverage_policy(55, 2)
    learner._govern_skill_ensemble()
    assert not learner.active_skill_versions
    assert artifact.model_dump() == original
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    assert restarted.coverage_policy.percent == 55
    assert not restarted.active_skill_versions
    assert restarted.consent_granted and restarted.auto_participation


@pytest.mark.parametrize("usable,expected", [(32, "failed"), (33, "restored")])
@pytest.mark.parametrize("skill", list(ChallengerSkill))
def test_recovery_at_55_keeps_its_fixed_window_and_result_after_restart(
    progression,  # noqa: F811
    skill,
    usable,
    expected,
):
    learner, database, settings = progression
    learner.set_coverage_policy(55, 0)
    artifact = candidate(learner, skill)
    evidence(learner, artifact, usable=100, count=100)
    learner.set_participation(True)
    learner._suspend_skill(skill, "unverifiable")
    later = artifact.model_copy(update={"created_at": artifact.created_at + timedelta(hours=1)})
    evidence(learner, later, usable=usable, count=60, prefix="recovery")
    learner._govern_skill_ensemble()
    state = learner._current_skill_state(skill)
    recovery = state.activation_proof["recovery"]
    assert recovery["status"] == expected
    assert saved_minimum(recovery) == 0.55
    frozen = recovery.copy()
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    retained = restarted._current_skill_state(skill).activation_proof["recovery"]
    assert retained == frozen
    if expected == "restored":
        assert restarted.active_skill_versions == {skill.value: artifact.version}
    if expected == "failed":
        restarted.set_coverage_policy(60, 1)
        restarted.set_coverage_policy(55, 2)
        restarted._govern_skill_ensemble()
        assert restarted._current_skill_state(skill).activation_proof["recovery"] == frozen
        assert not restarted.active_skill_versions


def test_55_battle_uses_new_receipts_and_cannot_restart_after_raise(progression):  # noqa: F811
    learner, database, settings = progression
    candidate(learner, ChallengerSkill.ENTRY, "old-champion", prediction=0.2)
    learner.set_coverage_policy(55, 0)
    contender = candidate(learner, ChallengerSkill.ENTRY, "contender")
    state = learner._current_skill_state(ChallengerSkill.ENTRY)
    assert state.testing_version == contender.version
    assert state.common_forward_count == 0
    assert saved_minimum(state.last_tournament) == 0.55
    assert state._battle_replay["minimum_coverage"] == 0.55
    learner.set_coverage_policy(60, 1)
    state = learner._current_skill_state(ChallengerSkill.ENTRY)
    assert state.testing_version is None
    assert state.last_tournament["result"] == "coverage_policy_changed"
    learner.set_coverage_policy(55, 2)
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    assert restarted._current_skill_state(ChallengerSkill.ENTRY).testing_version is None
    assert (
        contender.version in restarted._current_skill_state(ChallengerSkill.ENTRY).rejected_versions
    )


@pytest.mark.parametrize(
    "skill", [ChallengerSkill.MANIPULATION, ChallengerSkill.SIZING, ChallengerSkill.EXIT]
)
def test_sufficient_55_coverage_does_not_allow_harmful_activation(progression, skill):  # noqa: F811
    learner, _, _ = progression
    learner.set_coverage_policy(55, 0)
    artifact = candidate(learner, skill)
    evidence(learner, artifact, usable=73, count=100)
    for episode in learner.evidence_episodes.values():
        if episode.checkpoints["300"].net_return is None:
            continue
        episode.checkpoints["300"].net_return = 0.1
        episode.checkpoints["600"].net_return = 0.3
        for trial in episode.size_trials.values():
            for horizon, gain in (("300", 1.1), ("600", 1.3)):
                trial.checkpoints[horizon].exit_value_lamports = int(
                    trial.entry_cost_lamports * gain
                )
    proof = learner._skill_join_evidence(artifact, independent=True)
    assert proof["availability_fraction"] == 0.55
    assert proof["usable_count"] == 33
    assert proof["uplift_lower_bound"] < 0
    assert not proof["ready"]
    learner.set_participation(True)
    assert not learner.active_skill_versions


@pytest.mark.parametrize("skill", [ChallengerSkill.ENTRY, ChallengerSkill.MANIPULATION])
def test_more_55_qualifiers_bound_pending_work_without_replacing_trial_or_reusing_proof(
    progression,  # noqa: F811
    skill,
):
    learner, database, settings = progression
    learner.set_coverage_policy(55, 0)
    founder = candidate(learner, skill, "founder")
    testing = candidate(learner, skill, "testing")
    for index in range(12):
        waiting = candidate(learner, skill, f"waiting-{index}")
        state = learner._current_skill_state(skill)
        assert state.champion_version == founder.version
        assert state.testing_version == testing.version
        assert state.pending_versions == [waiting.version]
    episode = record_policy(learner, "fresh-forward", waiting.created_at + timedelta(minutes=10))
    # Waiting must not produce per-event inference or bank proof before its own trial.
    assert set(episode.challenger_evaluations) == {founder.version, testing.version}
    assert learner._skill_join_evidence(waiting, independent=True)["observed_count"] == 0
    assert not learner.active_skill_versions
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    retained = restarted._current_skill_state(skill)
    assert retained.testing_version == testing.version
    assert retained.pending_versions == [waiting.version]
    assert saved_minimum(retained.last_tournament) == 0.55
