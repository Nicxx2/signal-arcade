"""Only mathematically identical native Exit policies may skip a redundant battle."""

from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.intelligence.learning import CHALLENGER_SKILL_SCHEMA_VERSION, _stable_digest
from signal_arcade.models import ChallengerSkill, StatisticalModelFamily
from test_participation_progression import native_champion, progression  # noqa: F401


def deterministic_champion(learner):
    base = native_champion(learner, ChallengerSkill.EXIT, datetime.now(UTC))
    base = base.model_copy(
        update={
            "version": "deterministic-champion",
            "schema_version": CHALLENGER_SKILL_SCHEMA_VERSION,
            "model_family": StatisticalModelFamily.DETERMINISTIC,
            "implementation_version": "bounded-horizon-selector-v1",
            "recipe_version": "exit-horizon-v1",
            "payload_digest": _stable_digest(base.parameters),
        }
    )
    learner.skill_artifacts[base.version] = base
    learner.database.save_challenger_artifact(base)
    state = learner._current_skill_state(ChallengerSkill.EXIT)
    state.champion_version = base.version
    learner.database.save_challenger_skill_state(state)
    return base, state


def test_identical_exit_publication_keeps_different_waiting_contender(progression):  # noqa: F811
    learner, _, _ = progression
    base, state = deterministic_champion(learner)
    different = base.model_copy(
        update={
            "version": "different",
            "parameters": {**base.parameters, "selected_horizon_seconds": 60},
        }
    )
    learner._register_skill_artifact(different, state.cohort_key, defer_tournament=True)
    before = list(state.pending_versions)
    assert before == [different.version]
    duplicate = base.model_copy(
        update={"version": "duplicate", "created_at": base.created_at + timedelta(minutes=1)}
    )
    learner._register_skill_artifact(duplicate, state.cohort_key, defer_tournament=True)
    assert state.pending_versions == before
    assert state.testing_version is None
    assert state.latest_candidate_version == duplicate.version
    assert learner.skill_artifacts[duplicate.version] == duplicate


@pytest.mark.parametrize(
    "field",
    [
        "parameters",
        "payload_digest",
        "recipe_version",
        "implementation_version",
        "schema_version",
        "baseline_version",
        "feature_schema_version",
        "model_family",
    ],
)
def test_exit_similarity_is_not_policy_identity(progression, field):  # noqa: F811
    learner, _, _ = progression
    base, state = deterministic_champion(learner)
    value = (
        {**base.parameters, "selected_horizon_seconds": 60}
        if field == "parameters"
        else StatisticalModelFamily.LINEAR
        if field == "model_family"
        else "different"
    )
    candidate = base.model_copy(update={"version": "changed-contract", field: value})
    learner._register_skill_artifact(candidate, state.cohort_key, defer_tournament=True)
    assert candidate.version in state.pending_versions


def test_duplicate_does_not_reset_active_battle_or_discard_coach(progression):  # noqa: F811
    learner, _, _ = progression
    base, state = deterministic_champion(learner)
    battle = base.model_copy(
        update={
            "version": "running-battle",
            "parameters": {**base.parameters, "selected_horizon_seconds": 60},
        }
    )
    learner._register_skill_artifact(battle, state.cohort_key)
    assert state.testing_version == battle.version
    state.common_forward_count = 17
    coach = base.model_copy(
        update={"version": "waiting-coach", "schema_version": "challenger-skill-coach-v1"}
    )
    learner._register_skill_artifact(coach, state.cohort_key, defer_tournament=True)
    candidate = base.model_copy(update={"version": "duplicate-fit"})
    learner._register_skill_artifact(candidate, state.cohort_key)
    assert state.testing_version == battle.version and state.common_forward_count == 17
    assert (
        coach.version in state.pending_versions and candidate.version not in state.pending_versions
    )


def test_queued_duplicates_are_removed_before_selecting_next_battle(progression):  # noqa: F811
    learner, _, _ = progression
    base, state = deterministic_champion(learner)
    duplicate = base.model_copy(update={"version": "old-queued-duplicate"})
    learner.skill_artifacts[duplicate.version] = duplicate
    state.pending_versions = [duplicate.version]
    learner._start_next_skill_tournament(state)
    assert state.testing_version is None and not state.pending_versions
    assert state.champion_version == base.version
