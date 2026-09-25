"""Explanations must preserve native decisions, independent proof and old receipts."""

import json
import math
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.intelligence.learning import (
    FEATURE_SCHEMA_VERSION,
    MANIPULATION_FEATURE_NAMES,
    LearningEngine,
    _challenger_cohort_key,
    _policy_identity_key,
)
from signal_arcade.intelligence.training_job import freeze_training_inputs
from signal_arcade.models import (
    ChallengerEvaluationReceipt,
    ChallengerSkill,
    ChallengerSkillArtifact,
    ChallengerSkillState,
    DecisionAction,
    RiskMode,
    StatisticalModelFamily,
)
from signal_arcade.strategy import BASELINE_VERSION
from test_learning import make_decision, make_state

NOW = datetime(2026, 9, 20, 10, tzinfo=UTC)


@pytest.fixture
def active(settings, monkeypatch):
    db = Database(settings.database_path)
    learner = LearningEngine(db, settings, configuration_fingerprint=lambda: "evidence-test")
    width = len(MANIPULATION_FEATURE_NAMES)
    artifact = ChallengerSkillArtifact(
        version="evidence-champion",
        skill=ChallengerSkill.MANIPULATION,
        created_at=NOW - timedelta(days=1),
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="evidence-test",
        baseline_version=BASELINE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        feature_names=list(MANIPULATION_FEATURE_NAMES),
        parameters={
            "means": [0.0] * width,
            "scales": [1.0] * width,
            "coefficients": [-0.2, *([0.0] * width)],
        },
        metrics={"validation_rmse": 0.05},
        qualified=True,
    )
    cohort = _challenger_cohort_key(
        RiskMode.BALANCED, "evidence-test", BASELINE_VERSION, FEATURE_SCHEMA_VERSION
    )
    state = ChallengerSkillState(
        cohort_key=cohort,
        skill=artifact.skill,
        risk_mode=artifact.risk_mode,
        configuration_fingerprint=artifact.configuration_fingerprint,
        baseline_version=artifact.baseline_version,
        feature_schema_version=artifact.feature_schema_version,
        champion_version=artifact.version,
        active_version=artifact.version,
    )
    learner.skill_artifacts[artifact.version] = artifact
    learner.skill_states[(cohort, artifact.skill)] = state
    learner.active_skill_versions[artifact.skill.value] = artifact.version
    # Isolate receipt/action behavior. Existing lifecycle tests cover proof and activation.
    monkeypatch.setattr(learner, "_skill_eligible", lambda _: True)
    yield learner, artifact, db
    db.close()


def decision(at=NOW):
    result = make_decision(at, "evidence-mint")
    result.configuration_fingerprint = "evidence-test"
    return result


@pytest.mark.parametrize("scale,applied", [(1.0, True), (0.001, False)])
@pytest.mark.parametrize("actionable", [True, False])
def test_annotations_do_not_change_actions_predictions_or_size(
    active, monkeypatch, scale, applied, actionable
):
    learner, artifact, _ = active
    index = artifact.feature_names.index("repetition")
    artifact.parameters["scales"][index] = scale
    original = decision()
    result = learner._assess_active_skills(original, baseline_actionable=actionable)
    receipt = result.challenger_assessments["manipulation"]
    assert receipt["parameters"]["applied"] is (applied and actionable)
    if not applied:
        p = receipt["parameters"]
        assert p["support_reason"] == "outside_feature_support"
        assert p["support_feature"] == "repetition"
        assert p["support_feature_z"] == pytest.approx(100)
        assert p["support_failed_feature_count"] == 1
        assert result.action == DecisionAction.ENTER  # No new sticky veto.
    monkeypatch.setattr(learner, "_support_evidence", lambda *_a, **_k: {})
    monkeypatch.setattr(learner, "_decision_policy_origin", lambda *_: {})
    previous = learner._assess_active_skills(original, baseline_actionable=actionable)
    # Everything except additive audit parameters must remain byte-for-byte equivalent.
    result.challenger_assessments["manipulation"]["parameters"] = {
        "applied": applied and actionable
    }
    assert result.model_dump_json() == previous.model_dump_json()


@pytest.mark.parametrize("value", [-6.00001, -6, 0, 6, 6.00001, math.nan, math.inf])
@pytest.mark.parametrize("family", [StatisticalModelFamily.LINEAR, StatisticalModelFamily.XGBOOST])
def test_support_boundary_and_nonfinite_values_do_not_fabricate_feature_causes(
    active, monkeypatch, value, family
):
    learner, artifact, _ = active
    artifact.model_family = family
    monkeypatch.setattr(learner, "_load_nonlinear_artifact", lambda _: object())
    features = dict.fromkeys(artifact.feature_names, 0.0)
    features["repetition"] = value
    supported = learner._artifact_in_support(artifact, features)
    assert supported == (math.isfinite(value) and abs(value) <= 6)
    detail = learner._support_evidence(artifact, features, supported=supported)
    assert detail["support_reason"] == (
        "within_support" if supported else "outside_feature_support"
    )
    json.dumps(detail, allow_nan=False)  # Optional evidence cannot poison receipt serialization.
    assert len(json.dumps(detail)) < 1024


def test_payload_failure_not_reported_as_market_outlier_and_no_reload(active, monkeypatch):
    learner, artifact, _ = active
    artifact.model_family = StatisticalModelFamily.XGBOOST
    features = dict.fromkeys(artifact.feature_names, 0.0)
    monkeypatch.setattr(
        learner, "_load_nonlinear_artifact", lambda _: pytest.fail("extra model load")
    )
    detail = learner._support_evidence(artifact, features, supported=False)
    assert detail["support_reason"] == "nonlinear_payload_unavailable"
    assert "support_feature" not in detail
    artifact.parameters["scales"][0] = 0
    assert learner._support_evidence(artifact, features, supported=False)["support_reason"] == (
        "invalid_support_parameters"
    )


def test_freeze_origin_retry_restart_pruning_and_old_receipt_compatibility(active, settings):
    learner, artifact, db = active
    original = decision()
    assert learner.register(
        original, make_state(original.mint), live=True, evaluation_actionable=True
    )
    episode = next(iter(learner.evidence_episodes.values()))
    saved = episode.model_dump_json()
    first = learner._decision_policy_origin(original)
    assert first["policy_origin_relation"] == "original_decision"
    later = decision(NOW + timedelta(minutes=20))
    later.decision_id = "later-attempt"
    assert learner._decision_policy_origin(later)["policy_origin_relation"] == "later_attempt"
    assert learner._decision_policy_origin(later)["policy_origin_episode_id"] == episode.episode_id
    restarted = LearningEngine(db, settings, configuration_fingerprint=lambda: "evidence-test")
    assert restarted._decision_policy_origin(later) == learner._decision_policy_origin(later)
    learner.evidence_episodes.pop(episode.episode_id)
    assert learner._decision_policy_origin(later)["policy_origin_relation"] == "later_attempt"
    learner._policy_identities.clear()
    assert learner._decision_policy_origin(later) == {"policy_origin_status": "unavailable"}
    stored = db.list_learning_evidence_episodes()[0]
    assert stored.model_dump_json() == saved
    receipt = stored.challenger_evaluations[artifact.version]
    assert receipt.parameters["support_reason"] == "within_support"
    assert "applied" not in receipt.parameters  # Frozen proof is not an executed veto.
    legacy = receipt.model_dump()
    legacy["parameters"] = {}
    assert ChallengerEvaluationReceipt.model_validate(legacy).in_distribution is True
    assert ChallengerEvaluationReceipt.model_validate_json(receipt.model_dump_json()) == receipt


def test_identity_context_future_clocks_and_same_time_retry_stay_separate(active):
    learner, _, _ = active
    original = decision()
    learner.register(original, make_state(original.mint), live=True, evaluation_actionable=True)
    episode = next(iter(learner.evidence_episodes.values()))
    key = _policy_identity_key(episode)
    changed = original.model_copy(update={"configuration_fingerprint": "different"})
    assert learner._decision_policy_origin(changed)["policy_origin_status"] == "unavailable"
    retry = original.model_copy(update={"decision_id": "other-same-time"})
    assert (
        learner._decision_policy_origin(retry)["policy_origin_relation"] == "same_time_unconfirmed"
    )
    for clock in ("bad", "2026-09-20T10:00:00", (NOW + timedelta(seconds=1)).isoformat()):
        learner._policy_identities[key] = (clock, episode.episode_id)
        assert learner._decision_policy_origin(original) == {
            "policy_origin_status": "invalid_clock"
        }


def test_replacement_does_not_inherit_any_sticky_veto(active):
    learner, artifact, _ = active
    first = learner._assess_active_skills(decision(), baseline_actionable=True)
    assert first.action == DecisionAction.PASS
    artifact.parameters["coefficients"][0] = 0.2
    next_decision = learner._assess_active_skills(
        decision(NOW + timedelta(seconds=1)), baseline_actionable=True
    )
    assert next_decision.action == DecisionAction.ENTER
    assert next_decision.challenger_assessments["manipulation"]["proposed_action"] == "support"


@pytest.mark.parametrize("parameter", ["means", "scales", "coefficients"])
@pytest.mark.parametrize("invalid", [[], [math.nan], [0.0]])
def test_invalid_linear_shapes_are_not_described_as_market_outliers(active, parameter, invalid):
    learner, artifact, _ = active
    artifact.parameters[parameter] = invalid
    detail = learner._support_evidence(artifact, {}, supported=False)
    assert detail["support_reason"] == "invalid_support_parameters"
    assert "support_feature" not in detail


def test_small_scale_floor_missing_operand_and_multiple_failures_are_bounded(active):
    learner, artifact, _ = active
    artifact.parameters["scales"] = [1e-12] * len(artifact.feature_names)
    # The deployed support rule uses max(scale, 1e-6); explanation must use that same floor.
    features = dict.fromkeys(artifact.feature_names, 0.0)
    features["danger"] = 6e-6
    assert learner._artifact_in_support(artifact, features)
    features["danger"] = 7e-6
    features["repetition"] = 8e-6
    detail = learner._support_evidence(artifact, features, supported=False)
    assert detail["support_feature_z"] == pytest.approx(7)
    assert detail["support_failed_feature_count"] == 2
    artifact.parameters["means"][0] = 1.0
    del features["danger"]
    detail = learner._support_evidence(artifact, features, supported=False)
    assert detail["support_feature_present"] is False


def test_optional_origin_does_not_query_or_claim_reused_parent_is_original(active, monkeypatch):
    learner, _, db = active
    original = decision()
    learner.register(original, make_state(original.mint), live=True, evaluation_actionable=True)
    episode = next(iter(learner.evidence_episodes.values()))
    later = decision(NOW + timedelta(minutes=10))
    later.decision_id = "replacement-after-pruning"
    # Same primary key, later clock: persistent first identity still owns the opportunity.
    learner.evidence_episodes[episode.episode_id] = episode.model_copy(
        update={"entry_at": later.created_at, "decision_id": later.decision_id}
    )
    monkeypatch.setattr(
        db, "policy_identities", lambda *_: pytest.fail("per-attempt database query")
    )
    detail = learner._decision_policy_origin(later)
    assert detail["policy_origin_relation"] == "later_attempt"
    assert datetime.fromisoformat(detail["policy_origin_at"]) == original.created_at


def test_coach_support_failure_is_not_a_statistical_outlier(active):
    learner, artifact, _ = active
    artifact.parameters["coach_policy"] = {"kind": "entry_veto", "conditions": []}
    detail = learner._support_evidence(artifact, {}, supported=False)
    assert detail["support_reason"] == "coach_support_unavailable"
    assert "support_feature" not in detail


def test_receipt_metadata_never_changes_training_copy_or_artifact(active):
    learner, artifact, _ = active
    before_artifact = artifact.model_dump_json()
    original = decision()
    learner.register(original, make_state(original.mint), live=True, evaluation_actionable=True)
    inputs = (
        list(learner.observations.values()),
        list(learner.evidence_episodes.values()),
        [],
        [artifact],
        list(learner.skill_states.values()),
    )
    annotated = freeze_training_inputs(inputs)
    for parent in [*inputs[0], *inputs[1]]:
        for receipt in parent.challenger_evaluations.values():
            receipt.parameters.clear()
    assert freeze_training_inputs(inputs) == annotated
    assert b"support_evidence_version" not in b"".join(annotated)
    assert artifact.model_dump_json() == before_artifact
