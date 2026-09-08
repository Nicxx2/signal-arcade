from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.intelligence.learning import LearningEngine, _challenger_cohort_key
from signal_arcade.models import ChallengerSkill, StatisticalModelFamily
from test_participation_progression import native_champion


@pytest.mark.parametrize("difference", ["digest", "cutoff", "missing_digest", "count"])
def test_different_validation_populations_use_waiting_order_not_raw_scores(
    settings, monkeypatch, difference
):
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: "selection")
    now = datetime.now(UTC)
    base = native_champion(learner, ChallengerSkill.SIZING, now)
    old = base.model_copy(
        update={
            "version": "old-xgb",
            "model_family": StatisticalModelFamily.XGBOOST,
            "evidence_cohort_digest": "older-cohort",
            "training_cutoff_at": now,
            "metrics": {"validation_rmse": 10.0, "policy_uplift_lower": 0.001},
        }
    )
    newer = old.model_copy(
        update={
            "version": "new-linear",
            "model_family": StatisticalModelFamily.LINEAR,
            "created_at": now + timedelta(hours=1),
            "metrics": {"validation_rmse": 0.01, "policy_uplift_lower": 0.9},
        }
    )
    if difference == "digest":
        newer.evidence_cohort_digest = "new-cohort"
    elif difference == "cutoff":
        newer.training_cutoff_at = now + timedelta(hours=1)
    elif difference == "missing_digest":
        old.evidence_cohort_digest = newer.evidence_cohort_digest = None
    else:
        newer.validation_count += 1
    learner.skill_artifacts.update({item.version: item for item in (old, newer)})
    monkeypatch.setattr(learner, "_load_nonlinear_artifact", lambda _: object())
    state = learner._current_skill_state(ChallengerSkill.SIZING)
    state.pending_versions = [newer.version, old.version]
    assert learner._preferred_pending_version(state) == old.version
    database.close()


def test_native_exit_generations_do_not_discard_waiting_coach_or_active_battle(settings):
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: "selection")
    now = datetime.now(UTC)
    base = native_champion(learner, ChallengerSkill.EXIT, now)
    cohort = _challenger_cohort_key(
        base.risk_mode,
        base.configuration_fingerprint,
        base.baseline_version,
        base.feature_schema_version,
    )
    state = learner._current_skill_state(base.skill)
    battle = base.model_copy(
        update={"version": "ongoing", "created_at": now + timedelta(seconds=1)}
    )
    learner._register_skill_artifact(battle, cohort)
    assert state.testing_version == battle.version
    coach = base.model_copy(
        update={
            "version": "coach-waiting",
            "schema_version": "challenger-skill-coach-v1",
            "model_family": StatisticalModelFamily.DETERMINISTIC,
            "created_at": now + timedelta(seconds=2),
        }
    )
    learner._register_skill_artifact(coach, cohort)
    for i in range(20):
        latest = base.model_copy(
            update={
                "version": f"native-{i}",
                "model_family": StatisticalModelFamily.DETERMINISTIC,
                "created_at": now + timedelta(seconds=3 + i),
            }
        )
        learner._register_skill_artifact(latest, cohort)
        assert state.testing_version == battle.version
        assert state.pending_versions == [coach.version, latest.version]
    state.testing_version = None
    learner._start_next_skill_tournament(state)
    assert state.testing_version == coach.version
    database.close()


@pytest.mark.parametrize("policy_cohort", [None, "different", "same"])
def test_entry_selection_requires_matching_policy_population(settings, monkeypatch, policy_cohort):
    database = Database(settings.database_path)
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: "selection")
    now = datetime.now(UTC)
    base = native_champion(learner, ChallengerSkill.SIZING, now)
    old = base.model_copy(
        update={
            "version": "older-linear",
            "skill": ChallengerSkill.ENTRY,
            "model_family": StatisticalModelFamily.LINEAR,
            "evidence_cohort_digest": "discovery",
            "training_cutoff_at": now,
            "parameters": {"policy_evidence_cohort": "v1:policy-one"},
            "metrics": {"validation_rmse": 1.0, "policy_uplift_lower": 0.01},
        }
    )
    newer = old.model_copy(
        update={
            "version": "newer-xgb",
            "created_at": now + timedelta(hours=1),
            "model_family": StatisticalModelFamily.XGBOOST,
            "parameters": (
                {
                    "policy_evidence_cohort": "v1:policy-one"
                    if policy_cohort == "same"
                    else "v1:policy-two"
                }
                if policy_cohort
                else {}
            ),
            "metrics": {"validation_rmse": 0.9, "policy_uplift_lower": 0.02},
        }
    )
    learner.skill_artifacts.update({item.version: item for item in (old, newer)})
    monkeypatch.setattr(learner, "_load_nonlinear_artifact", lambda _: object())
    state = learner._current_skill_state(ChallengerSkill.SIZING).model_copy(
        update={"skill": ChallengerSkill.ENTRY, "champion_version": None}
    )
    state.pending_versions = [newer.version, old.version]
    assert learner._preferred_pending_version(state) == (
        newer.version if policy_cohort == "same" else old.version
    )
    database.close()


def test_policy_cohort_tracks_unknown_labels_and_membership_without_model_predictions(settings):
    from signal_arcade.intelligence.learning import _policy_evidence_cohort
    from signal_arcade.models import LearningCheckpoint
    from test_learning import policy_episode_for
    from test_policy_identity import enroll

    database = Database(settings.database_path)
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: "identity-test")
    at = datetime.now(UTC)
    episodes = []
    for index in range(2):
        mint = f"cohort-{index}"
        enroll(learner, mint, at + timedelta(seconds=index))
        episode = policy_episode_for(learner, mint)
        episode.checkpoints["300"] = LearningCheckpoint(
            horizon_seconds=300,
            observed_at=at + timedelta(minutes=5, seconds=index),
            net_return=None if index else -0.1,
            missing_reason="route_unavailable" if index else None,
        )
        episodes.append(episode)
    original = _policy_evidence_cohort(episodes)
    assert _policy_evidence_cohort(list(reversed(episodes))) == original
    assert _policy_evidence_cohort(episodes[:1]) != original
    episodes[1].checkpoints["300"].net_return = 0.2
    assert _policy_evidence_cohort(episodes) != original
    database.close()
