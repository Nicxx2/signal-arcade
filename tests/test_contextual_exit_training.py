"""Train on the past, qualify on the held-out population, then require fresh battle proof."""

from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.intelligence.exit_context import RECIPE, load_policy
from signal_arcade.models import (
    DecisionAction,
    LearningCheckpoint,
    LearningEvidenceEpisode,
    LearningEvidenceLane,
    RiskMode,
)
from signal_arcade.strategy import BASELINE_VERSION
from test_exit_context import entry_features
from test_participation_progression import progression  # noqa: F401


def population(learner):
    start = datetime.now(UTC) - timedelta(days=3)
    rows = []
    for index in range(150):
        at = start + timedelta(minutes=20 * index)
        high = index % 2 == 0
        rows.append(
            LearningEvidenceEpisode(
                episode_id=f"row-{index}",
                idempotency_key=f"row-{index}",
                trajectory_key=f"row-{index}",
                lane=LearningEvidenceLane.POLICY,
                mint=f"mint-{index}",
                symbol="TEST",
                created_at=at,
                entry_at=at,
                risk_mode=RiskMode.BALANCED,
                baseline_version=BASELINE_VERSION,
                feature_schema_version="challenger-features-v5",
                baseline_action=DecisionAction.ENTER,
                baseline_actionable=True,
                qualification_eligible=True,
                configuration_fingerprint=learner.configuration_fingerprint(),
                features=entry_features(0.9 if high else 0.1),
                checkpoints={
                    str(h): LearningCheckpoint(
                        horizon_seconds=h, observed_at=at + timedelta(seconds=h), net_return=value
                    )
                    for h, value in (
                        (60, 0.3 if high else -0.1),
                        (300, -0.1 if high else 0.3),
                        (600, 0.0),
                    )
                },
            )
        )
    return rows


def publish(learner, monkeypatch, rows):
    # Substitute only the already selected Policy population; use the real split/fitter/queue.
    monkeypatch.setattr(learner, "_policy_evidence", lambda **kwargs: rows)
    learner._publish_exit_artifact(
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint=learner.configuration_fingerprint(),
        baseline_version=BASELINE_VERSION,
    )
    return next(a for a in reversed(learner.skill_artifacts.values()) if a.recipe_version == RECIPE)


def test_context_can_beat_constant_timing_without_auto_activating(progression, monkeypatch):  # noqa: F811
    learner, _, _ = progression
    artifact = publish(learner, monkeypatch, population(learner))
    assert artifact.qualified, artifact.qualification_reasons
    from signal_arcade.intelligence.learning import _skill_qualification_gates

    assert all(
        gate["state"] == "passed" for gate in _skill_qualification_gates(artifact.skill, artifact)
    )
    assert artifact.training_count == 100 and artifact.validation_count == 50
    assert artifact.metrics["reference_uplift_lower_bound"] > 0.01
    policy = load_policy(artifact)
    assert policy.select(entry_features(0.9))[0] == 60
    assert policy.select(entry_features(0.1))[0] == 300
    assert not learner.active_skill_versions


def test_validation_cannot_change_model_parameters(progression, monkeypatch):  # noqa: F811
    learner, _, _ = progression
    rows = population(learner)
    first = publish(learner, monkeypatch, rows)
    for row in rows[-50:]:
        row.checkpoints["60"].net_return *= -1
        row.checkpoints["300"].net_return *= -1
    learner.outcomes_seen += 1  # a second immutable publication gets its own identity
    second = publish(learner, monkeypatch, rows)
    assert first.parameters == second.parameters
    assert first.payload_digest == second.payload_digest
    assert not second.qualified


@pytest.mark.parametrize(("missing", "qualifies"), [(15, True), (16, False)])
def test_unavailable_validation_outcomes_remain_in_coverage(
    progression,  # noqa: F811
    monkeypatch,
    missing,
    qualifies,
):
    learner, _, _ = progression
    rows = population(learner)
    for row in rows[-missing:]:
        for checkpoint in row.checkpoints.values():
            checkpoint.net_return = None
            checkpoint.missing_reason = "unavailable_route"
    artifact = publish(learner, monkeypatch, rows)
    assert artifact.validation_count == 50
    assert artifact.metrics["validation_availability_fraction"] == (50 - missing) / 50
    assert artifact.qualified is qualifies


def test_missing_features_fail_familiarity_without_hiding_markets(progression, monkeypatch):  # noqa: F811
    learner, _, _ = progression
    rows = population(learner)
    for row in rows[-16:]:
        row.features.pop("momentum")
    artifact = publish(learner, monkeypatch, rows)
    assert not artifact.qualified
    assert artifact.metrics["validation_availability_fraction"] == 1.0
    assert artifact.metrics["in_distribution_fraction"] == 0.68


def test_late_training_outcome_is_embargoed(progression, monkeypatch):  # noqa: F811
    learner, _, _ = progression
    rows = population(learner)
    rows[99].checkpoints["600"].observed_at = rows[100].entry_at + timedelta(seconds=1)
    artifact = publish(learner, monkeypatch, rows)
    assert artifact.training_count == 99 and artifact.embargoed_count == 1
    assert artifact.training_cutoff_at == rows[100].entry_at


def test_constant_best_horizon_does_not_award_complexity(progression, monkeypatch):  # noqa: F811
    learner, _, _ = progression
    rows = population(learner)
    for row in rows:
        row.checkpoints["60"].net_return = 0.3
        row.checkpoints["300"].net_return = 0.1
    artifact = publish(learner, monkeypatch, rows)
    assert not artifact.qualified
    assert "contextual_reference_advantage" in artifact.qualification_reasons
