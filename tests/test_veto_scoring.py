from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.intelligence.learning import (
    ENTRY_VALIDATION_VERSION,
    FEATURE_NAMES,
    FEATURE_SCHEMA_VERSION,
    LearningEngine,
    _challenger_cohort_key,
    _participation_values,
    _tournament_policy_value,
)
from signal_arcade.models import (
    ChallengerSkill,
    ChallengerSkillArtifact,
    RiskMode,
)
from signal_arcade.strategy import BASELINE_VERSION
from test_learning import make_decision, make_state, policy_episode_for, resolve_forward_primary


@pytest.fixture(params=[ChallengerSkill.ENTRY, ChallengerSkill.MANIPULATION])
def veto_battle(settings, request):
    database = Database(settings.database_path)
    configuration = "veto-scoring-context"
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: configuration)
    skill = request.param
    now = datetime.now(UTC) - timedelta(hours=2)
    cohort = _challenger_cohort_key(
        RiskMode.BALANCED, configuration, BASELINE_VERSION, FEATURE_SCHEMA_VERSION
    )
    assert cohort
    for version, prediction in [("champion", 0.2), ("candidate", -0.2)]:
        artifact = ChallengerSkillArtifact(
            version=version,
            skill=skill,
            created_at=now,
            risk_mode=RiskMode.BALANCED,
            configuration_fingerprint=configuration,
            baseline_version=BASELINE_VERSION,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            feature_names=list(FEATURE_NAMES),
            parameters={
                "means": [0.0] * len(FEATURE_NAMES),
                "scales": [1.0] * len(FEATURE_NAMES),
                "coefficients": [prediction, *([0.0] * len(FEATURE_NAMES))],
            },
            metrics={"validation_rmse": 0.05},
            hyperparameters={"entry_validation_version": ENTRY_VALIDATION_VERSION},
            qualified=True,
        )
        learner._register_skill_artifact(artifact, cohort)
    for index in range(30):
        at = now + timedelta(minutes=10 + index)
        mint = f"comparison-{index}"
        decision = make_decision(at, mint).model_copy(
            update={"configuration_fingerprint": configuration}
        )
        assert learner.register(decision, make_state(mint), live=True, evaluation_actionable=True)
        resolve_forward_primary(learner, mint, at + timedelta(seconds=300), -0.2)
    yield learner, database, learner.skill_states[(cohort, skill)]
    database.close()


@pytest.mark.parametrize("outcome", [-0.2, 0.0, 0.2, None])
@pytest.mark.parametrize("supported", [True, False])
def test_comparison_matches_execution_fallback(veto_battle, outcome, supported):
    learner, _, _ = veto_battle
    episode = policy_episode_for(learner, "comparison-0")
    episode.checkpoints["300"].net_return = outcome
    receipt = episode.challenger_evaluations["candidate"].model_copy(
        update={"in_distribution": supported}
    )
    actual, baseline = _participation_values(episode, receipt)
    assert baseline == outcome
    assert _tournament_policy_value(episode, receipt) == actual


@pytest.mark.parametrize("unsupported", ["candidate", "champion", "both"])
def test_unsupported_cases_cannot_award_a_false_crown(veto_battle, unsupported):
    learner, _, state = veto_battle
    for episode in learner.evidence_episodes.values():
        for version, receipt in episode.challenger_evaluations.items():
            if unsupported in {version, "both"}:
                receipt.in_distribution = False
                receipt.proposed_action = "veto"  # Existing persisted receipt representation.
        if unsupported == "champion":
            # The familiar candidate keeps the trade, just as the unfamiliar Champion must.
            episode.challenger_evaluations["candidate"].proposed_action = "support"
    learner._advance_entry_tournaments()
    assert state.champion_version == "champion"
    assert state.last_tournament["mean_uplift"] == 0.0


def test_unsupported_winners_are_not_counted_as_vetoes(veto_battle):
    learner, _, state = veto_battle
    for episode in learner.evidence_episodes.values():
        episode.checkpoints["300"].net_return = 0.2
        for receipt in episode.challenger_evaluations.values():
            receipt.in_distribution = False
            receipt.proposed_action = "veto"
    learner._advance_entry_tournaments()
    assert state.last_tournament["candidate_winner_vetoes"] == 0
    assert state.last_tournament["champion_winner_vetoes"] == 0


def test_manual_health_and_join_use_execution_fallback(veto_battle):
    learner, _, state = veto_battle
    for episode in learner.evidence_episodes.values():
        episode.active_skill_versions[state.skill.value] = "candidate"
        for receipt in episode.challenger_evaluations.values():
            receipt.in_distribution = False
            receipt.proposed_action = "veto"
    artifact = learner.skill_artifacts["candidate"]
    health = learner._skill_health(state.skill, artifact.version)
    join = learner._skill_join_evidence(artifact)
    assert health["estimated_uplift"] == 0.0
    assert join["mean_uplift"] == 0.0


def test_unknown_action_cannot_earn_a_cash_preservation_score(veto_battle):
    learner, _, _ = veto_battle
    episode = policy_episode_for(learner, "comparison-0")
    receipt = episode.challenger_evaluations["candidate"].model_copy(
        update={"proposed_action": "invalid"}
    )
    assert _tournament_policy_value(episode, receipt) is None


def test_corrected_battle_survives_restart_without_changing_the_artifact(veto_battle):
    learner, database, state = veto_battle
    frozen = learner.skill_artifacts["candidate"].model_dump_json()
    for episode in learner.evidence_episodes.values():
        episode.challenger_evaluations["candidate"].in_distribution = False
        database.save_learning_evidence_episode(episode)
    learner._advance_entry_tournaments()
    restarted = LearningEngine(
        database, learner.settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    restored = restarted.skill_states[(state.cohort_key, state.skill)]
    assert restored.champion_version == "champion"
    assert restored.last_tournament["mean_uplift"] == 0.0
    assert restored.last_tournament["action_scoring"] == "baseline-fallback-v1"
    assert restarted.skill_artifacts["candidate"].model_dump_json() == frozen
