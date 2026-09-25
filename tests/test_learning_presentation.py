"""Learning explanations must not mutate proof or grant trading authority."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.intelligence.coverage_policy import CoveragePolicy
from signal_arcade.intelligence.learning import (
    _entry_family_proof_gates,
    _skill_artifact_summary,
    _skill_qualified,
)
from signal_arcade.models import StatisticalModelFamily
from test_entry_proof_status import artifact


@pytest.mark.parametrize("family", [StatisticalModelFamily.LINEAR, StatisticalModelFamily.XGBOOST])
@pytest.mark.parametrize("percent", [60, 65, 70])
@pytest.mark.parametrize("fresh", [False, True])
def test_versioned_family_gate_ids_are_unique_without_changing_authority(family, percent, fresh):
    item = artifact(family=family)
    at = datetime(2026, 9, 19, tzinfo=UTC)
    item.hyperparameters.update(CoveragePolicy(percent, 1, at).metadata())
    item.hyperparameters["coverage_fresh_validation"] = fresh
    item.training_cutoff_at = at if fresh else at - timedelta(microseconds=1)
    before, qualified = item.model_dump_json(), _skill_qualified(item)
    gates = _entry_family_proof_gates(item)
    ids = [gate["id"] for gate in gates]
    assert len(ids) == len(set(ids))
    assert len(ids) == (15 if family == StatisticalModelFamily.XGBOOST else 14)
    assert next(g for g in gates if g["id"] == "entry_coverage_fresh_validation")["state"] == (
        "passed" if fresh else "not_met"
    )
    assert item.model_dump_json() == before
    assert _skill_qualified(item) == qualified
    json.dumps(gates, allow_nan=False)


@pytest.mark.parametrize("family", [StatisticalModelFamily.LINEAR, StatisticalModelFamily.XGBOOST])
@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"coverage_minimum_percent": 65},
        {
            "coverage_policy_version": "unknown",
            "coverage_minimum_percent": 60,
            "coverage_revision": 1,
            "coverage_effective_at": "2026-09-19T00:00:00Z",
        },
    ],
)
def test_legacy_and_unreadable_policy_keep_safe_unique_finite_gates(family, metadata):
    item = artifact(family=family)
    item.hyperparameters.update(metadata)
    before = item.model_dump_json()
    gates = _entry_family_proof_gates(item)
    ids = [g["id"] for g in gates]
    assert len(ids) == len(set(ids))
    assert ids.count("entry_coverage_fresh_validation") == bool(metadata)
    coverage = next(g for g in gates if g["id"] == "entry_outcome_availability")
    assert coverage["target"] == (None if metadata else 0.70)
    if metadata:
        assert coverage["state"] == "not_met"
        assert not _skill_qualified(item)
    assert item.model_dump_json() == before
    json.dumps(gates, allow_nan=False)


def test_missing_family_has_no_invented_proof():
    assert _entry_family_proof_gates(None) == []


@pytest.mark.parametrize("recorded", [False, True])
def test_artifact_summary_exposes_only_its_own_saved_period(recorded):
    item = artifact()
    if recorded:
        item.evidence_started_at = datetime(2026, 9, 18, tzinfo=UTC)
        item.evidence_ended_at = datetime(2026, 9, 19, tzinfo=UTC)
    before = item.model_dump_json()
    summary = _skill_artifact_summary(item)
    assert summary is not None
    assert summary["schema_version"] == item.schema_version
    assert summary["evidence_started_at"] == (
        item.evidence_started_at.isoformat() if recorded else None
    )
    assert summary["evidence_ended_at"] == (
        item.evidence_ended_at.isoformat() if recorded else None
    )
    assert summary["training_count"] == item.training_count
    assert summary["embargoed_count"] == item.embargoed_count
    assert item.model_dump_json() == before
