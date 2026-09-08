"""A research handoff and crown must not bypass fresh activation or ongoing health."""

from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.config import Settings
from signal_arcade.database import Database
from signal_arcade.intelligence.learning import LearningEngine, _challenger_cohort_key
from signal_arcade.models import (
    ChallengerSkill,
    CoachCondition,
    CoachExperimentKind,
    LearningCheckpoint,
    LearningEvidenceEpisode,
    LearningMode,
)
from test_learning import (
    _coach_test_champion,
    _supported_coach_hypothesis,
    make_decision,
    make_state,
    policy_episode_for,
    resolve_forward_primary,
)
from test_participation_progression import native_champion


def record_policy(learner: LearningEngine, mint: str, at: datetime) -> LearningEvidenceEpisode:
    decision = make_decision(at, mint)
    decision.configuration_fingerprint = learner.configuration_fingerprint()
    decision.feature_snapshot.values["momentum_1m"].value = -0.2
    decision.feature_snapshot.values["wallet_volume_hhi"].value = 0.5
    assert learner.register(decision, make_state(mint), live=True, evaluation_actionable=True)
    resolve_forward_primary(learner, mint, at + timedelta(seconds=300), -0.1)
    episode = policy_episode_for(learner, mint)
    episode.checkpoints["600"] = LearningCheckpoint(
        horizon_seconds=600,
        observed_at=at + timedelta(seconds=600),
        net_return=-0.3,
    )
    for trial in episode.size_trials.values():
        assert trial.entry_cost_lamports
        for horizon, retained in ((300, 0.9), (600, 0.7)):
            trial.checkpoints[str(horizon)] = LearningCheckpoint(
                horizon_seconds=horizon,
                observed_at=at + timedelta(seconds=horizon),
                exit_value_lamports=int(trial.entry_cost_lamports * retained),
            )
    learner.database.save_learning_evidence_episode(episode)
    return episode


def crowned_coach(learner: LearningEngine, skill: ChallengerSkill, *, replace_active=False) -> str:
    """Research qualification and a won battle are fixtures; joins/health are real."""
    now = datetime.now(UTC)
    if skill == ChallengerSkill.ENTRY:
        old = _coach_test_champion(now)
        cohort = _challenger_cohort_key(
            old.risk_mode,
            old.configuration_fingerprint,
            old.baseline_version,
            old.feature_schema_version,
        )
        assert cohort
        learner._register_skill_artifact(old, cohort)  # noqa: SLF001
    else:
        old = native_champion(learner, skill, now)
    if replace_active:
        for index in range(81):
            record_policy(learner, f"native-join-{index}", now + timedelta(seconds=index + 1))
        learner._govern_skill_ensemble()
        assert learner.active_skill_versions == {skill.value: old.version}
    hypothesis = _supported_coach_hypothesis(now)
    hypothesis.skill = skill
    hypothesis.dependency_versions = dict(learner.active_skill_versions)
    hypothesis.conditions = [CoachCondition(feature_name="momentum", operator="<=", threshold=0)]
    if skill == ChallengerSkill.MANIPULATION:
        hypothesis.kind = CoachExperimentKind.MANIPULATION_VETO
        hypothesis.conditions = [
            CoachCondition(feature_name="concentration", operator=">=", threshold=0.35)
        ]
    elif skill == ChallengerSkill.SIZING:
        hypothesis.kind = CoachExperimentKind.SIZING_MULTIPLIER
        hypothesis.conditions = []
        hypothesis.size_multiplier = 0.5
    elif skill == ChallengerSkill.EXIT:
        hypothesis.kind = CoachExperimentKind.EARLIER_REVIEW
        hypothesis.conditions = []
        hypothesis.hold_seconds = 300
        hypothesis.baseline_hold_seconds = 600
    version, result = learner.seed_coach_candidate(hypothesis)
    assert result == "handed_off" and version
    state = learner._current_skill_state(skill)  # noqa: SLF001
    assert state
    state.champion_version = version
    state.testing_version = None
    learner.database.save_challenger_skill_state(state)
    learner._promote_active_skill(learner.skill_artifacts[version], previous_version=old.version)  # noqa: SLF001
    return version


@pytest.fixture
def coach_lifecycle(settings: Settings):  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    database.set_setting("demo_mode", False)
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: "coach-fp")
    learner.set_participation(True)
    yield learner, database, settings
    database.close()


@pytest.mark.parametrize("skill", list(ChallengerSkill))
@pytest.mark.parametrize("outcome", ["healthy", "missing_receipt", "pending"])
@pytest.mark.parametrize("replace_active", [False, True])
def test_coach_crown_earns_activation_then_remains_monitored_across_restart(
    coach_lifecycle,
    skill: ChallengerSkill,
    outcome: str,  # type: ignore[no-untyped-def]
    replace_active: bool,
) -> None:
    learner, database, settings = coach_lifecycle
    version = crowned_coach(learner, skill, replace_active=replace_active)
    artifact_before = learner.skill_artifacts[version].model_dump()
    learner._govern_skill_ensemble()  # noqa: SLF001
    assert not learner.active_skill_versions
    at = datetime.now(UTC) + timedelta(minutes=1)
    for index in range(81):
        record_policy(learner, f"join-{index}", at + timedelta(seconds=index))
    learner._govern_skill_ensemble()  # noqa: SLF001
    assert learner.active_skill_versions == {skill.value: version}
    assert learner.skill_artifacts[version].model_dump() == artifact_before
    assert learner._skill_health(skill, version)["observed_count"] == 0  # noqa: SLF001
    for index in range(60):
        episode = record_policy(
            learner, f"health-{index}", at + timedelta(minutes=5, seconds=index)
        )
        if outcome != "healthy":
            episode.challenger_evaluations.pop(version, None)
        if outcome == "pending":
            episode.checkpoints.clear()
        database.save_learning_evidence_episode(episode)
    health = learner._skill_health(skill, version)  # noqa: SLF001
    assert (
        health["state"]
        == {
            "healthy": "healthy",
            "missing_receipt": "unverifiable",
            "pending": "collecting",
        }[outcome]
    )
    assert health["observed_count"] == (0 if outcome == "pending" else 60)
    learner._govern_skill_ensemble()  # noqa: SLF001
    expected = {} if outcome == "missing_receipt" else {skill.value: version}
    assert learner.active_skill_versions == expected
    restarted = LearningEngine(database, settings, configuration_fingerprint=lambda: "coach-fp")
    assert restarted.active_skill_versions == expected
    assert restarted.skill_artifacts[version].model_dump() == artifact_before


def test_coach_join_requires_new_proof_when_upstream_changes(coach_lifecycle) -> None:  # type: ignore[no-untyped-def]
    learner, _, _ = coach_lifecycle
    version = crowned_coach(learner, ChallengerSkill.EXIT)
    at = datetime.now(UTC) + timedelta(minutes=1)
    for index in range(31):
        record_policy(learner, f"old-context-{index}", at + timedelta(seconds=index))
    artifact = learner.skill_artifacts[version]
    assert learner._skill_join_evidence(artifact, independent=True)["ready"]  # noqa: SLF001
    learner.active_skill_versions = {"sizing": "different-upstream"}
    assert not learner._skill_join_evidence(artifact, independent=True)["ready"]  # noqa: SLF001


@pytest.mark.parametrize("skill", list(ChallengerSkill))
@pytest.mark.parametrize("automatic", [False, True])
def test_coach_restart_cannot_accept_a_native_activation_receipt(coach_lifecycle, skill, automatic):  # type: ignore[no-untyped-def]
    learner, database, settings = coach_lifecycle
    version = crowned_coach(learner, skill)
    at = datetime.now(UTC) + timedelta(minutes=1)
    for index in range(81):
        record_policy(learner, f"join-{index}", at + timedelta(seconds=index))
    learner._govern_skill_ensemble()
    assert learner.active_skill_versions == {skill.value: version}
    state = learner._current_skill_state(skill)
    assert state.activation_proof["policy"] == "coach-independent-v2"
    state.activation_proof["policy"] = "independent-v1"
    database.save_challenger_skill_state(state)
    database.set_setting("challenger_auto_participation", automatic)
    restarted = LearningEngine(database, settings, configuration_fingerprint=lambda: "coach-fp")
    assert restarted.active_skill_versions == {}
    assert restarted._current_skill_state(skill).champion_version == version


@pytest.mark.parametrize("clock", [None, "invalid", "2026-09-07T00:00:00"])
def test_coach_join_rejects_missing_or_invalid_clock_without_rewriting_it(coach_lifecycle, clock):  # type: ignore[no-untyped-def]
    learner, database, _ = coach_lifecycle
    version = crowned_coach(learner, ChallengerSkill.EXIT)
    at = datetime.now(UTC) + timedelta(minutes=1)
    for index in range(31):
        record_policy(learner, f"join-{index}", at + timedelta(seconds=index))
    artifact = learner.skill_artifacts[version]
    assert learner._skill_join_evidence(artifact)["ready"]
    state = learner._current_skill_state(artifact.skill)
    state.activation_proof["started_at"] = clock
    database.save_challenger_skill_state(state)
    before = state.model_dump()
    assert not learner._skill_join_evidence(artifact)["ready"]
    assert state.model_dump() == before


def battle_coach(learner, skill, *, replace_active):
    """Initial native qualification and supported research are fixtures; the battle is real."""
    now = datetime.now(UTC)
    if skill == ChallengerSkill.ENTRY:
        old = _coach_test_champion(now)
        cohort = _challenger_cohort_key(
            old.risk_mode,
            old.configuration_fingerprint,
            old.baseline_version,
            old.feature_schema_version,
        )
        learner._register_skill_artifact(old, cohort)
    else:
        old = native_champion(
            learner,
            skill,
            now,
            intercept=0.2 if skill == ChallengerSkill.MANIPULATION else 2.0,
        )
    if replace_active:
        # Represent an existing qualified native Champion through its legacy activation path.
        # Coach activation below must always pass fresh independent proof, even in manual mode.
        learner.auto_participation = False
        learner._activate_skill(old)
        learner.auto_participation = True
        learner.mode = LearningMode.ACTIVE
        learner.database.set_setting("learning_mode", LearningMode.ACTIVE.value)
        assert learner.active_skill_versions == {skill.value: old.version}
    hypothesis = _supported_coach_hypothesis(now)
    hypothesis.skill = skill
    hypothesis.dependency_versions = dict(learner.active_skill_versions)
    if skill == ChallengerSkill.MANIPULATION:
        hypothesis.kind = CoachExperimentKind.MANIPULATION_VETO
        hypothesis.conditions = [
            CoachCondition(feature_name="concentration", operator=">=", threshold=0.35)
        ]
    elif skill == ChallengerSkill.SIZING:
        hypothesis.kind = CoachExperimentKind.SIZING_MULTIPLIER
        hypothesis.conditions = []
        hypothesis.size_multiplier = 0.5
    elif skill == ChallengerSkill.EXIT:
        hypothesis.kind = CoachExperimentKind.EARLIER_REVIEW
        hypothesis.conditions = []
        hypothesis.hold_seconds = 60
        hypothesis.baseline_hold_seconds = 600
    version, result = learner.seed_coach_candidate(hypothesis)
    assert result == "handed_off" and version
    state = learner._current_skill_state(skill)
    assert state.champion_version == old.version and state.testing_version == version
    at = now + timedelta(minutes=1)
    for index in range(31):
        episode = record_policy(learner, f"real-battle-{index}", at + timedelta(seconds=index))
        episode.checkpoints["60"] = LearningCheckpoint(
            horizon_seconds=60,
            observed_at=episode.entry_at + timedelta(seconds=60),
            net_return=-0.01,
        )
        learner.database.save_learning_evidence_episode(episode)
    learner._advance_entry_tournaments()
    assert state.champion_version == version, state.last_tournament
    assert state.last_tournament["result"] == "promoted"
    assert state.last_tournament["common_usable_count"] == 31
    assert state.last_tournament["uplift_lower_bound"] > 0
    assert version not in learner.active_skill_versions.values()
    learner._govern_skill_ensemble()
    assert not learner.active_skill_versions
    assert not learner._skill_join_evidence(learner.skill_artifacts[version])["ready"]
    return version, at + timedelta(minutes=10)


@pytest.mark.parametrize("skill", list(ChallengerSkill))
@pytest.mark.parametrize("replace_active", [False, True])
@pytest.mark.parametrize("health_kind", ["healthy", "missing", "harmful", "pending"])
def test_real_coach_battle_then_fresh_activation_health_and_restart(
    coach_lifecycle, skill, replace_active, health_kind
):
    learner, database, settings = coach_lifecycle
    version, at = battle_coach(learner, skill, replace_active=replace_active)
    artifact_before = learner.skill_artifacts[version].model_dump()
    for index in range(81):
        episode = record_policy(learner, f"real-join-{index}", at + timedelta(seconds=index))
        episode.checkpoints["60"] = LearningCheckpoint(
            horizon_seconds=60,
            observed_at=episode.entry_at + timedelta(seconds=60),
            net_return=-0.01,
        )
        database.save_learning_evidence_episode(episode)
    learner._govern_skill_ensemble()
    assert learner.active_skill_versions == {skill.value: version}
    assert learner._skill_health(skill, version)["observed_count"] == 0
    for index in range(60):
        episode = record_policy(
            learner, f"real-health-{index}", at + timedelta(minutes=10, seconds=index)
        )
        episode.checkpoints["60"] = LearningCheckpoint(
            horizon_seconds=60,
            observed_at=episode.entry_at + timedelta(seconds=60),
            net_return=-0.01,
        )
        if health_kind in {"missing", "pending"}:
            episode.challenger_evaluations.pop(version)
        if health_kind == "pending":
            episode.checkpoints.clear()
        elif health_kind == "harmful":
            episode.checkpoints["300"].net_return = 0.3
            episode.checkpoints["600"].net_return = 0.3
            episode.checkpoints["60"].net_return = -0.3
            for trial in episode.size_trials.values():
                trial.checkpoints["300"].exit_value_lamports = int(trial.entry_cost_lamports * 1.3)
        database.save_learning_evidence_episode(episode)
    health = learner._skill_health(skill, version)
    assert (
        health["state"]
        == {
            "healthy": "healthy",
            "missing": "unverifiable",
            "harmful": "degraded",
            "pending": "collecting",
        }[health_kind]
    )
    learner._govern_skill_ensemble()
    expected = {skill.value: version} if health_kind in {"healthy", "pending"} else {}
    assert learner.active_skill_versions == expected
    restarted = LearningEngine(database, settings, configuration_fingerprint=lambda: "coach-fp")
    assert restarted.active_skill_versions == expected
    assert restarted._current_skill_state(skill).champion_version == version
    assert restarted.skill_artifacts[version].model_dump() == artifact_before
