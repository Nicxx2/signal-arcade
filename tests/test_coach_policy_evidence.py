"""Forward research follows first actionable Policy identities, not Discovery guesses."""

import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.coach import AiCoach, _evaluate_policy_hypothesis
from signal_arcade.config import Settings
from signal_arcade.database import AdvisoryReadDeferred
from signal_arcade.intelligence.learning import FEATURE_SCHEMA_VERSION, LearningEngine
from signal_arcade.models import (
    ChallengerSkill,
    CoachExperimentKind,
    CoachExperimentState,
    DecisionAction,
    LearningEvidenceStatus,
)
from signal_arcade.strategy import BASELINE_VERSION
from test_coach import FakeCoachHttp, _hypothesis
from test_learning import make_decision, make_state
from test_participation_progression import progression, record_policy  # noqa: F401


def study(learner, cutoff, kind=CoachExperimentKind.SIZING_MULTIPLIER):
    return _hypothesis(cutoff).model_copy(
        update={
            "evidence_contract": "policy-v1",
            "kind": kind,
            "skill": ChallengerSkill(
                {
                    "entry_veto": "entry",
                    "manipulation_veto": "manipulation",
                    "sizing_multiplier": "sizing",
                    "earlier_review": "exit",
                }[kind.value]
            ),
            "configuration_fingerprint": learner.configuration_fingerprint(),
            "baseline_version": BASELINE_VERSION,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "size_multiplier": 0.5,
            "threshold": 1.0,
            "hold_seconds": 300,
            "baseline_hold_seconds": 600,
        }
    )


def seed_policy_study(database, count=30):
    database.set_setting("demo_mode", False)
    learner = LearningEngine(
        database, Settings(database_path=database.path), configuration_fingerprint=lambda: "fp"
    )
    cutoff = datetime.now(UTC) - timedelta(hours=2)
    for index in range(count):
        record_policy(learner, f"policy-{index}", cutoff + timedelta(minutes=1, seconds=index))
    return study(learner, cutoff)


def evaluate(database, hypothesis, now, limit=64):
    rows, identities, cursor, gap = database.coach_policy_page(hypothesis, limit=limit)
    return _evaluate_policy_hypothesis(hypothesis, rows, identities, cursor, gap, now)


@pytest.mark.parametrize("kind", list(CoachExperimentKind))
def test_later_actionable_policy_counts_after_discovery_pass(progression, kind):  # noqa: F811
    learner, database, _ = progression
    cutoff = datetime.now(UTC) - timedelta(hours=2)
    decision = make_decision(cutoff - timedelta(minutes=1), "later").model_copy(
        update={
            "action": DecisionAction.PASS,
            "configuration_fingerprint": learner.configuration_fingerprint(),
        }
    )
    assert learner.register(decision, make_state("later"), live=True)
    episode = record_policy(learner, "later", cutoff + timedelta(seconds=1))
    assert learner.observations["later"].baseline_action == DecisionAction.PASS
    hypothesis = study(learner, cutoff, kind)
    updated = evaluate(database, hypothesis, datetime.now(UTC))
    assert updated.forward_observed_count == 1
    assert updated.forward_usable_count == 1
    assert updated.forward_observation_ids == [episode.episode_id]
    assert updated.influence_applied is False
    database.save_coach_hypothesis(updated)
    restored = database.coach_hypothesis(updated.hypothesis_id)
    assert evaluate(database, restored, datetime.now(UTC)).forward_observed_count == 1


def test_pending_prefix_cannot_be_skipped_by_later_success(progression):  # noqa: F811
    learner, database, _ = progression
    cutoff = datetime.now(UTC) - timedelta(minutes=2)
    first = record_policy(learner, "first", cutoff + timedelta(seconds=1))
    second = record_policy(learner, "second", cutoff + timedelta(seconds=2))
    # Resolve a later row while the earlier trial remains pending.
    first.size_trials["0.5"].checkpoints.clear()
    first.size_trials["1"].checkpoints.clear()
    database.save_learning_evidence_episode(first)
    now = cutoff + timedelta(minutes=12)
    updated = evaluate(database, study(learner, cutoff), cutoff + timedelta(minutes=4), limit=1)
    assert updated.forward_observed_count == 0
    updated = evaluate(database, updated, now, limit=1)
    assert updated.forward_observation_ids == [first.episode_id, second.episode_id]
    assert updated.forward_usable_count == 1
    assert updated.forward_availability_fraction == 0.5
    assert updated.collection_counts["enrolled"] == 2


def test_preproposal_policy_and_repeated_mint_do_not_become_new_proof(progression):  # noqa: F811
    learner, database, _ = progression
    cutoff = datetime.now(UTC) - timedelta(hours=2)
    first = record_policy(learner, "old", cutoff - timedelta(minutes=1))
    repeat = first.model_copy(
        deep=True,
        update={
            "episode_id": "later-repeat",
            "trajectory_key": "later-repeat",
            "idempotency_key": "later-repeat",
            "created_at": cutoff + timedelta(seconds=1),
            "entry_at": cutoff + timedelta(seconds=1),
            "season_id": "later-season",
        },
    )
    database.save_learning_evidence_episode(repeat)
    updated = evaluate(database, study(learner, cutoff), datetime.now(UTC))
    assert updated.forward_observed_count == 0
    assert updated.collection_counts["identity_excluded"] == 1


def test_deferred_reader_does_not_advance_or_shrink_study(progression):  # noqa: F811
    learner, database, _ = progression
    hypothesis = study(learner, datetime.now(UTC) - timedelta(hours=2))
    before = hypothesis.model_dump()

    def defer():
        raise AdvisoryReadDeferred

    with pytest.raises(AdvisoryReadDeferred):
        database.coach_policy_page(hypothesis, pause=defer)
    assert hypothesis.model_dump() == before


def test_unscanned_retention_gap_is_inconclusive_not_high_coverage(progression):  # noqa: F811
    learner, database, _ = progression
    cutoff = datetime.now(UTC) - timedelta(hours=2)
    for index in range(3):
        episode = record_policy(learner, f"retained-{index}", cutoff + timedelta(seconds=index + 1))
        episode.status = LearningEvidenceStatus.COMPLETE
        database.save_learning_evidence_episode(episode)
    database.prune_learning_evidence(1)
    updated = evaluate(database, study(learner, cutoff), datetime.now(UTC))
    assert updated.state == CoachExperimentState.INCONCLUSIVE
    assert updated.resolution_reason == "policy_history_gap"
    assert updated.forward_usable_count == 0


def test_old_study_transition_is_durable_and_preserves_evidence(progression):  # noqa: F811
    learner, database, _ = progression
    legacy = _hypothesis(datetime.now(UTC) - timedelta(hours=2)).model_copy(
        update={
            "forward_observed_count": 2,
            "forward_usable_count": 1,
            "forward_observation_ids": ["old-a", "old-b"],
            "forward_values": [0.1],
        }
    )
    database.save_coach_hypothesis(legacy)
    coach = AiCoach(
        database,
        FakeCoachHttp(),
        enabled=lambda: True,
        context=lambda: (learner.current_risk_mode, learner.configuration_fingerprint()),
        outcomes_seen=lambda: 100,
        model_provenance=lambda: ("test", "digest"),
        can_run=lambda: (True, None),
    )
    coach._refresh_hypotheses(datetime.now(UTC), [])
    saved = database.coach_hypothesis(legacy.hypothesis_id)
    assert saved.resolution_reason == "evidence_contract_changed"
    assert saved.forward_values == [0.1]
    assert saved.forward_observation_ids == ["old-a", "old-b"]
    coach._refresh_hypotheses(datetime.now(UTC), [])
    assert database.coach_hypothesis(legacy.hypothesis_id) == saved


def test_retention_gap_detects_unscanned_rows_at_cursor_timestamp(progression):  # noqa: F811
    learner, database, _ = progression
    cutoff = datetime.now(UTC) - timedelta(hours=2)
    for index in range(4):
        episode = record_policy(learner, f"same-time-{index}", cutoff + timedelta(seconds=1))
        episode.status = LearningEvidenceStatus.COMPLETE
        database.save_learning_evidence_episode(episode)
    first = evaluate(database, study(learner, cutoff), datetime.now(UTC), limit=1)
    assert first.forward_observed_count == 1
    database.prune_learning_evidence(1)
    updated = evaluate(database, first, datetime.now(UTC))
    assert updated.state == CoachExperimentState.INCONCLUSIVE
    assert updated.resolution_reason == "policy_history_gap"


@pytest.mark.parametrize("change", ["synthetic", "dependencies", "features"])
def test_changed_pending_contract_resolves_unknown(progression, change):  # noqa: F811
    learner, database, _ = progression
    cutoff = datetime.now(UTC) - timedelta(minutes=2)
    episode = record_policy(learner, "changed-contract", cutoff + timedelta(seconds=1))
    now = cutoff + timedelta(minutes=3)
    pending = evaluate(database, study(learner, cutoff), now)
    assert pending.forward_observed_count == 0  # The fixture's checkpoint is still in the future.
    if change == "synthetic":
        episode.synthetic = True
    elif change == "dependencies":
        episode.active_skill_versions = {"entry": "different"}
    else:
        episode.features.clear()
    database.save_learning_evidence_episode(episode)
    updated = evaluate(database, pending, cutoff + timedelta(minutes=20))
    assert updated.forward_observed_count == 1
    assert updated.forward_usable_count == 0
    assert updated.forward_availability_fraction == 0


def test_new_contract_requires_meaningful_seasons_and_bounds_enrollment(progression):  # noqa: F811
    learner, database, _ = progression
    cutoff = datetime.now(UTC) - timedelta(hours=2)
    for index in range(190):
        episode = record_policy(learner, f"capacity-{index}", cutoff + timedelta(seconds=index + 1))
        episode.season_id = "season-one" if index < 60 else "season-two"
        database.save_learning_evidence_episode(episode)
    hypothesis = study(learner, cutoff)
    first = evaluate(database, hypothesis, datetime.now(UTC), limit=60)
    assert first.forward_usable_count == 60
    assert first.forward_season_count == 1
    assert first.state == CoachExperimentState.TESTING
    supported = evaluate(database, first, datetime.now(UTC), limit=10)
    assert supported.forward_season_count == 2
    assert supported.state == CoachExperimentState.PROMISING
    bounded = hypothesis.model_copy(update={"minimum_forward_samples": 181})
    for _ in range(3):
        bounded = evaluate(database, bounded, datetime.now(UTC))
    assert len(bounded.forward_enrollments) == 180
    assert bounded.forward_observed_count == 180
    assert bounded.state == CoachExperimentState.INCONCLUSIVE


def test_active_policy_study_skips_historical_screen_and_keeps_payload_small(
    progression,  # noqa: F811
    monkeypatch,
):
    learner, database, _ = progression
    hypothesis = seed_policy_study(database)
    database.save_coach_hypothesis(hypothesis)
    coach = AiCoach(
        database,
        FakeCoachHttp(),
        enabled=lambda: True,
        context=lambda: (learner.current_risk_mode, "fp"),
        outcomes_seen=lambda: 100,
        model_provenance=lambda: ("test", "digest"),
        can_run=lambda: (True, None),
        provenance=lambda: {
            "baseline_version": BASELINE_VERSION,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
        },
    )
    monkeypatch.setattr(
        database,
        "recent_learning_observations",
        lambda *args, **kwargs: pytest.fail("historical scan during forward work"),
    )
    asyncio.run(coach.tick())
    saved = database.coach_hypothesis(hypothesis.hypothesis_id)
    assert saved.forward_usable_count == 30
    assert coach.http.calls == 0
    view = coach.status()["recent_hypotheses"][0]
    assert "forward_enrollments" not in view
    assert view["collection_counts"]["enrolled"] == 30


def test_proposal_cutoff_is_frozen_after_inference(tmp_path, monkeypatch):
    import signal_arcade.coach as module
    from signal_arcade.database import Database
    from test_coach import _observation
    from test_coach_pressure import coach_for

    database = Database(tmp_path / "proposal-clock.sqlite3")
    for index in range(30):
        database.save_learning_observation(
            _observation(index, datetime.now(UTC) - timedelta(hours=1, seconds=index))
        )
    selected_at = datetime.now(UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return selected_at

    coach = coach_for(database)
    original = coach.http.ollama_structured

    async def delayed(**kwargs):
        nonlocal selected_at
        result = await original(**kwargs)
        selected_at += timedelta(seconds=45)
        return result

    monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(coach.http, "ollama_structured", delayed)
    try:
        asyncio.run(coach.tick())
        assert coach.hypotheses[0].evidence_contract == "policy-v1"
        assert coach.hypotheses[0].cutoff_at == selected_at
    finally:
        database.close()


@pytest.mark.parametrize("selected,baseline", [(10.0, -1.0), (-1.0, 10.0)])
def test_large_valid_exit_differences_survive_persistence(progression, selected, baseline):  # noqa: F811
    learner, database, _ = progression
    cutoff = datetime.now(UTC) - timedelta(hours=2)
    episode = record_policy(learner, "large-exit-difference", cutoff + timedelta(seconds=1))
    episode.checkpoints["300"].net_return = selected
    episode.checkpoints["600"].net_return = baseline
    database.save_learning_evidence_episode(episode)
    updated = evaluate(
        database, study(learner, cutoff, CoachExperimentKind.EARLIER_REVIEW), datetime.now(UTC)
    )
    database.save_coach_hypothesis(updated)
    restored = database.coach_hypothesis(updated.hypothesis_id)
    assert restored is not None
    assert restored.forward_values == [selected - baseline]
    assert restored.forward_uplift_lower_bound <= restored.forward_mean_uplift
    assert restored.forward_uplift_upper_bound >= restored.forward_mean_uplift
    assert restored.state == CoachExperimentState.TESTING


def test_missing_pending_row_stays_in_denominator(progression):  # noqa: F811
    learner, database, _ = progression
    cutoff = datetime.now(UTC) - timedelta(minutes=2)
    first = record_policy(learner, "lost-pending", cutoff + timedelta(seconds=1))
    record_policy(learner, "kept-pending", cutoff + timedelta(seconds=2))
    pending = evaluate(database, study(learner, cutoff), cutoff + timedelta(minutes=3))
    assert len(pending.forward_enrollments) == 2
    first.status = LearningEvidenceStatus.COMPLETE
    database.save_learning_evidence_episode(first)
    # Simulate external loss after enrollment, independently of the pruning watermark.
    with database._conn:
        database._conn.execute(
            "DELETE FROM learning_evidence_episodes WHERE episode_id=?", (first.episode_id,)
        )
    updated = evaluate(database, pending, cutoff + timedelta(minutes=20))
    assert updated.forward_observed_count == 2
    assert updated.forward_usable_count == 1
    assert updated.forward_availability_fraction == 0.5


def test_policy_reader_uses_committed_wal_snapshot_without_core_locks(progression):  # noqa: F811
    _, database, _ = progression
    hypothesis = seed_policy_study(database)
    before = evaluate(database, hypothesis, datetime.now(UTC))
    database._conn.execute("BEGIN IMMEDIATE")
    try:
        database._conn.execute("DELETE FROM learning_evidence_episodes WHERE lane='policy'")
        with ThreadPoolExecutor(max_workers=1) as worker, database._lock, database._reader_lock:
            observed = worker.submit(evaluate, database, hypothesis, datetime.now(UTC)).result(
                timeout=2
            )
        assert observed.forward_observation_ids == before.forward_observation_ids
        assert observed.forward_values == before.forward_values
    finally:
        database._conn.rollback()


def test_interrupted_policy_page_preserves_progress_until_complete_retry(progression):  # noqa: F811
    _, database, _ = progression
    hypothesis = seed_policy_study(database, count=40)
    database.save_coach_hypothesis(hypothesis)
    pauses = 0

    def interrupt_second_record_batch():
        nonlocal pauses
        pauses += 1
        if pauses == 3:
            raise AdvisoryReadDeferred

    with pytest.raises(AdvisoryReadDeferred):
        database.coach_policy_page(hypothesis, pause=interrupt_second_record_batch)
    assert database.coach_hypothesis(hypothesis.hypothesis_id) == hypothesis
    recovered = evaluate(database, hypothesis, datetime.now(UTC))
    assert recovered.forward_observed_count == 40
    assert len(set(recovered.forward_observation_ids)) == 40


def test_same_timestamp_pages_resume_after_restart_without_duplicates(progression):  # noqa: F811
    learner, database, _ = progression
    cutoff = datetime.now(UTC) - timedelta(hours=2)
    expected = []
    for index in range(9):
        episode = record_policy(learner, f"page-tie-{index}", cutoff + timedelta(seconds=1))
        expected.append(episode.episode_id)
    hypothesis = study(learner, cutoff)
    for _ in range(4):
        updated = evaluate(database, hypothesis, datetime.now(UTC), limit=3)
        database.save_coach_hypothesis(updated)
        hypothesis = database.coach_hypothesis(updated.hypothesis_id)
    assert hypothesis.forward_observation_ids == sorted(expected)
    assert hypothesis.collection_counts["scanned"] == 9
    assert hypothesis.forward_observed_count == 9


def test_failed_coach_commit_keeps_evidence_and_cursor_retryable(progression):  # noqa: F811
    learner, database, _ = progression
    hypothesis = seed_policy_study(database)
    database.save_coach_hypothesis(hypothesis)
    coach = AiCoach(
        database,
        FakeCoachHttp(),
        enabled=lambda: True,
        context=lambda: (learner.current_risk_mode, "fp"),
        outcomes_seen=lambda: 100,
        model_provenance=lambda: ("test", "digest"),
        can_run=lambda: (True, None),
    )

    def deny_commit(action, operation, *args):
        return (
            sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_TRANSACTION and operation == "COMMIT"
            else sqlite3.SQLITE_OK
        )

    database._conn.set_authorizer(deny_commit)
    try:
        with pytest.raises(sqlite3.DatabaseError):
            coach._refresh_hypotheses(datetime.now(UTC))
    finally:
        database._conn.set_authorizer(None)
    assert not database._conn.in_transaction
    assert coach.hypotheses[0] == hypothesis
    assert database.coach_hypothesis(hypothesis.hypothesis_id) == hypothesis
    coach._refresh_hypotheses(datetime.now(UTC))
    assert database.coach_hypothesis(hypothesis.hypothesis_id).forward_observed_count == 30
