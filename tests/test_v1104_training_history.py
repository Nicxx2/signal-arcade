from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.database import RECENT_CHAMPION_EVENTS_IN_MEMORY, Database
from signal_arcade.intelligence.learning import LearningEngine
from signal_arcade.models import (
    ChallengerChampionEvent,
    ChallengerSkill,
    ChallengerSkillState,
    LearningCheckpoint,
    LearningMode,
    Position,
    RiskMode,
)
from signal_arcade.orchestrator import Orchestrator
from test_learning import make_decision, make_state


def training_fixture(settings, count=100):
    database = Database(settings.database_path)
    context = ["training-context"]
    learner = LearningEngine(database, settings, configuration_fingerprint=lambda: context[0])
    start = datetime.now(UTC) - timedelta(minutes=count + 80)
    for index in range(count):
        mint = f"row-{index}"
        decision = make_decision(start + timedelta(minutes=index), mint, (index % 10) / 10)
        decision.configuration_fingerprint = context[0]
        assert learner.register(decision, make_state(mint), live=True)
        learner.observations[mint].checkpoints["300"] = LearningCheckpoint(
            horizon_seconds=300,
            observed_at=decision.created_at + timedelta(seconds=300),
            net_return=(index % 10) / 10 - 0.5,
            exit_value_lamports=1000,
        )
    learner.request_current_training()
    return learner, database, context


def test_linear_and_xgboost_publish_the_same_frozen_policy_population(settings):
    from signal_arcade.intelligence.learning import _policy_evidence_cohort
    from signal_arcade.models import StatisticalModelFamily
    from test_participation_progression import record_policy

    learner, database, _ = training_fixture(settings, count=400)
    start = datetime.now(UTC) - timedelta(hours=1)
    for i in range(4):
        episode = record_policy(learner, f"proof-{i}", start + timedelta(seconds=i))
        if i == 0:
            episode.checkpoints["300"].net_return = None
            episode.checkpoints["300"].missing_reason = "route_unavailable"
    job = learner.prepare_next_training(("season-1",))
    assert job is not None
    expected = _policy_evidence_cohort(list(learner.evidence_episodes.values()))
    episode.checkpoints["300"].net_return = 0.75
    assert _policy_evidence_cohort(list(learner.evidence_episodes.values())) != expected
    learner.fit_training_job(job)
    assert learner.finish_training_job(job, runtime_context=("season-1",))
    artifacts = [
        a for a in database.list_challenger_artifacts() if a.skill == ChallengerSkill.ENTRY
    ]
    assert {a.model_family for a in artifacts} == {
        StatisticalModelFamily.LINEAR,
        StatisticalModelFamily.XGBOOST,
    }
    assert {a.parameters["policy_evidence_cohort"] for a in artifacts} == {expected}
    assert all(a.metrics["policy_observed"] == 4 for a in artifacts)
    database.close()


def test_fit_reads_a_copy_and_publication_does_not_replace_new_evidence(settings):
    learner, database, _context = training_fixture(settings)
    job = learner.prepare_next_training(("season-1",))
    assert job is not None
    original_value = learner.observations["row-0"].features["opportunity"]
    learner.observations["row-0"].features["opportunity"] = 0.999
    learner.observations["row-0"].checkpoints["600"] = LearningCheckpoint(
        horizon_seconds=600,
        observed_at=datetime.now(UTC),
        net_return=-0.8,
    )
    learner.fit_training_job(job)
    assert database.list_learning_models() == []
    assert database.list_challenger_artifacts() == []
    assert job.workspace.observations["row-0"].features["opportunity"] == original_value
    assert "600" not in job.workspace.observations["row-0"].checkpoints
    assert job.workspace._training_output.models
    assert learner.finish_training_job(job, runtime_context=("season-1",))
    assert database.list_learning_models()
    assert learner.observations["row-0"].features["opportunity"] == 0.999
    assert learner.observations["row-0"].checkpoints["600"].net_return == -0.8
    database.close()


@pytest.mark.parametrize("change", ["configuration", "risk", "mode", "dependency", "season"])
def test_fit_cannot_publish_after_its_context_changes(settings, change):
    learner, database, context = training_fixture(settings)
    job = learner.prepare_next_training(("season-1",))
    assert job is not None
    learner.fit_training_job(job)
    assert job.workspace._training_output.models
    runtime = ("season-1",)
    if change == "configuration":
        context[0] = "changed"
    elif change == "risk":
        learner.current_risk_mode = RiskMode.AGGRESSIVE
    elif change == "mode":
        learner.mode = LearningMode.OFF
    elif change == "dependency":
        learner.active_skill_versions["entry"] = "different-version"
    else:
        runtime = ("season-2",)
    assert not learner.finish_training_job(job, runtime_context=runtime)
    assert not database.list_learning_models()
    assert not database.list_challenger_artifacts()
    assert learner.training_status()["discarded_stale_jobs"] == 1
    assert learner.has_pending_training()
    database.close()


def test_fit_failure_retains_one_retry_and_releases_worker(settings):
    learner, database, _context = training_fixture(settings)
    job = learner.prepare_next_training()
    with pytest.raises(RuntimeError, match="injected"):
        learner.finish_training_job(job, error=RuntimeError("injected fit failure"))
    assert learner.training_status()["queued"] == 1
    assert learner.training_status()["state"] == "queued"
    assert not database.list_learning_models()
    database.close()


def test_dormant_inventory_allows_coach_but_unexecutable_active_inventory_does_not(settings):
    engine = Orchestrator(settings)
    engine.demo_mode = False
    position = Position(
        position_id="position",
        mint="mint",
        symbol="DORMANT",
        token_units=1,
        entry_cost_lamports=1,
        book_value_lamports=1,
        opened_at=datetime.now(UTC),
        entry_fill_id="fill",
        market_status="dormant",
    )
    engine.broker.positions[position.mint] = position
    assert engine._coach_can_run() == (True, None)
    engine._event_batches_in_flight = 1
    assert engine._coach_can_run() == (True, None)
    engine.last_processing_lag_seconds = 2
    assert not engine._coach_can_run()[0]
    engine.last_processing_lag_seconds = 0
    engine._event_batches_in_flight = 0
    engine.broker.positions[position.mint] = position.model_copy(
        update={
            "market_status": type(position.market_status)("active"),
        }
    )
    assert engine._coach_can_run() == (False, "protecting_open_positions")
    asyncio.run(engine.http.close())
    engine.database.close()


def history_state():
    return ChallengerSkillState(
        cohort_key="history-cohort",
        skill=ChallengerSkill.ENTRY,
        risk_mode=RiskMode.BALANCED,
        configuration_fingerprint="history",
        baseline_version="baseline",
        feature_schema_version="features",
        champion_version="crown",
    )


def test_large_history_is_paged_and_crown_metadata_survives_the_memory_tail(settings):
    database = Database(settings.database_path)
    state = history_state()
    start = datetime.now(UTC) - timedelta(days=1)
    state.champion_journey = [
        ChallengerChampionEvent(
            event_id=f"event-{index:04}",
            occurred_at=start + timedelta(seconds=index),
            skill=state.skill,
            kind="first_champion" if index == 0 else "defended",
            candidate_version=f"candidate-{index}",
            champion_version="crown",
        )
        for index in range(1200)
    ]
    database.save_challenger_skill_state(state)
    assert len(state.champion_journey) == RECENT_CHAMPION_EVENTS_IN_MEMORY
    database.save_challenger_skill_state(state)
    loaded = database.list_challenger_skill_states()[0]
    assert len(loaded.champion_journey) == RECENT_CHAMPION_EVENTS_IN_MEMORY
    record = database.champion_record(loaded)
    assert record["history_complete"]
    assert record["champion_generation"] == 1
    assert record["retained_count"] == 1199
    seen, cursor = set(), None
    while True:
        page = database.champion_events_page(state.cohort_key, limit=47, cursor=cursor)
        assert page["total"] == 1200
        assert not seen.intersection(event.event_id for event, _ in page["events"])
        seen.update(event.event_id for event, _ in page["events"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == 1200
    with pytest.raises(ValueError, match="cohort"):
        database.champion_events_page("other", cursor="event-0000")
    database.close()


def test_v13_sidecar_migrates_once_without_changing_settings(settings):
    database = Database(settings.database_path)
    state = history_state()
    event = ChallengerChampionEvent(
        event_id="legacy-event",
        skill=state.skill,
        kind="first_champion",
        candidate_version="crown",
        champion_version="crown",
    )
    database.save_challenger_skill_state(state)
    database.set_setting("custom-drawdown", {"limit": 0.25})
    database.set_setting(
        database._challenger_journey_setting_key(state), [event.model_dump(mode="json")]
    )
    with database._conn:
        database._conn.execute("DROP TABLE challenger_champion_events")
        database._conn.execute("PRAGMA user_version=13")
    database.close()
    for _ in range(2):
        database = Database(settings.database_path)
        assert database.champion_events_page(state.cohort_key)["total"] == 1
        assert database.get_setting("custom-drawdown") == {"limit": 0.25}
        assert database.get_setting(database._challenger_journey_setting_key(state)) is None
        assert database.list_challenger_skill_states()[0].champion_journey == [event]
        raw = database._conn.execute("SELECT record_json FROM challenger_skill_states").fetchone()[
            0
        ]
        assert "champion_journey" not in json.loads(raw)
        database.close()


def test_failed_journal_migration_does_not_advance_schema_or_remove_sidecar(settings):
    database = Database(settings.database_path)
    state = history_state()
    database.save_challenger_skill_state(state)
    key = database._challenger_journey_setting_key(state)
    database.set_setting(key, [{"event_id": "malformed"}])
    with database._conn:
        database._conn.execute("PRAGMA user_version=13")
    database.close()
    with pytest.raises(ValueError):
        Database(settings.database_path)
    with sqlite3.connect(settings.database_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 13
        assert conn.execute("SELECT value_json FROM settings WHERE key=?", (key,)).fetchone()
        assert conn.execute("SELECT COUNT(*) FROM challenger_champion_events").fetchone()[0] == 0
        conn.execute("UPDATE settings SET value_json='[]' WHERE key=?", (key,))
    database = Database(settings.database_path)
    assert database._conn.execute("PRAGMA user_version").fetchone()[0] == 16
    database.close()
