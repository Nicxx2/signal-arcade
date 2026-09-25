"""Enrollment evidence must remain optional, bounded, immutable and outside training."""

import asyncio
import sqlite3
from datetime import timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.intelligence.activity_evidence import (
    BOOL_METRICS,
    COUNT_METRICS,
    MAX_ACTIVITY_EVIDENCE_BYTES,
    METRICS,
    capture_activity,
    read_activity,
)
from signal_arcade.intelligence.learning import LearningEngine
from signal_arcade.intelligence.training_job import freeze_training_inputs
from signal_arcade.models import (
    DecisionAction,
    IntegrityAssessment,
    LearningObservationStatus,
    MarketIntegrityState,
)
from test_activity_evidence import NOW
from test_learning import data, make_decision, make_state


def full_decision(mint="example"):
    decision = make_decision(NOW, mint)
    for name in METRICS:
        value = True if name in BOOL_METRICS else 10 if name in COUNT_METRICS else 0.5
        if name == "signed_net_quote_flow_ratio_5m":
            value = 0.0
        if name == "trade_buffer_saturated":
            value = False
        if name in {
            "trade_amount_coverage_5m",
            "known_wallet_trade_coverage",
            "signed_trade_coverage",
        }:
            value = 1.0
        decision.feature_snapshot.values[name] = data(NOW, value)
    decision.integrity_assessment = IntegrityAssessment(
        policy_version="integrity-gates-v3",
        state=MarketIntegrityState.CLEAN,
        score=0,
        coverage=1,
        sample_count=10,
        category_count=0,
        categories=[],
        evidence=["Original assessment"],
    )
    return decision


@pytest.fixture
def enrolled(settings):
    db = Database(settings.database_path)
    learner = LearningEngine(db, settings)
    decision = make_decision(NOW, "example")
    assert learner.register(decision, make_state("example"), live=True, evaluation_actionable=True)
    yield db, learner, learner.observations["example"]
    db.close()


def test_contract_keeps_raw_signed_values_clocks_context_and_integrity(enrolled):
    _, _, parent = enrolled
    decision = full_decision()
    decision.feature_snapshot.values["buy_quote_volume_ratio_5m"].value = 0.25
    decision.feature_snapshot.values["signed_net_quote_flow_ratio_5m"].value = -0.5
    for item in decision.feature_snapshot.values.values():
        item.as_of -= timedelta(milliseconds=500)
    record = capture_activity(parent, decision, "SOL")
    assert record.status == "complete"
    assert record.metrics["signed_net_quote_flow_ratio_5m"][0] == -0.5
    assert record.clocks == [NOW - timedelta(milliseconds=500)]
    assert record.integrity == decision.integrity_assessment
    assert len(record.model_dump_json().encode()) <= MAX_ACTIVITY_EVIDENCE_BYTES
    assert read_activity(record.model_dump_json(), parent) == record
    with pytest.raises(ValueError, match="mismatch"):
        read_activity(record.model_dump_json(), parent.model_copy(update={"decision_id": "later"}))


@pytest.mark.parametrize(
    "name,value",
    [
        ("signed_net_quote_flow_ratio_5m", True),
        ("trade_count_5m", -1),
        ("meaningful_trade_count_1m", 10.5),
        ("buy_quote_volume_ratio_5m", float("nan")),
        ("signed_net_quote_flow_ratio_5m", float("inf")),
        ("buy_quote_volume_ratio_5m", "0.5"),
        ("trade_buffer_saturated", 0),
        ("meaningful_trade_count_1m", 11),
        ("signed_net_quote_flow_ratio_5m", 0.4),
    ],
)
def test_malformed_capture_never_becomes_reassuring_numeric_evidence(enrolled, name, value):
    _, _, parent = enrolled
    decision = full_decision()
    decision.feature_snapshot.values[name].value = value
    record = capture_activity(parent, decision, "SOL")
    assert record.status == "unavailable"
    assert record.reason == "invalid_capture"
    assert record.metrics == {}


def test_missing_future_mismatched_and_oversize_records(enrolled):
    _, _, parent = enrolled
    decision = full_decision()
    del decision.feature_snapshot.values["meaningful_trade_count_1m"]
    record = capture_activity(parent, decision, "SOL")
    assert record.status == "partial"
    assert record.metrics["meaningful_trade_count_1m"] == (None, 0, None, "not_recorded")
    decision.feature_snapshot.values["trade_count_5m"].as_of += timedelta(seconds=1)
    assert capture_activity(parent, decision, "SOL").status == "unavailable"
    decision = full_decision()
    decision.decision_id = "later"
    assert capture_activity(parent, decision, "SOL").status == "unavailable"
    decision = full_decision()
    decision.integrity_assessment.evidence = ["x" * 5000]
    record = capture_activity(parent, decision, "SOL")
    assert record.reason == "payload_too_large"
    assert record.metrics == {}


def test_raw_integrity_operand_with_low_coverage_reason_is_preserved(enrolled):
    _, _, parent = enrolled
    decision = full_decision()
    raw = decision.feature_snapshot.values["median_trade_quote_sol"]
    raw.value, raw.quality, raw.missing_reason = 1.75, 0.5, "trade_amount_unavailable"
    record = capture_activity(parent, decision, "SOL")
    assert record.status == "partial"
    assert record.metrics["median_trade_quote_sol"] == (1.75, 0.5, 0, "trade_amount_unavailable")
    assert read_activity(record.model_dump_json(), parent) == record


def test_partial_amounts_and_mixed_cached_clocks_are_not_complete(enrolled):
    _, _, parent = enrolled
    decision = full_decision()
    decision.feature_snapshot.values["trade_amount_coverage_5m"].value = 0.9
    assert capture_activity(parent, decision, "SOL").status == "unavailable"
    decision = full_decision()
    decision.feature_snapshot.values["meaningful_trade_count_1m"].as_of -= timedelta(milliseconds=1)
    assert capture_activity(parent, decision, "SOL").status == "unavailable"


def records(db, table="learning_activity_discovery"):
    assert table in {"learning_activity_discovery", "learning_activity_policy"}
    return [
        tuple(row)
        for row in db._conn.execute(
            f"SELECT * FROM {table} ORDER BY parent_id"  # noqa: S608 - test allowlist
        )
    ]


def test_enrollment_first_identity_retry_checkpoint_and_training_are_unchanged(settings):
    db = Database(settings.database_path)
    learner = LearningEngine(db, settings)
    first = make_decision(NOW, "same-mint")
    first.action = DecisionAction.PASS
    state = make_state(first.mint)
    assert learner.register(first, state, live=True)
    discovery = learner.observations[first.mint]
    original_discovery = records(db)
    later = make_decision(NOW + timedelta(seconds=90), first.mint)
    later.decision_id = "second-decision"
    assert learner.register(later, state, live=True, evaluation_actionable=True)
    episode = next(iter(learner.evidence_episodes.values()))
    policy = records(db, "learning_activity_policy")
    assert read_activity(policy[0][1], episode).decision_at == later.created_at
    assert read_activity(original_discovery[0][1], discovery).decision_at == first.created_at
    assert records(db) == original_discovery
    frozen = freeze_training_inputs(([discovery], [episode], [], [], []))
    parent_json = discovery.model_dump_json(), episode.model_dump_json()
    # A failed first order and later successful attempt do not replace enrollment evidence.
    learner.link_policy_order(later.decision_id, "first-order")
    retry = later.model_copy(deep=True)
    retry.decision_id = "third-successful-attempt"
    retry.created_at += timedelta(seconds=60)
    assert not learner.register(retry, state, live=True, evaluation_actionable=True)
    db.save_learning_observation(discovery)
    db.save_learning_evidence_episode(episode)
    assert records(db) == original_discovery
    assert records(db, "learning_activity_policy") == policy
    # Metadata storage is absent from serialization; linking an order is a pre-existing change.
    episode.order_id = None
    assert parent_json == (discovery.model_dump_json(), episode.model_dump_json())
    assert frozen == freeze_training_inputs(([discovery], [episode], [], [], []))
    db.save_learning_observation(discovery, activity_decision=retry)
    assert records(db) == original_discovery
    assert db.activity_capture_counts() == {
        "attempted": 3,
        "persisted_partial": 2,
        "skipped_existing": 1,
    }
    db.close()
    reopened = Database(settings.database_path)
    assert records(reopened) == original_discovery
    assert records(reopened, "learning_activity_policy") == policy
    assert reopened.activity_capture_counts() == {}
    reopened.close()


def test_legacy_rows_are_not_backfilled_and_parent_retention_cascades(enrolled):
    db, learner, parent = enrolled
    legacy = parent.model_copy(deep=True, update={"observation_id": "legacy", "mint": "legacy"})
    db.save_learning_observation(legacy)
    db.save_learning_observation(legacy, activity_decision=make_decision(NOW, "legacy"))
    assert len(records(db)) == 1
    # Pending rows are protected by existing retention. Completing/pruning removes metadata.
    db.prune_learning_observations(0)
    assert len(records(db)) == 1
    parent.status = LearningObservationStatus.COMPLETE
    db.save_learning_observation(parent)
    db.prune_learning_observations(0)
    assert not records(db)
    episode = next(iter(learner.evidence_episodes.values()))
    db._conn.execute(
        "DELETE FROM learning_evidence_episodes WHERE episode_id=?", (episode.episode_id,)
    )
    db._conn.commit()
    assert not records(db, "learning_activity_policy")
    assert not db._conn.execute("PRAGMA foreign_key_check").fetchall()


def test_decision_rotation_does_not_erase_learning_metadata(enrolled):
    db, _, _ = enrolled
    db.save_decision(make_decision(NOW, "example"))
    before = records(db), records(db, "learning_activity_policy")
    with db._lock, db._conn:
        db._clear_paper_tables()
    assert db.get_decision("decision-example") is None
    assert (records(db), records(db, "learning_activity_policy")) == before
    assert not db._conn.execute("PRAGMA foreign_key_check").fetchall()


def test_capture_counters_reuse_bounded_collection_events(settings):
    from signal_arcade.diagnostics_store import MAX_EVENT_PAYLOAD, encode
    from signal_arcade.orchestrator import Orchestrator

    engine = Orchestrator(settings)
    engine.diagnostics.enabled = True
    try:
        engine.learning.collection_diagnostics.enrolled("discovery", "parent")
        engine.learning.collection_diagnostics.record("discovery", 300, "expired")
        for key in (
            "attempted",
            "persisted_complete",
            "persisted_partial",
            "persisted_unavailable",
            "invalid_capture",
            "optional_sql_failed",
            "skipped_existing",
            "parent_failed",
        ):
            engine.database._activity_counts[key] = 10**12
        events = engine._collection_diagnostic_events()
        assert len(events) == 2
        assert (
            events[-1]["activity_capture_since_boot"] == engine.database.activity_capture_counts()
        )
        for event in events:
            encode(event, max_payload=MAX_EVENT_PAYLOAD)
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()


@pytest.mark.parametrize("trigger,raises", [("ABORT", False), ("ROLLBACK", True)])
def test_optional_sql_failure_isolated_only_while_parent_transaction_is_intact(
    settings, trigger, raises
):
    db = Database(settings.database_path)
    db._conn.execute(f"""CREATE TRIGGER fail_activity BEFORE INSERT ON learning_activity_discovery
        BEGIN SELECT RAISE({trigger}, 'injected optional error'); END""")
    learner = LearningEngine(db, settings)
    decision = make_decision(NOW, "example")
    if raises:
        with pytest.raises(sqlite3.IntegrityError):
            learner.register(decision, make_state("example"), live=True)
        assert not db.list_learning_observations()
        assert db.activity_capture_counts() == {"attempted": 1, "parent_failed": 1}
    else:
        assert learner.register(decision, make_state("example"), live=True)
        assert len(db.list_learning_observations()) == 1
        assert db.activity_capture_counts() == {"attempted": 1, "optional_sql_failed": 1}
    assert not records(db)
    db.close()


@pytest.mark.parametrize(
    "error",
    [
        sqlite3.SQLITE_FULL,
        sqlite3.SQLITE_CORRUPT,
        sqlite3.SQLITE_IOERR,
        sqlite3.SQLITE_INTERRUPT,
        "cancel",
        "commit",
    ],
)
def test_fatal_storage_cancellation_and_commit_failure_never_ack_durability(settings, error):
    db = Database(settings.database_path)
    learner = LearningEngine(db, settings)
    original = db._conn

    class FaultConnection:
        def __getattr__(self, name):
            return getattr(original, name)

        def __enter__(self):
            original.__enter__()
            return self

        def __exit__(self, kind, value, trace):
            if error == "commit" and kind is None:
                original.rollback()
                raise sqlite3.OperationalError("injected commit failure")
            return original.__exit__(kind, value, trace)

        def execute(self, sql, *args):
            if "INSERT INTO learning_activity" in sql and error != "commit":
                if error == "cancel":
                    raise asyncio.CancelledError()
                exc = sqlite3.OperationalError("injected fatal storage failure")
                exc.sqlite_errorcode = error
                raise exc
            return original.execute(sql, *args)

    db._conn = FaultConnection()
    with pytest.raises((sqlite3.OperationalError, asyncio.CancelledError)):
        learner.register(make_decision(NOW, "example"), make_state("example"), live=True)
    assert not db.list_learning_observations()
    assert not records(db)
    assert db.activity_capture_counts() == {"attempted": 1, "parent_failed": 1}
    db._conn = original
    db.close()
