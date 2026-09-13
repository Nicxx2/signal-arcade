"""Top-group membership must never use held-out returns to resolve equal forecasts."""

import hashlib
import itertools
import math

import pytest
from signal_arcade.intelligence.learning import (
    ENTRY_VALIDATION_VERSION,
    LearningEngine,
    _challenger_cohort_key,
    _entry_validation_current,
    _skill_qualified,
    _top_mean,
)
from signal_arcade.models import (
    ChallengerSkill,
    ChallengerSkillArtifact,
    ChallengerSkillState,
    LearningMode,
    StatisticalModelFamily,
)
from test_entry_proof_status import artifact
from test_learning import qualified_model
from test_participation_progression import progression  # noqa: F401


@pytest.mark.parametrize(
    ("predictions", "returns", "expected"),
    [
        ([1] * 6, [-0.3, -0.2, -0.1, 0, 0.1, 0.2], -0.05),
        ([3, 2, 2, 1, 0, -1], [0.3, -0.2, 0.4, -0.1, 0, 0.1], 0.2),
        ([6, 5, 4, 3, 2, 1], [0.1, 0.2, -0.2, 0.3, 0.4, -0.4], 0.15),
        ([1], [-0.1], -0.1),
    ],
)
def test_top_group_is_neutral_to_outcomes_within_prediction_ties(predictions, returns, expected):
    assert _top_mean(predictions, returns) == pytest.approx(expected)
    for indices in itertools.permutations(range(len(returns))):
        assert _top_mean(
            [predictions[i] for i in indices], [returns[i] for i in indices]
        ) == pytest.approx(expected)


@pytest.mark.parametrize(
    "predictions,returns", [([], []), ([1], [1, 2]), ([math.nan], [1]), ([1], [math.inf])]
)
def test_top_group_rejects_invalid_populations(predictions, returns):
    with pytest.raises(ValueError):
        _top_mean(predictions, returns)


def test_legacy_scores_remain_readable_but_do_not_grant_current_qualification():
    current = qualified_model("current", 0.2, 100)
    legacy = current.model_copy(update={"hyperparameters": {}})
    assert legacy.qualified and not _entry_validation_current(legacy)
    assert _entry_validation_current(current)
    base = dict(
        version="entry",
        skill=ChallengerSkill.ENTRY,
        risk_mode="balanced",
        configuration_fingerprint="context",
        baseline_version="baseline-v1.5",
        feature_schema_version="challenger-features-v5",
        qualified=True,
    )
    old_artifact = ChallengerSkillArtifact(**base)
    assert not _skill_qualified(old_artifact)
    updated = old_artifact.model_copy(
        update={"hyperparameters": {"entry_validation_version": ENTRY_VALIDATION_VERSION}}
    )
    assert _skill_qualified(updated)
    assert old_artifact.qualified  # Immutable historical qualification is retained.
    for skill in (ChallengerSkill.SIZING, ChallengerSkill.EXIT, ChallengerSkill.MANIPULATION):
        assert _skill_qualified(old_artifact.model_copy(update={"skill": skill}))
    assert _skill_qualified(
        old_artifact.model_copy(update={"schema_version": "challenger-skill-coach-v1"})
    )


@pytest.mark.parametrize("family", ["linear", "xgboost"])
def test_legacy_entry_cannot_restore_or_reactivate(progression, monkeypatch, family):  # noqa: F811
    learner, database, settings = progression
    old = artifact("legacy-entry", StatisticalModelFamily(family)).model_copy(
        update={
            "hyperparameters": {},
            "configuration_fingerprint": learner.configuration_fingerprint(),
        }
    )
    cohort = _challenger_cohort_key(
        old.risk_mode,
        old.configuration_fingerprint,
        old.baseline_version,
        old.feature_schema_version,
    )
    payload = b"{}" if family == "xgboost" else None
    if payload is not None:
        old.payload_format = "json"
        old.payload_digest = hashlib.sha256(payload).hexdigest()
    learner._register_skill_artifact(old, cohort, payload=payload)
    state = learner._current_skill_state(ChallengerSkill.ENTRY)
    state.champion_version = old.version
    state.active_version = old.version
    database.save_challenger_skill_state(state)
    database.set_setting("active_challenger_skills", {"entry": old.version})
    database.set_setting("learning_mode", LearningMode.ACTIVE.value)
    database.set_setting("challenger_consent_granted", True)
    # Even an available model and healthy current coverage cannot bypass provenance.
    monkeypatch.setattr(LearningEngine, "_load_nonlinear_artifact", lambda *args: object())
    restarted = LearningEngine(
        database, settings, configuration_fingerprint=learner.configuration_fingerprint
    )
    monkeypatch.setattr(restarted, "entry_outcome_availability", lambda: {"qualified": True})
    assert restarted.active_skill_versions == {}
    assert database.get_setting("active_challenger_skills") == {}
    assert restarted._skill_activation_candidate() is None
    with pytest.raises(ValueError, match="not eligible"):
        restarted._activate_skill(old)


@pytest.mark.parametrize(
    "role,old_label",
    [
        ("qualified", "proof_not_met"),
        ("queued", "proof_not_met"),
        ("testing", "proof_not_met"),
        ("active", "champion"),
        ("champion", "champion"),
        ("suspended", "suspended"),
    ],
)
def test_nonlinear_qualification_label_respects_current_validation(
    progression,  # noqa: F811
    role,
    old_label,
):
    learner, _, _ = progression
    legacy = artifact("legacy-status", StatisticalModelFamily.XGBOOST).model_copy(
        update={
            "hyperparameters": {},
            "configuration_fingerprint": learner.configuration_fingerprint(),
        }
    )
    learner.skill_artifacts[legacy.version] = legacy
    cohort = _challenger_cohort_key(
        legacy.risk_mode,
        legacy.configuration_fingerprint,
        legacy.baseline_version,
        legacy.feature_schema_version,
    )
    state = ChallengerSkillState(
        cohort_key=cohort,
        skill=ChallengerSkill.ENTRY,
        risk_mode=legacy.risk_mode,
        configuration_fingerprint=legacy.configuration_fingerprint,
        baseline_version=legacy.baseline_version,
        feature_schema_version=legacy.feature_schema_version,
    )
    if role in {"champion", "active", "suspended"}:
        state.champion_version = legacy.version
    if role == "queued":
        state.pending_versions = [legacy.version]
    elif role == "testing":
        state.testing_version = legacy.version
    elif role == "active":
        state.active_version = legacy.version
    elif role == "suspended":
        state.suspended_version = legacy.version
    learner.skill_states[(cohort, ChallengerSkill.ENTRY)] = state
    status = learner.nonlinear_entry_status()
    assert status["latest_artifact"]["qualified"] is False
    assert status["state"] == old_label
    current = legacy.model_copy(
        update={"hyperparameters": {"entry_validation_version": ENTRY_VALIDATION_VERSION}}
    )
    learner.skill_artifacts[current.version] = current
    assert learner.nonlinear_entry_status()["state"] == role
    assert legacy.qualified  # Preserve the immutable historical qualification.
