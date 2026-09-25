"""Research must preserve first opportunities, missingness, fees and honest outcome signs."""

from datetime import timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.intelligence.activity_evidence import capture_activity
from signal_arcade.intelligence.activity_research import (
    ActivityStudy,
    evaluate_activity,
    proposed_veto,
    read_study,
)
from signal_arcade.intelligence.learning import LearningEngine, _policy_identity
from signal_arcade.models import LearningCheckpoint, RiskMode
from test_activity_companions import full_decision
from test_activity_evidence import NOW
from test_learning import data, make_decision, make_state


@pytest.fixture
def cohort(settings):
    db = Database(settings.database_path)
    learner = LearningEngine(db, settings)
    decision = make_decision(NOW, "example")
    state = make_state("example")
    learner.register(decision, state, live=True, evaluation_actionable=True)
    episode = next(iter(learner.evidence_episodes.values()))
    spec = ActivityStudy(
        frozen_at=NOW - timedelta(days=1),
        start=NOW - timedelta(hours=1),
        end=NOW + timedelta(hours=1),
        outcome_cutoff=NOW + timedelta(hours=2),
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint=episode.configuration_fingerprint,
        baseline_version=episode.baseline_version,
        season_profile_fingerprint=episode.season_profile_fingerprint,
        fee_bps=episode.fee_bps,
        network_fee_lamports=episode.checkpoint_network_fee_lamports,
        venue=episode.venue,
        quote_mint=episode.quote_mint,
        selected_coverage_percent=55,
    )
    yield db, learner, episode, spec
    db.close()


def pattern(parent):
    decision = full_decision(parent.mint)
    decision.decision_id = parent.decision_id
    decision.created_at = parent.created_at
    for name, value in {
        "buy_ratio_5m": 0.8,
        "buy_quote_volume_ratio_5m": 0.4,
        "signed_net_quote_flow_ratio_5m": -0.2,
        "meaningful_trade_count_1m": 2,
        "net_buy_wallet_count_5m": 2,
        "trade_count_5m": 40,
        "age_seconds": 90,
    }.items():
        decision.feature_snapshot.values[name] = data(parent.created_at, value)
    return capture_activity(parent, decision, parent.quote_mint)


def outcome(parent, value, reason=None):
    parent.checkpoints["300"] = LearningCheckpoint(
        horizon_seconds=300,
        observed_at=parent.entry_at + timedelta(seconds=300),
        net_return=value,
        missing_reason=reason,
    )


def test_profitable_suspicious_pattern_is_a_missed_winner_not_fabricated_success(cohort):
    _, _, parent, spec = cohort
    record = pattern(parent)
    assert proposed_veto(record) is True
    hashes = []
    for value, delta, bucket in ((0.4, -0.4, "missed_winners"), (-0.3, 0.3, "avoided_losses")):
        outcome(parent, value)
        report = evaluate_activity(
            spec,
            [parent],
            {},
            {parent.episode_id: record.model_dump_json()},
            as_of=spec.outcome_cutoff,
        )
        assert report["paired_mean_300s_return_delta"] == delta
        assert report["counts"][bucket] == 1
        assert report["activation_allowed"] is False
        assert report["sufficient_for_economic_screen"] is False
        assert report["original_integrity_states"] == {"clean": 1}
        hashes.append(report["dataset_sha256"])
    assert hashes[0] != hashes[1]
    assert record.integrity.state.value == "clean"  # Outcome never rewrites original assessment.


@pytest.mark.parametrize("unavailable", ["absent", "malformed", "stale", "partial", "identity"])
def test_unknown_evidence_keeps_baseline_and_denominator(cohort, unavailable):
    _, _, parent, spec = cohort
    outcome(parent, -0.5)
    record = pattern(parent)
    if unavailable == "stale":
        record = record.model_copy(update={"clocks": [NOW - timedelta(seconds=2)]})
    elif unavailable == "partial":
        record.metrics["known_wallet_trade_coverage"] = (None, 0, None, "unknown")
        record = record.model_copy(update={"status": "partial"})
    elif unavailable == "identity":
        record = record.model_copy(update={"parent_id": "different-parent"})
    records = (
        {}
        if unavailable == "absent"
        else {parent.episode_id: record.model_dump_json() if unavailable != "malformed" else "{}"}
    )
    report = evaluate_activity(spec, [parent], {}, records, as_of=spec.outcome_cutoff)
    assert report["counts"]["opportunities"] == 1
    assert report["counts"]["feature_unknown"] == 1
    assert report["paired_mean_300s_return_delta"] == 0
    assert report["outcome_coverage"] == 1
    assert report["feature_availability"] == 0


def test_first_failed_or_missing_policy_cannot_be_replaced_by_later_success(cohort):
    _, _, first, spec = cohort
    outcome(first, None, "executable_exit_quote_unavailable")
    later = first.model_copy(
        deep=True, update={"episode_id": "later", "entry_at": NOW + timedelta(minutes=5)}
    )
    outcome(later, 0.9)
    identity = _policy_identity(first)
    report = evaluate_activity(
        spec, [later, first], {identity[0]: identity[1:]}, {}, as_of=spec.outcome_cutoff
    )
    assert report["counts"]["opportunities"] == 1
    assert report["counts"]["quote_failure"] == 1
    assert report["outcome_coverage"] == 0
    assert report["paired_mean_300s_return_delta"] is None
    # Once the original is pruned, its reservation still excludes the retry.
    report = evaluate_activity(
        spec, [later], {identity[0]: identity[1:]}, {}, as_of=spec.outcome_cutoff
    )
    assert report["outcome_coverage"] is None
    assert not report["economic_screen_positive"]


def test_spec_chronology_fee_context_cutoff_and_digest(cohort):
    _, _, parent, spec = cohort
    with pytest.raises(ValueError):
        ActivityStudy.model_validate({**spec.model_dump(), "frozen_at": spec.start})
    outcome(parent, -0.2)
    record = pattern(parent)
    report = evaluate_activity(
        spec, [parent], {}, {parent.episode_id: record.model_dump_json()}, as_of=NOW
    )
    assert report["counts"]["outside_outcome_clock"] == 1
    assert not report["sufficient_for_economic_screen"]
    parent.fee_bps += 1
    assert evaluate_activity(spec, [parent], {}, {}, as_of=spec.outcome_cutoff)["counts"] == {
        "context_excluded": 1
    }


def test_offline_reader_never_migrates_or_writes(cohort):
    db, _, parent, spec = cohort
    before = db._conn.total_changes
    report = read_study(db.path, spec)
    assert report["read_limits"]["rows_read"] == 1
    assert report["counts"]["pending_or_no_checkpoint"] == 1
    assert db._conn.total_changes == before
    assert not report["activation_allowed"]


def test_selection_cap_cannot_look_like_complete_prospective_evidence(cohort):
    _, _, prototype, spec = cohort
    rows = []
    for i in range(1001):
        row = prototype.model_copy(
            deep=True, update={"episode_id": f"policy-{i:04}", "mint": f"mint-{i}"}
        )
        rows.append(row)
    report = evaluate_activity(spec, rows, {}, {}, as_of=spec.outcome_cutoff)
    assert report["counts"]["opportunities"] == 1000
    assert report["selection_at_limit"] is True
    assert report["retention_completeness"] == "not_certified"
    assert not report["sufficient_for_economic_screen"]


def test_sol_cutoff_cannot_be_applied_to_other_quote_currency(cohort):
    _, _, _, spec = cohort
    with pytest.raises(ValueError, match="SOL"):
        ActivityStudy.model_validate({**spec.model_dump(), "quote_mint": "different-currency"})


def test_later_traffic_cannot_displace_a_frozen_study_cohort(cohort):
    _, _, parent, spec = cohort
    outcome(parent, -0.2)
    companions = {parent.episode_id: pattern(parent).model_dump_json()}
    expected = evaluate_activity(spec, [parent], {}, companions, as_of=spec.outcome_cutoff)
    later = [
        parent.model_copy(
            deep=True,
            update={
                "episode_id": f"future-{i:04}",
                "mint": f"future-{i}",
                "entry_at": spec.end + timedelta(seconds=i),
            },
        )
        for i in range(1001)
    ]
    actual = evaluate_activity(spec, [*later, parent], {}, companions, as_of=spec.outcome_cutoff)
    assert actual == expected


@pytest.mark.parametrize("horizon,seconds", [(60, 300), (600, 600), (300, 299.999), (300, 390.001)])
def test_malformed_primary_checkpoint_is_not_usable_economic_proof(cohort, horizon, seconds):
    _, _, parent, spec = cohort
    outcome(parent, -0.8)
    parent.checkpoints["300"].horizon_seconds = horizon
    parent.checkpoints["300"].observed_at = parent.entry_at + timedelta(seconds=seconds)
    report = evaluate_activity(
        spec,
        [parent],
        {},
        {parent.episode_id: pattern(parent).model_dump_json()},
        as_of=spec.outcome_cutoff,
    )
    assert report["counts"]["opportunities"] == 1
    assert report["counts"]["invalid_primary_checkpoint"] == 1
    assert report["outcome_coverage"] == 0
    assert report["paired_mean_300s_return_delta"] is None


@pytest.mark.parametrize("seconds", [300, 390])
def test_valid_primary_checkpoint_window_includes_its_boundaries(cohort, seconds):
    _, _, parent, spec = cohort
    outcome(parent, -0.8)
    parent.checkpoints["300"].observed_at = parent.entry_at + timedelta(seconds=seconds)
    report = evaluate_activity(spec, [parent], {}, {}, as_of=spec.outcome_cutoff)
    assert report["outcome_coverage"] == 1


def test_expired_unknown_checkpoint_retains_its_missing_outcome(cohort):
    _, _, parent, spec = cohort
    outcome(parent, None, "checkpoint_window_elapsed")
    parent.checkpoints["300"].observed_at = parent.entry_at + timedelta(seconds=450)
    report = evaluate_activity(spec, [parent], {}, {}, as_of=spec.outcome_cutoff)
    assert report["counts"]["other_missing_outcome"] == 1
    assert report["outcome_coverage"] == 0


def test_pre_study_history_cap_does_not_falsely_mark_the_study_truncated(cohort):
    _, _, parent, spec = cohort
    rows = [parent]
    for i in range(1001):
        rows.append(
            parent.model_copy(
                deep=True,
                update={
                    "episode_id": f"old-{i:04}",
                    "mint": f"old-{i}",
                    "entry_at": spec.start - timedelta(seconds=i + 1),
                },
            )
        )
    report = evaluate_activity(spec, rows, {}, {}, as_of=spec.outcome_cutoff)
    assert report["counts"]["opportunities"] == 1
    assert report["selection_at_limit"]
    assert not report["study_selection_may_be_truncated"]
    # Keep the first independent opportunity even when it predates the period. Filtering
    # at the start before independence selection would incorrectly admit the later retry.
    earlier = parent.model_copy(
        deep=True,
        update={
            "episode_id": "earlier-same-mint",
            "entry_at": spec.start - timedelta(seconds=1),
        },
    )
    report = evaluate_activity(spec, [earlier, parent], {}, {}, as_of=spec.outcome_cutoff)
    assert report["outcome_coverage"] is None


def test_oversized_companion_is_unknown_without_hiding_the_parent(cohort):
    db, _, parent, spec = cohort
    # Disposable corrupted/imported fixture bypasses the normal writer's byte constraint.
    db._conn.execute("PRAGMA ignore_check_constraints=ON")
    with db._conn:
        db._conn.execute("UPDATE learning_activity_policy SET record_json=?", ("x" * 10000,))
    report = read_study(db.path, spec)
    assert report["counts"]["opportunities"] == 1
    assert report["counts"]["companion_invalid"] == 1
    assert report["feature_availability"] == 0


def test_oversized_parent_aborts_read_without_partial_evidence(cohort, monkeypatch):
    import sqlite3

    from signal_arcade.intelligence import activity_research

    db, _, parent, spec = cohort
    monkeypatch.setattr(activity_research, "MAX_STUDY_PARENT_BYTES", 4096)
    with db._conn:
        oversized = parent.model_copy(update={"symbol": "x" * 10000})
        db._conn.execute(
            "UPDATE learning_evidence_episodes SET record_json=?", (oversized.model_dump_json(),)
        )
    with pytest.raises(sqlite3.DataError, match="too big"):
        read_study(db.path, spec)


def test_complete_but_stale_record_is_not_usable_feature_evidence(cohort):
    _, _, parent, spec = cohort
    record = pattern(parent).model_copy(update={"clocks": [NOW - timedelta(seconds=2)]})
    outcome(parent, -0.5)
    report = evaluate_activity(
        spec, [parent], {}, {parent.episode_id: record.model_dump_json()}, as_of=spec.outcome_cutoff
    )
    assert report["recorded_companions"] == 1
    assert report["valid_companion_statuses"] == {"complete": 1}
    assert report["feature_unknown_reasons"] == {"stale_or_future_metric": 1}
    assert report["feature_availability"] == 0
    assert report["changed_fraction"] == 0
    assert "insufficient_feature_availability" in report["screen_blockers"]


@pytest.mark.parametrize("value", [-0.5, 0, 0.5])
def test_no_matching_pattern_is_inconclusive_even_with_many_usable_outcomes(cohort, value):
    _, _, prototype, spec = cohort
    rows, companions = [], {}
    for i in range(200):
        parent = prototype.model_copy(deep=True, update={"episode_id": str(i), "mint": str(i)})
        record = pattern(parent)
        record.metrics["buy_ratio_5m"] = (0.5, 1.0, 0, None)
        outcome(parent, value)
        rows.append(parent)
        companions[parent.episode_id] = record.model_dump_json()
    report = evaluate_activity(spec, rows, {}, companions, as_of=spec.outcome_cutoff)
    assert report["outcome_coverage"] == 1
    assert report["feature_availability"] == 1
    assert report["pattern_observed"] is False
    assert report["screen_blockers"] == ["insufficient_changed_usable_outcomes"]
    assert not report["sufficient_for_economic_screen"]
    assert not report["economic_screen_positive"]


def test_zero_opportunities_and_no_positive_outcomes_cannot_claim_success(cohort):
    _, _, parent, spec = cohort
    empty = evaluate_activity(spec, [], {}, {}, as_of=spec.outcome_cutoff)
    assert empty["outcome_coverage"] is None
    assert empty["winner_veto_fraction"] is None
    assert not empty["economic_screen_positive"]
    rows, companions = [], {}
    for i in range(200):
        row = parent.model_copy(deep=True, update={"episode_id": str(i), "mint": str(i)})
        outcome(row, -0.5)
        rows.append(row)
        companions[row.episode_id] = pattern(row).model_dump_json()
    report = evaluate_activity(spec, rows, {}, companions, as_of=spec.outcome_cutoff)
    assert report["sufficient_for_economic_screen"]
    assert report["winner_veto_fraction"] is None
    assert not report["economic_screen_positive"]
    assert not report["activation_allowed"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("venue", "other_venue"),
        ("quote_mint", "other_quote"),
        ("entry_at", NOW + timedelta(seconds=1)),
    ],
)
def test_companion_requires_policy_route_and_original_entry_time(cohort, field, value):
    from signal_arcade.intelligence.activity_evidence import read_activity

    _, _, parent, _ = cohort
    payload = pattern(parent).model_dump_json()
    changed_parent = parent.model_copy(update={field: value})
    with pytest.raises(ValueError, match="mismatch"):
        read_activity(payload, changed_parent)


def test_extreme_numeric_payload_is_unknown_research_not_a_crash(cohort):
    import json

    _, _, parent, spec = cohort
    record = pattern(parent).model_dump(mode="json")
    record["metrics"]["trade_count_5m"][0] = 10**500
    payload = json.dumps(record, separators=(",", ":"))
    assert len(payload.encode()) < 4096
    report = evaluate_activity(
        spec, [parent], {}, {parent.episode_id: payload}, as_of=spec.outcome_cutoff
    )
    assert report["counts"]["companion_invalid"] == 1
    assert report["counts"]["opportunities"] == 1
