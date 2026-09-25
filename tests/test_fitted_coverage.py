"""Fitted coverage metadata describes evidence; it cannot change fitting or permissions."""

import copy
import json
from datetime import UTC, datetime

import pytest
from signal_arcade.diagnostics import artifact_summary
from signal_arcade.diagnostics_store import MAX_EVENT_PAYLOAD, decode, encode
from signal_arcade.intelligence.coverage import (
    COVERAGE_BUCKETS,
    coverage_breakdown,
    fitted_coverage_metrics,
    freeze_quote_failures,
)
from signal_arcade.intelligence.learning import _skill_artifact_summary
from signal_arcade.intelligence.training_job import TrainingOutput
from signal_arcade.models import ChallengerSkill, StatisticalModelFamily
from test_v1104_training_history import training_fixture


def test_frozen_cohort_counts_survive_live_mutation_and_restart(settings):
    learner, database, _ = training_fixture(settings, count=400)
    reasons = [
        ("executable_exit_quote_unavailable", "sell output exceeds real quote reserves"),
        ("executable_exit_quote_unavailable", "fees exceed sell proceeds"),
        ("executable_exit_quote_unavailable", "future quote failure"),
        ("executable_exit_quote_unavailable", None),
        ("stale_cached_route", None),
        ("checkpoint_window_elapsed", None),
        ("route_unavailable", None),
        (None, None),
    ]
    for index, (reason, quote) in enumerate(reasons):
        checkpoint = learner.observations[f"row-{index}"].checkpoints["300"]
        checkpoint.net_return = None
        checkpoint.missing_reason = reason
        checkpoint.route_snapshot = {"quote_failure_reason": quote, "bulky": "x" * 100000}
    expected = fitted_coverage_metrics(list(learner.observations.values()))
    assert expected == {
        "coverage_schema": 1,
        "coverage_resolved": 400,
        "coverage_usable": 392,
        "coverage_quote_liquidity": 1,
        "coverage_quote_fees": 1,
        "coverage_quote_other": 2,
        "coverage_stale_route": 1,
        "coverage_window_elapsed": 1,
        "coverage_other_missing": 2,
    }
    job = learner.prepare_next_training()
    assert job is not None
    assert b"bulky" not in b"".join(job.frozen_inputs)
    assert len(json.dumps(job.workspace._coverage_quote_failures)) < 500
    learner.observations["row-0"].checkpoints["300"].net_return = 0.9
    learner.observations["row-1"].checkpoints["300"].route_snapshot["quote_failure_reason"] = "new"
    learner.fit_training_job(job)
    assert learner.finish_training_job(job)
    artifacts = [
        a
        for a in database.list_challenger_artifacts()
        if a.skill in (ChallengerSkill.ENTRY, ChallengerSkill.MANIPULATION)
    ]
    assert len(artifacts) == 3
    assert {a.model_family for a in artifacts} == {
        StatisticalModelFamily.LINEAR,
        StatisticalModelFamily.XGBOOST,
    }
    for artifact in artifacts:
        assert {k: v for k, v in artifact.metrics.items() if k.startswith("coverage_")} == expected
        assert artifact.metrics["outcome_availability"] == 392 / 400
        assert artifact.sample_count == 392
        assert artifact.training_count + artifact.validation_count + artifact.embargoed_count == 392
        summary = _skill_artifact_summary(artifact)
        assert summary["coverage_breakdown"]["resolved"] == 400
        assert artifact_summary(artifact)["coverage"] == [1, 400, 392, 1, 1, 2, 1, 1, 2]
        assert len(json.dumps(artifact_summary(artifact)).encode()) < 2048
        event = {"kind": "proof", "at": 1800000000.0, **artifact_summary(artifact)}
        assert decode(encode(event, max_payload=MAX_EVENT_PAYLOAD)) == event
        legacy = artifact.model_copy(
            update={
                "metrics": {
                    k: v for k, v in artifact.metrics.items() if not k.startswith("coverage_")
                }
            }
        )
        old_summary = _skill_artifact_summary(legacy)
        assert old_summary["coverage_breakdown"] is None
        assert old_summary["qualified"] == summary["qualified"]
        assert (
            legacy.parameters == artifact.parameters
            and legacy.payload_digest == artifact.payload_digest
        )
    versions = [a.model_dump_json() for a in artifacts]
    path = database.path
    database.close()
    from signal_arcade.database import Database

    database = Database(path)
    assert [
        a.model_dump_json()
        for a in database.list_challenger_artifacts()
        if a.skill in (ChallengerSkill.ENTRY, ChallengerSkill.MANIPULATION)
    ] == versions
    database.close()


def valid_metrics():
    return {
        "coverage_schema": 1,
        "coverage_resolved": 1000,
        "coverage_usable": 430,
        "coverage_quote_liquidity": 305,
        "coverage_quote_fees": 8,
        "coverage_quote_other": 0,
        "coverage_stale_route": 251,
        "coverage_window_elapsed": 6,
        "coverage_other_missing": 0,
        "outcome_availability": 0.43,
    }


@pytest.mark.parametrize(
    "key,value",
    [
        ("coverage_schema", 2),
        ("coverage_resolved", 0),
        ("coverage_resolved", 1001),
        ("coverage_quote_fees", -1),
        ("coverage_usable", True),
        ("coverage_usable", 430.0),
        ("coverage_usable", None),
        ("coverage_other_missing", 1),
        ("outcome_availability", 0.70),
        ("outcome_availability", float("nan")),
        ("outcome_availability", float("inf")),
        ("outcome_availability", True),
    ],
)
def test_bad_or_future_reports_are_unknown_without_changing_metrics(key, value):
    metrics = valid_metrics()
    metrics[key] = value
    before = dict(metrics)
    assert coverage_breakdown(metrics, 430) is None
    assert metrics == before


def test_legacy_partial_and_wrong_generation_counts_are_unknown():
    assert coverage_breakdown({}, 430) is None
    metrics = valid_metrics()
    assert coverage_breakdown(metrics, 429) is None
    assert coverage_breakdown(metrics, 430)["quote_liquidity"] == 305
    for key in COVERAGE_BUCKETS:
        incomplete = dict(metrics)
        del incomplete[f"coverage_{key}"]
        assert coverage_breakdown(incomplete, 430) is None


def test_failure_classification_does_not_count_zero_or_losses_as_missing(settings):
    learner, database, _ = training_fixture(settings, count=100)
    observations = list(learner.observations.values())
    assert any(o.checkpoints["300"].net_return == 0 for o in observations)
    assert any(o.checkpoints["300"].net_return < 0 for o in observations)
    assert fitted_coverage_metrics(observations)["coverage_usable"] == 100
    assert freeze_quote_failures(observations) == {}
    database.close()


def test_reporting_metadata_cannot_change_fits_hashes_or_authority(settings, monkeypatch):
    from signal_arcade.intelligence import learning

    learner, database, _ = training_fixture(settings, count=400)
    job = learner.prepare_next_training()
    reference = copy.copy(job)
    reference.workspace = copy.copy(job.workspace)
    reference.workspace._training_output = TrainingOutput()
    now = datetime.now(UTC)

    class FixedTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(learning, "datetime", FixedTime)
    learner.fit_training_job(job)
    monkeypatch.setattr(learning, "fitted_coverage_metrics", lambda *args: {})
    learner.fit_training_job(reference)
    actual = job.workspace._training_output
    expected = reference.workspace._training_output
    assert actual.models == expected.models
    assert len(actual.artifacts) == len(expected.artifacts) == 3
    for (artifact, cohort, payload), (old, old_cohort, old_payload) in zip(
        actual.artifacts, expected.artifacts, strict=True
    ):
        clean = artifact.model_copy(
            update={
                "metrics": {
                    k: v for k, v in artifact.metrics.items() if not k.startswith("coverage_")
                }
            }
        )
        # Manipulation's created_at uses the model's wall-clock default factory;
        # generation IDs, cutoff, hashes, coefficients and all authority fields must match.
        assert clean.model_dump(exclude={"created_at"}) == old.model_dump(exclude={"created_at"})
        assert cohort == old_cohort and payload == old_payload
    assert database.list_learning_models() == []
    assert database.list_challenger_artifacts() == []
    database.close()
