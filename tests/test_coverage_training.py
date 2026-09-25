"""Changing the proof requirement cannot change the fitted market population or predictions."""

import copy
import json
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.diagnostics import artifact_summary
from signal_arcade.intelligence import learning
from signal_arcade.intelligence.coverage_policy import CoveragePolicy, validation_current
from signal_arcade.intelligence.learning import _entry_qualification_gates, _skill_qualified
from signal_arcade.intelligence.training_job import TrainingOutput
from test_learning import qualified_model
from test_v1104_training_history import training_fixture


@pytest.mark.parametrize("percent", [55, 60, 65])
def test_real_fits_keep_rows_costs_predictions_and_noncoverage_gates(
    settings, monkeypatch, percent
):
    learner, database, _ = training_fixture(settings, count=600)
    for index in range(210):
        checkpoint = learner.observations[f"row-{index}"].checkpoints["300"]
        checkpoint.net_return = None
        checkpoint.missing_reason = "executable_exit_quote_unavailable"
        checkpoint.route_snapshot = {"quote_failure_reason": "fees exceed sell proceeds"}
    job = learner.prepare_next_training()
    assert job is not None
    changed = copy.copy(job)
    changed.workspace = copy.copy(job.workspace)
    changed.workspace._training_output = TrainingOutput()
    at = min(o.created_at for o in learner.observations.values()) - timedelta(seconds=1)
    changed.workspace.coverage_policy = CoveragePolicy(percent, 1, at)
    now = datetime.now(UTC)

    class FixedTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(learning, "datetime", FixedTime)
    learner.fit_training_job(job)
    learner.fit_training_job(changed)
    before, after = job.workspace._training_output, changed.workspace._training_output
    assert len(before.artifacts) == len(after.artifacts) == 3
    for (old, cohort, payload), (new, new_cohort, new_payload) in zip(
        before.artifacts, after.artifacts, strict=True
    ):
        assert new.parameters == old.parameters
        assert new.metrics == old.metrics
        assert (new_cohort, new_payload, new.payload_digest) == (
            cohort,
            payload,
            old.payload_digest,
        )
        assert new.training_count == old.training_count
        assert new.validation_count == old.validation_count
        assert new.evidence_cohort_digest == old.evidence_cohort_digest
        assert new.metrics["outcome_availability"] == 0.65
        assert new.metrics["coverage_quote_fees"] == 210
        assert new.hyperparameters["coverage_minimum_percent"] == percent
        assert validation_current(new)
        assert artifact_summary(new)["coverage_policy"]["percent"] == percent
        # These data lack actionable Policy proof; coverage alone must not qualify anything.
        assert not new.qualified and not old.qualified
    assert before.models[0].coefficients == after.models[0].coefficients
    assert not after.models[0].qualified
    assert not database.list_learning_models() and not database.list_challenger_artifacts()
    database.close()


@pytest.mark.parametrize("percent", [55, 65])
def test_real_fit_after_change_does_not_reuse_prechange_validation(settings, percent):
    learner, database, _ = training_fixture(settings, count=400)
    learner.set_coverage_policy(percent, 0)
    job = learner.prepare_next_training()
    assert job is not None
    learner.fit_training_job(job)
    assert job.workspace._training_output.artifacts
    for artifact, _, _ in job.workspace._training_output.artifacts:
        assert not validation_current(artifact) and not _skill_qualified(artifact)
        assert artifact.hyperparameters["coverage_fresh_validation"] is False
    assert not validation_current(job.workspace._training_output.models[0])
    database.close()


def test_malformed_legacy_proof_keeps_snapshot_json_safe():
    model = qualified_model("model", -0.2, 100)
    model.hyperparameters["coverage_minimum_percent"] = 65
    gates = _entry_qualification_gates(
        model,
        usable_outcomes=100,
        current_availability={
            "availability_fraction": 0.8,
            "minimum_fraction": 0.7,
            "observed_count": 100,
        },
        activation_available=False,
    )
    json.dumps(gates, allow_nan=False)
    coverage = next(g for g in gates if g["id"] == "model_outcome_availability")
    assert coverage["target"] is None and coverage["state"] == "not_met"
