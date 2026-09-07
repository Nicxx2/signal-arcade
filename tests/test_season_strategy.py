from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import Database
from signal_arcade.models import LearningAssessment, Position
from signal_arcade.season_strategy import (
    MAX_PARTICIPANTS,
    decision_participants,
    new_strategy_record,
    record_strategy_use,
    strategy_view,
)
from test_auto_seasons import season_summary
from test_learning import make_decision

# ruff: noqa: SLF001


def setup(settings):
    db = Database(settings.database_path)
    db.initialize_portfolio("initial", 400_000_000, "USDC")
    return db, db.get_setting("season_id")


def decision(season, sequence=0, *, skill=None, applied=True):
    item = make_decision(datetime.now(UTC), f"mint-{sequence}", 0.7)
    item.season_id = season
    if skill:
        item.challenger_assessments[skill] = {
            "artifact_version": f"{skill}-champion-v1",
            "skill": skill,
            "parameters": {"applied": applied},
        }
    return item


def usage(db):
    return db.list_paper_seasons()[-1]["strategy_usage"]


def test_new_season_records_actual_use_and_preserves_it_across_restart_and_archive(settings):
    db, season = setup(settings)
    try:
        assert usage(db)["status"] == "no_decisions"
        db.save_decision(decision(season, skill="entry", applied=False))
        assert usage(db)["status"] == "baseline"
        applied = decision(season, 1, skill="sizing")
        db.save_decision(applied)
        db.save_decision(applied)
        result = usage(db)
        assert result["status"] == "mixed" and result["complete_from_start"]
        assert result["skills_observed"] == ["sizing"]
        assert len(result["participants"]) == 1
        assert result["participants"][0]["first_used_at"]
        assert result["participants"][0]["name"]
        db.close()
        db = Database(settings.database_path)
        assert usage(db) == result
        db.reset_paper_state(season_summary())
        assert usage(db) == result
        # A late or imported decision cannot rewrite a closed season's usage.
        db.save_decision(decision(season, 2, skill="manipulation"))
        assert usage(db) == result
        db.initialize_portfolio("next", 400_000_000, "USDC")
        assert usage(db)["status"] == "no_decisions"
    finally:
        db.close()


def test_upgrade_marks_current_history_partial_and_completed_history_unknown(settings):
    db, season = setup(settings)
    db.reset_paper_state(season_summary())
    db.initialize_portfolio("next", 400_000_000, "USDC")
    current = db.get_setting("season_id")
    db.close()
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute("DROP TABLE paper_season_strategy")
        connection.execute("PRAGMA user_version=14")
    db = Database(settings.database_path)
    try:
        old, active = db.list_paper_seasons()
        assert old["season_id"] == season
        assert old["strategy_usage"]["status"] == "unknown"
        assert not active["strategy_usage"]["complete_from_start"]
        db.save_decision(decision(current))
        assert usage(db)["status"] == "unknown"
        db.save_decision(decision(current, 1, skill="entry"))
        assert usage(db)["status"] == "mixed"
        assert not usage(db)["complete_from_start"]
    finally:
        db.close()


def test_failed_write_does_not_cache_uncommitted_usage(settings):
    db, season = setup(settings)
    try:
        db._conn.execute("""CREATE TRIGGER fail_strategy BEFORE UPDATE ON paper_season_strategy
            BEGIN SELECT RAISE(ABORT, 'injected failure'); END""")
        item = decision(season, skill="entry")
        with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
            db.save_decision(item)
        assert db.get_decision(item.decision_id) is None
        assert usage(db)["status"] == "no_decisions"
        db._conn.execute("DROP TRIGGER fail_strategy")
        db.save_decision(item)
        assert usage(db)["status"] == "assisted"
    finally:
        db.close()


def test_shadow_and_legacy_and_actual_critic_veto_are_distinguished():
    item = decision(None, skill="entry", applied=False)
    assert decision_participants(item) == []
    item.learning_assessment = LearningAssessment(
        model_version="legacy-entry",
        predicted_net_return=0.1,
        conservative_net_return=0.05,
        validation_rmse=0.05,
        applied=True,
        verdict="supports_entry",
    )
    assert decision_participants(item)[0]["kind"] == "learner"
    item.model_version += "+ai-critic-v4"
    assert decision_participants(item)[1]["kind"] == "ai_critic"


@pytest.mark.parametrize(
    "raw", [None, "broken", "{}", '{"schema_version":99}', '{"participants":[null]}']
)
def test_missing_or_malformed_history_stays_unknown(raw):
    assert strategy_view(raw)["status"] == "unknown"


def test_repeat_use_does_not_write_history_and_version_details_are_bounded(settings):
    db, season = setup(settings)
    try:
        db.save_decision(decision(season, skill="entry"))
        queries = []
        db._conn.set_trace_callback(queries.append)
        for index in range(1, 20):
            db.save_decision(decision(season, index, skill="entry"))
        db._conn.set_trace_callback(None)
        assert not any("paper_season_strategy" in query for query in queries)
    finally:
        db.close()
    at = datetime.now(UTC).isoformat()
    record = new_strategy_record(at, complete=True)
    for index in range(MAX_PARTICIPANTS + 5):
        record = record_strategy_use(
            record, [{"kind": "champion", "skill": "entry", "version": str(index)}], at
        )
    assert len(record["participants"]) == MAX_PARTICIPANTS
    assert record["details_limited"]
    assert strategy_view(json.dumps(record))["status"] == "assisted"


def test_exit_participation_survives_position_retirement(settings):
    from signal_arcade.models import ExitAssessment

    db, season = setup(settings)
    now = datetime.now(UTC)
    position = Position(
        position_id="position",
        mint="mint",
        symbol="Token",
        token_units=100,
        entry_cost_lamports=100,
        book_value_lamports=100,
        opened_at=now - timedelta(minutes=10),
        entry_fill_id="entry",
        exit_assessment=ExitAssessment(
            evaluated_at=now,
            action="hold",
            reason="support",
            support_score=0.6,
            pnl_fraction=0.1,
            peak_return_fraction=0.1,
            drawdown_from_peak_fraction=0,
            age_seconds=600,
            soft_hold_seconds=600,
            hard_hold_seconds=1200,
            strategy_season_id=season,
            strategy_participant={"kind": "champion", "skill": "exit", "version": "exit-v1"},
        ),
    )
    try:
        db.save_position(position)
        db.delete_position(position.position_id)
        assert usage(db)["skills_observed"] == ["exit"]
        assert usage(db)["status"] == "assisted"
    finally:
        db.close()


def test_strategy_changes_are_not_hidden_by_decision_deduplication(settings):
    from signal_arcade.orchestrator import Orchestrator

    engine = Orchestrator(settings)
    try:
        previous = decision(None)
        previous.action = "pass"
        engine.last_recorded_decision[previous.mint] = previous
        changed = previous.model_copy(
            update={"model_version": previous.model_version + "+new-champion"}
        )
        assert engine._should_record_decision(changed)
        assert not engine._should_record_decision(previous)
    finally:
        engine.database.close()


def test_late_data_cannot_claim_participation_before_tracking_started():
    now = datetime.now(UTC)
    record = new_strategy_record(now.isoformat(), complete=True)
    assert record_strategy_use(record, [], (now - timedelta(seconds=1)).isoformat()) is record
    assert record_strategy_use(record, [], "invalid") is record


def test_duplicate_participants_and_details_cap_preserve_actual_skill_summary():
    now = datetime.now(UTC).isoformat()
    record = new_strategy_record(now, complete=True)
    item = {"kind": "learner", "skill": "entry", "version": "legacy"}
    record = record_strategy_use(record, [item, item], now)
    assert len(record["participants"]) == 1
    for index in range(MAX_PARTICIPANTS):
        record = record_strategy_use(record, [{**item, "version": str(index)}], now)
    record = record_strategy_use(
        record, [{"kind": "champion", "skill": "sizing", "version": "sizing-v2"}], now
    )
    assert record["champion_observed"]
    assert record["skills_observed"] == ["entry", "sizing"]
    assert record["details_limited"]


def test_incomplete_participant_details_do_not_crash_or_claim_baseline_use(settings):
    db, season = setup(settings)
    try:
        item = decision(season, skill="entry")
        item.challenger_assessments["entry"]["artifact_version"] = ""
        db.save_decision(item)
        assert db.get_decision(item.decision_id) is not None
        assert usage(db)["status"] == "unknown"
        assert usage(db)["unattributed_use"]
        assert not usage(db)["baseline_observed"]
        db.save_decision(decision(season, 1))
        assert usage(db)["status"] == "unknown"
        db.save_decision(decision(season, 2, skill="sizing"))
        assert usage(db)["skills_observed"] == ["sizing"]
        assert usage(db)["unattributed_use"]
    finally:
        db.close()


@pytest.mark.parametrize(
    "corruption",
    [
        "family",
        "blank_version",
        "duplicate",
        "missing_skill",
        "missing_champion_flag",
        "false_ai_flag",
        "baseline_without_time",
        "time_without_baseline",
        "early_time",
        "false_detail_limit",
    ],
)
def test_corrupt_saved_history_stays_unknown(corruption):
    now = datetime.now(UTC)
    record = record_strategy_use(
        new_strategy_record(now.isoformat(), complete=True),
        [{"kind": "champion", "skill": "entry", "version": "entry-v1"}],
        now.isoformat(),
    )
    if corruption == "family":
        record["participants"][0]["kind"] = "ai_critic"
    elif corruption == "blank_version":
        record["participants"][0]["version"] = " "
    elif corruption == "duplicate":
        record["participants"].append(record["participants"][0])
    elif corruption == "missing_skill":
        record["skills_observed"] = []
    elif corruption == "missing_champion_flag":
        record["champion_observed"] = False
    elif corruption == "false_ai_flag":
        record["ai_observed"] = True
    elif corruption == "baseline_without_time":
        record["baseline_observed"] = True
    elif corruption == "time_without_baseline":
        record["first_baseline_at"] = now.isoformat()
    elif corruption == "early_time":
        record["participants"][0]["first_used_at"] = (now - timedelta(seconds=1)).isoformat()
    elif corruption == "false_detail_limit":
        record["details_limited"] = True
    assert strategy_view(json.dumps(record))["status"] == "unknown"


@pytest.mark.parametrize("participant", [{}, {"kind": "champion"}])
def test_incomplete_exit_metadata_cannot_break_position_save(settings, participant):
    from signal_arcade.models import RISK_LIMITS, ExitAssessment, RiskMode
    from signal_arcade.paper.exit_policy import assess_exit
    from test_exit_policy import features, position

    db, season = setup(settings)
    now = datetime.now(UTC)
    try:
        item = position(now, age_seconds=60)
        assessment: ExitAssessment = assess_exit(
            position=item, features=features(now), now=now, limits=RISK_LIMITS[RiskMode.BALANCED]
        )
        assessment.strategy_season_id = season
        assessment.strategy_participant = participant
        item.exit_assessment = assessment
        db.save_position(item)
        assert usage(db)["status"] == "unknown"
        assert usage(db)["unattributed_use"]
        assert not usage(db)["baseline_observed"]
        assert db.list_positions()
    finally:
        db.close()


@pytest.mark.parametrize(
    "mark,strong,seconds,executable",
    [
        (110, True, 60, True),
        (110, False, 60, True),
        (60, True, 60, True),
        (110, False, 60, False),
        (110, True, 99999, True),
    ],
)
def test_exit_attribution_does_not_change_assessment_or_orders(
    settings, tmp_path, mark, strong, seconds, executable
):
    from signal_arcade.models import RiskMode
    from test_broker import make_broker
    from test_exit_policy import features, position
    from test_learning import make_state

    now = datetime.now(UTC)
    results = []
    for index, participant in enumerate(
        [None, {"kind": "champion", "skill": "exit", "version": "exit-v1"}]
    ):
        db = Database(tmp_path / f"exit-{index}.sqlite3")
        try:
            broker = make_broker(db, settings)
            item = position(now, age_seconds=700, mark=mark)
            item.mark_is_executable = executable
            broker.positions[item.mint] = item
            broker._schedule_exit_if_needed(
                make_state(item.mint),
                features(now, strong=strong),
                now,
                RiskMode.BALANCED,
                soft_hold_seconds=seconds,
                soft_hold_participant=participant,
            )
            assert item.exit_assessment is not None
            results.append(
                (
                    item.exit_assessment.model_dump(
                        exclude={"strategy_season_id", "strategy_participant"}
                    ),
                    [order.model_dump(exclude={"order_id"}) for order in broker.pending.values()],
                )
            )
            if seconds == 99999:
                assert item.exit_assessment.strategy_participant is None
            if not executable:
                assert not broker.pending
        finally:
            db.close()
    assert results[0] == results[1]
