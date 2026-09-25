"""Prospective receipts, honest missingness and no activation authority."""

# ruff: noqa: F811 -- shared pytest fixture

from datetime import timedelta

import pytest
from pydantic import ValidationError
from signal_arcade.intelligence.activity_dataset import StudyDataset, spec_digest
from signal_arcade.intelligence.learning import _policy_identity_key
from signal_arcade.intelligence.support_research import SupportStudy, evaluate_support
from signal_arcade.models import ChallengerEvaluationReceipt, ChallengerSkill, LearningCheckpoint
from test_activity_research import cohort  # noqa: F401


def example(cohort, count=200):
    _, _, parent, old = cohort
    study = SupportStudy(
        **old.model_dump(
            exclude={
                "recipe",
                "minimum_changed",
                "configuration_fingerprint",
                "season_profile_fingerprint",
            }
        ),
        configuration_fingerprint="config",
        season_profile_fingerprint="profile",
        season_id="season",
        active_skill_versions={"manipulation": "frozen"},
        artifact_sha256="a" * 64,
        validation_rmse=0.4,
    )
    rows = []
    for i in range(count):
        at = study.start + (study.end - study.start) * ((i + 0.5) / count)
        row = parent.model_copy(
            deep=True,
            update={
                "episode_id": f"row-{i}",
                "mint": f"mint-{i}",
                "created_at": at,
                "entry_at": at,
                "configuration_fingerprint": "config",
                "season_profile_fingerprint": "profile",
                "season_id": "season",
                "active_skill_versions": {"manipulation": "frozen"},
            },
        )
        prediction = 0.2 if i % 2 else -0.2
        row.challenger_evaluations = {
            "frozen": ChallengerEvaluationReceipt(
                artifact_version="frozen",
                skill="manipulation",
                evaluated_at=at,
                prediction=prediction,
                conservative_value=prediction - 0.4,
                in_distribution=True,
                proposed_action="veto",
                baseline_actionable=True,
            )
        }
        row.checkpoints = {
            "300": LearningCheckpoint(
                horizon_seconds=300,
                observed_at=at + timedelta(seconds=300),
                net_return=0.5 if i % 2 else -0.5,
            )
        }
        rows.append(row)
    return study, rows


def bundle(study, rows, **changes):
    parents = [r.model_dump_json() for r in rows]
    return StudyDataset(
        spec_sha256=spec_digest(study),
        as_of=study.outcome_cutoff,
        source_schema=16,
        parents=parents,
        companions={},
        identities={_policy_identity_key(r): (r.entry_at.isoformat(), r.episode_id) for r in rows},
        metadata_rows_read=len(rows),
        parent_bytes=sum(len(p.encode()) for p in parents),
        pruned_through=None,
    ).model_copy(update=changes)


def test_positive_screen_still_cannot_activate_and_inputs_are_immutable(cohort):
    study, rows = example(cohort)
    data = bundle(study, rows)
    before = data.model_dump_json()
    report = evaluate_support(data, study)
    assert report["economic_screen_positive"] is True
    assert report["activation_allowed"] is False
    assert report["changed_usable"] == 100
    assert report["changed_usable_by_half"] == [50, 50]
    assert report["candidate_minus_reference"]["cash"]["mean"] == 0.25
    assert data.model_dump_json() == before


@pytest.mark.parametrize("case", ["clock", "version", "rmse", "action", "absent", "skill"])
def test_inconsistent_frozen_receipts_stay_unknown_in_denominator(cohort, case):
    study, rows = example(cohort)
    for row in rows:
        receipt = row.challenger_evaluations["frozen"]
        if case == "clock":
            receipt.evaluated_at += timedelta(seconds=1)
        elif case == "version":
            receipt.artifact_version = "later"
        elif case == "rmse":
            receipt.conservative_value = receipt.prediction - 0.2
        elif case == "action":
            receipt.proposed_action = "support"
        elif case == "skill":
            receipt.skill = ChallengerSkill.ENTRY
        else:
            row.challenger_evaluations.clear()
    report = evaluate_support(bundle(study, rows), study)
    assert report["counts"]["opportunities"] == 200
    assert report["receipt_availability"] == report["paired_coverage"] == 0
    assert not report["economic_screen_positive"]


@pytest.mark.parametrize("case", ["failed", "missing", "late", "future", "wrong_horizon"])
def test_unusable_outcomes_are_never_converted_to_returns(cohort, case):
    study, rows = example(cohort)
    for row in rows:
        checkpoint = row.checkpoints["300"]
        if case == "failed":
            checkpoint.net_return = None
            checkpoint.missing_reason = "executable_exit_quote_unavailable"
        elif case == "missing":
            row.checkpoints.clear()
        elif case == "late":
            checkpoint.observed_at = row.entry_at + timedelta(seconds=391)
        elif case == "wrong_horizon":
            checkpoint.horizon_seconds = 60
        else:
            checkpoint.observed_at = study.outcome_cutoff + timedelta(seconds=1)
    report = evaluate_support(bundle(study, rows), study)
    assert report["counts"]["opportunities"] == 200
    assert report["outcome_coverage"] == 0
    assert not report["economic_screen_positive"]


@pytest.mark.parametrize("case", ["retention", "identity", "immature", "context", "no_change"])
def test_incomplete_or_wrong_context_cannot_pass(cohort, case):
    study, rows = example(cohort)
    changes = {}
    if case == "retention":
        changes["pruned_through"] = '["' + study.start.isoformat() + '","removed"]'
    elif case == "identity":
        changes["identities"] = {}
    elif case == "immature":
        changes["as_of"] = study.outcome_cutoff - timedelta(seconds=1)
    elif case == "context":
        for row in rows:
            row.active_skill_versions["entry"] = "new"
    else:
        for row in rows:
            row.challenger_evaluations["frozen"].in_distribution = False
    report = evaluate_support(bundle(study, rows, **changes), study)
    assert not report["economic_screen_positive"]
    assert report["screen_blockers"]


def test_winners_and_losses_are_preserved_instead_of_labelled_manipulation(cohort):
    study, rows = example(cohort)
    for row in rows:
        row.checkpoints["300"].net_return = 0.5
    report = evaluate_support(bundle(study, rows), study)
    assert report["counts"]["candidate_missed_winners"] == 100
    assert report["candidate_winner_veto_fraction"] == 0.5
    assert not report["economic_screen_positive"]
    for row in rows:
        row.checkpoints["300"].net_return = -0.5
    report = evaluate_support(bundle(study, rows), study)
    assert report["counts"]["candidate_admitted_losses"] == 100
    assert report["candidate_minus_reference"]["cash"]["mean"] < 0
    assert not report["economic_screen_positive"]


@pytest.mark.parametrize(
    "change",
    [
        {"minimum_changed": 59},
        {"minimum_opportunities": 199},
        {"validation_rmse": float("nan")},
        {"selected_coverage_percent": 20},
        {"active_skill_versions": {}},
        {"artifact_sha256": "bad"},
    ],
)
def test_protocol_cannot_weaken_minima_or_use_invalid_context(cohort, change):
    study, _ = example(cohort)
    with pytest.raises(ValidationError):
        SupportStudy.model_validate({**study.model_dump(), **change})
