from datetime import UTC, datetime

import pytest
from signal_arcade.config import Settings
from signal_arcade.database import Database
from signal_arcade.intelligence.learning import LearningEngine, _challenger_cohort_key
from signal_arcade.models import (
    ChallengerSkill,
    CoachCondition,
    CoachExperimentKind,
    LearningMode,
)
from test_learning import _coach_test_champion, _supported_coach_hypothesis
from test_participation_progression import native_champion


@pytest.mark.parametrize("skill", list(ChallengerSkill))
def test_coach_handoff_preserves_paused_learning_and_champion_across_restart(
    settings: Settings, skill: ChallengerSkill
) -> None:
    """Supported research is a fixture; handoff must never stand in for activation proof."""
    now = datetime.now(UTC)
    hypothesis = _supported_coach_hypothesis(now)
    hypothesis.skill = skill
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

    cohort = _challenger_cohort_key(
        hypothesis.risk_mode,
        hypothesis.configuration_fingerprint,
        hypothesis.baseline_version,
        hypothesis.feature_schema_version,
    )
    assert cohort is not None
    database = Database(settings.database_path)
    database.set_setting("demo_mode", False)
    try:
        learner = LearningEngine(database, settings, configuration_fingerprint=lambda: "coach-fp")
        assert learner.seed_coach_candidate(hypothesis) == (None, "waiting_for_champion")
        assert not learner.skill_artifacts
        if skill == ChallengerSkill.ENTRY:
            champion = _coach_test_champion(now)
            learner._register_skill_artifact(champion, cohort)  # noqa: SLF001
        else:
            champion = native_champion(learner, skill, now)
        learner.set_participation(True)
        learner.set_mode(LearningMode.OFF)

        stale = hypothesis.model_copy(update={"dependency_versions": {"entry": "old-version"}})
        assert learner.seed_coach_candidate(stale) == (None, "coach_context_stale")
        assert len(learner.skill_artifacts) == 1
        version, result = learner.seed_coach_candidate(hypothesis)
        assert version is not None and result == "handed_off"
        assert learner.seed_coach_candidate(hypothesis) == (version, "handed_off")
        assert len(learner.skill_artifacts) == 2
        assert learner.mode == LearningMode.OFF
        assert learner.auto_participation is True
        assert not learner.active_skill_versions
        state = learner.skill_states[(cohort, skill)]
        assert state.champion_version == champion.version
        assert state.testing_version == version
        assert state.common_forward_count == 0
    finally:
        database.close()

    restarted_database = Database(settings.database_path)
    try:
        restarted = LearningEngine(
            restarted_database, settings, configuration_fingerprint=lambda: "coach-fp"
        )
        assert restarted.mode == LearningMode.OFF
        assert restarted.auto_participation is True
        assert not restarted.active_skill_versions
        state = restarted.skill_states[(cohort, skill)]
        assert state.champion_version == champion.version
        assert state.testing_version == version
        assert state.common_forward_count == 0
        restarted.set_mode(LearningMode.SHADOW)
        assert restarted.seed_coach_candidate(hypothesis) == (version, "handed_off")
        assert len(restarted.skill_artifacts) == 2
        assert restarted.auto_participation is True
        assert not restarted.active_skill_versions
    finally:
        restarted_database.close()
