from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.intelligence.learning import (
    FEATURE_SCHEMA_VERSION,
    MANIPULATION_FEATURE_NAMES,
    SIZING_FEATURE_NAMES,
    LearningEngine,
    _challenger_cohort_key,
    _participation_values,
)
from signal_arcade.models import (
    RISK_LIMITS,
    ChallengerEvaluationReceipt,
    ChallengerSkill,
    ChallengerSkillArtifact,
    LearningCheckpoint,
    LearningMode,
    RiskMode,
)
from signal_arcade.strategy import BASELINE_VERSION
from test_learning import (
    make_decision,
    make_state,
    policy_episode_for,
    qualified_model,
    resolve_forward_primary,
)


@pytest.fixture
def participation(settings):  # type: ignore[no-untyped-def]
    database = Database(settings.database_path)
    database.set_setting("demo_mode", False)
    configuration = "independent-participation-context"
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: configuration)
    now = datetime.now(UTC) - timedelta(hours=2)
    artifact = ChallengerSkillArtifact(
        version="challenger-skill-v2-manipulation-independent",
        skill=ChallengerSkill.MANIPULATION,
        created_at=now,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint=configuration,
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        sample_count=80,
        training_count=60,
        validation_count=20,
        outcomes_seen=80,
        feature_names=list(MANIPULATION_FEATURE_NAMES),
        parameters={
            "means": [0.0] * len(MANIPULATION_FEATURE_NAMES),
            "scales": [1.0] * len(MANIPULATION_FEATURE_NAMES),
            "coefficients": [-0.2, *([0.0] * len(MANIPULATION_FEATURE_NAMES))],
        },
        metrics={"validation_rmse": 0.05},
        qualified=True,
    )
    cohort = _challenger_cohort_key(
        RiskMode.BALANCED, configuration, BASELINE_VERSION, FEATURE_SCHEMA_VERSION
    )
    assert cohort
    learner._register_skill_artifact(artifact, cohort)  # noqa: SLF001
    for index in range(30):
        observed_at = now + timedelta(minutes=10 + index)
        mint = f"standalone-{index}"
        decision = make_decision(observed_at, mint).model_copy(
            update={"configuration_fingerprint": configuration, "model_version": BASELINE_VERSION}
        )
        assert learner.register(decision, make_state(mint), live=True, evaluation_actionable=True)
        resolve_forward_primary(learner, mint, observed_at + timedelta(seconds=300), -0.1)
    yield learner, database, artifact, settings, configuration
    database.close()


def test_non_entry_can_join_first_only_after_permission_and_forward_proof(participation):  # type: ignore[no-untyped-def]
    learner, database, artifact, settings, configuration = participation
    learner._govern_skill_ensemble()  # noqa: SLF001
    assert learner.active_skill_versions == {}
    learner.set_participation(True)
    assert learner.mode == LearningMode.ACTIVE
    assert learner.active_skill_versions == {"manipulation": artifact.version}
    assert learner._skill_activation_candidate() is None  # noqa: SLF001
    decision = make_decision(datetime.now(UTC), "actual").model_copy(
        update={"configuration_fingerprint": configuration, "model_version": BASELINE_VERSION}
    )
    assessed = learner.assess(decision, live=True, baseline_actionable=True)
    assert "challenger_manipulation_veto" in assessed.blockers
    assert learner.assess(decision, live=False, baseline_actionable=True) == decision
    state = learner._current_skill_state(ChallengerSkill.MANIPULATION)  # noqa: SLF001
    joined = state.joined_at
    learner.set_participation(True)
    assert state.joined_at == joined  # repeated PUT cannot reset authority/health
    restarted = LearningEngine(database, settings, configuration_fingerprint=lambda: configuration)
    assert restarted.auto_participation
    assert restarted.active_skill_versions == {"manipulation": artifact.version}


@pytest.mark.parametrize(
    "failure", ["missing", "different_ensemble", "unsupported", "no_advantage"]
)
def test_no_false_activation_from_incomplete_or_wrong_context_proof(participation, failure):  # type: ignore[no-untyped-def]
    learner, _, artifact, _, _ = participation
    for episode in learner.evidence_episodes.values():
        if artifact.version not in episode.challenger_evaluations:
            continue
        if failure == "missing":
            episode.checkpoints["300"].net_return = None
        elif failure == "different_ensemble":
            episode.active_skill_versions = {"entry": "unrelated-entry"}
        elif failure == "unsupported":
            episode.challenger_evaluations[artifact.version].in_distribution = False
        else:
            episode.checkpoints["300"].net_return = 0
    learner.set_participation(True)
    assert learner.auto_participation
    assert learner.mode == LearningMode.SHADOW
    assert learner.active_skill_versions == {}


def test_disable_pause_demo_and_context_change_preserve_safe_fallback(participation):  # type: ignore[no-untyped-def]
    learner, database, _, _, _ = participation
    learner.set_participation(True)
    learner.set_mode(LearningMode.OFF)
    learner._govern_skill_ensemble()  # noqa: SLF001
    assert learner.active_skill_versions == {}
    assert learner.auto_participation
    learner.set_mode(LearningMode.SHADOW)
    learner._govern_skill_ensemble()  # noqa: SLF001
    assert learner.mode == LearningMode.ACTIVE
    database.set_setting("demo_mode", True)
    learner._govern_skill_ensemble()  # noqa: SLF001
    assert learner.active_skill_versions == {}
    assert learner.auto_participation
    database.set_setting("demo_mode", False)
    learner.set_risk_mode(RiskMode.SAFE)
    learner._govern_skill_ensemble()  # noqa: SLF001
    assert learner.active_skill_versions == {}
    learner.set_participation(False)
    assert not database.get_setting("challenger_auto_participation")


def test_missing_activation_receipt_cannot_restore_standalone_authority(participation):  # type: ignore[no-untyped-def]
    learner, database, _, settings, configuration = participation
    learner.set_participation(True)
    state = learner._current_skill_state(ChallengerSkill.MANIPULATION)  # noqa: SLF001
    state.activation_proof = {}
    database.save_challenger_skill_state(state)
    restarted = LearningEngine(database, settings, configuration_fingerprint=lambda: configuration)
    assert restarted.mode == LearningMode.SHADOW
    assert restarted.active_skill_versions == {}
    assert restarted.auto_participation


@pytest.mark.parametrize("paused", [False, True])
def test_manual_active_cannot_mix_legacy_authority_with_automatic_support(
    participation, monkeypatch, paused
):  # type: ignore[no-untyped-def]
    learner, database, _, _, _ = participation
    learner.set_participation(True)
    if paused:
        learner.set_mode(LearningMode.OFF)
    before_mode = learner.mode
    before_versions = dict(learner.active_skill_versions)
    legacy = qualified_model("legacy-manual-candidate", -0.1, 100)
    monkeypatch.setattr(learner, "_activation_candidate", lambda: legacy)

    with pytest.raises(ValueError, match="automatic Champion support governs activation"):
        learner.set_mode(LearningMode.ACTIVE)

    assert learner.active_model is None
    assert learner.mode == before_mode
    assert learner.active_skill_versions == before_versions
    assert database.get_setting("challenger_auto_participation") is True
    assert not database.get_setting("active_learning_model")


def test_suspension_keeps_permission_but_cannot_reenable_same_artifact(participation):  # type: ignore[no-untyped-def]
    learner, _, _, _, _ = participation
    learner.set_participation(True)
    learner._suspend_skill(ChallengerSkill.MANIPULATION, "degraded")  # noqa: SLF001
    learner._govern_skill_ensemble()  # noqa: SLF001
    assert learner.active_skill_versions == {}
    assert learner.auto_participation


def test_entry_join_requires_standalone_skill_to_reprove_composition_after_restart(
    participation, monkeypatch
):  # type: ignore[no-untyped-def]
    learner, database, manipulation, settings, configuration = participation
    learner.set_participation(True)
    assert learner.active_skill_versions == {"manipulation": manipulation.version}

    now = datetime.now(UTC)
    entry_model = qualified_model("later-entry", 0.20, 80).model_copy(
        update={"created_at": now, "configuration_fingerprint": configuration}
    )
    learner._publish_entry_artifact(  # noqa: SLF001
        entry_model,
        baseline_version=BASELINE_VERSION,
        evidence_started_at=now - timedelta(hours=1),
        evidence_ended_at=now,
    )
    monkeypatch.setattr(
        learner, "entry_outcome_availability", lambda *args, **kwargs: {"qualified": True}
    )
    learner._govern_skill_ensemble()  # noqa: SLF001
    assert set(learner.active_skill_versions) == {"entry"}
    state = learner._current_skill_state(ChallengerSkill.MANIPULATION)  # noqa: SLF001
    assert state.champion_version == manipulation.version
    assert state.active_version is None
    assert state.suspended_version is None

    # Standalone evidence cannot establish a safe veto beside a newly active Entry model.
    learner._govern_skill_ensemble()  # noqa: SLF001
    assert set(learner.active_skill_versions) == {"entry"}
    restarted = LearningEngine(database, settings, configuration_fingerprint=lambda: configuration)
    assert restarted.auto_participation
    assert restarted.active_skill_versions == learner.active_skill_versions
    assert not restarted._skill_join_evidence(manipulation, independent=True)["ready"]  # noqa: SLF001


def test_unsupported_veto_never_earns_cash_preservation_advantage(participation):  # type: ignore[no-untyped-def]
    learner, _, artifact, _, _ = participation
    episode = policy_episode_for(learner, "standalone-0")
    receipt = episode.challenger_evaluations[artifact.version].model_copy(
        update={"in_distribution": False}
    )
    assert _participation_values(episode, receipt) == (-0.1, -0.1)


@pytest.mark.parametrize("skill", [ChallengerSkill.SIZING, ChallengerSkill.EXIT])
def test_sizing_and_exit_can_each_be_first_with_their_own_proof(participation, skill):  # type: ignore[no-untyped-def]
    learner, database, original, settings, configuration = participation
    learner.skill_states.clear()
    learner.evidence_episodes.clear()
    learner.observations.clear()
    parameters = (
        {"selected_horizon_seconds": 300, "baseline_horizon_seconds": 600}
        if skill == ChallengerSkill.EXIT
        else {
            "means": [0.0] * len(SIZING_FEATURE_NAMES),
            "scales": [1.0] * len(SIZING_FEATURE_NAMES),
            "coefficients": [0.5, *([0.0] * len(SIZING_FEATURE_NAMES))],
        }
    )
    artifact = original.model_copy(
        update={
            "skill": skill,
            "version": f"standalone-{skill.value}",
            "parameters": parameters,
            "feature_names": list(SIZING_FEATURE_NAMES) if skill == ChallengerSkill.SIZING else [],
        }
    )
    cohort = _challenger_cohort_key(
        RiskMode.BALANCED, configuration, BASELINE_VERSION, FEATURE_SCHEMA_VERSION
    )
    assert cohort
    learner._register_skill_artifact(artifact, cohort)  # noqa: SLF001
    for index in range(30):
        at = original.created_at + timedelta(minutes=60 + index)
        mint = f"{skill.value}-{index}"
        decision = make_decision(at, mint).model_copy(
            update={"configuration_fingerprint": configuration, "model_version": BASELINE_VERSION}
        )
        assert learner.register(decision, make_state(mint), live=True, evaluation_actionable=True)
        resolve_forward_primary(learner, mint, at + timedelta(seconds=300), 0.1)
        episode = policy_episode_for(learner, mint)
        if skill == ChallengerSkill.EXIT:
            horizon = RISK_LIMITS[RiskMode.BALANCED].max_hold_seconds
            episode.checkpoints[str(horizon)] = LearningCheckpoint(
                horizon_seconds=horizon,
                observed_at=at + timedelta(seconds=horizon),
                net_return=-0.1,
            )
        else:
            for trial in episode.size_trials.values():
                assert trial.entry_cost_lamports
                trial.checkpoints["300"] = LearningCheckpoint(
                    horizon_seconds=300,
                    observed_at=at + timedelta(seconds=300),
                    exit_value_lamports=int(trial.entry_cost_lamports * 0.9),
                )
        database.save_learning_evidence_episode(episode)
    learner.set_participation(True)
    assert learner.active_skill_versions == {skill.value: artifact.version}
    if skill == ChallengerSkill.EXIT:
        assert learner.recommended_hold_seconds(RiskMode.BALANCED) == 300
        state = learner._current_skill_state(skill)  # noqa: SLF001
        state.suspended_version = artifact.version
        assert (
            learner.recommended_hold_seconds(RiskMode.BALANCED)
            == RISK_LIMITS[RiskMode.BALANCED].max_hold_seconds
        )
    else:
        assert learner._current_skill_state(skill).activation_proof["usable_count"] == 30  # noqa: SLF001


def test_exit_composition_uses_bounded_size_and_requires_its_horizon_receipts(participation):  # type: ignore[no-untyped-def]
    learner, _, _, _, _ = participation
    episode = policy_episode_for(learner, "standalone-0")
    episode.active_skill_versions = {"sizing": "sizing-version"}
    sizing = ChallengerEvaluationReceipt(
        artifact_version="sizing-version",
        skill=ChallengerSkill.SIZING,
        evaluated_at=episode.created_at,
        in_distribution=True,
        proposed_action="2",
        baseline_actionable=True,
        parameters={"bounds_policy": "sizing-authority-v1", "bounded_multiplier": 1.0},
    )
    episode.challenger_evaluations[sizing.artifact_version] = sizing
    exit_receipt = ChallengerEvaluationReceipt(
        artifact_version="exit-version",
        skill=ChallengerSkill.EXIT,
        evaluated_at=episode.created_at,
        in_distribution=True,
        proposed_action="300",
        baseline_actionable=True,
    )
    horizon = RISK_LIMITS[RiskMode.BALANCED].max_hold_seconds
    trial = episode.size_trials["1"]
    assert trial.entry_cost_lamports
    for seconds, value in [(300, 1.1), (horizon, 0.9)]:
        trial.checkpoints[str(seconds)] = LearningCheckpoint(
            horizon_seconds=seconds,
            observed_at=episode.created_at + timedelta(seconds=seconds),
            exit_value_lamports=int(trial.entry_cost_lamports * value),
        )
    actual, baseline = _participation_values(episode, exit_receipt)
    assert actual == pytest.approx(0.1, abs=1e-6)
    assert baseline == pytest.approx(-0.1, abs=1e-6)
    trial.checkpoints.pop(str(horizon))
    assert _participation_values(episode, exit_receipt)[1] is None
    sizing.parameters.clear()
    assert _participation_values(episode, exit_receipt) == (None, None)
