import asyncio
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
import signal_arcade.coach as coach_module
from signal_arcade.database import Database
from signal_arcade.models import CoachExperimentState
from test_coach import _hypothesis
from test_coach_pressure import coach_for


@pytest.mark.parametrize("coach_table", [False, True])
def test_retained_work_index_is_installed_for_existing_coach_tables(tmp_path, coach_table):
    path = tmp_path / "coach-index.sqlite3"
    database = Database(path)
    with database._conn:
        database._conn.execute("DROP INDEX IF EXISTS idx_coach_work")
        if not coach_table:
            database._conn.execute("DROP TABLE coach_hypotheses")
    database.close()
    database = Database(path)
    try:
        index = database._reader_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_coach_work'"
        ).fetchone()
        assert bool(index) is coach_table
        if coach_table:
            plan = database._reader_conn.execute(
                "EXPLAIN QUERY PLAN SELECT created_at,hypothesis_id,record_json "
                "FROM coach_hypotheses WHERE state='testing' "
                "AND (created_at,hypothesis_id)>(?,?) "
                "ORDER BY created_at,hypothesis_id LIMIT 25",
                ("", ""),
            ).fetchall()
            assert any("idx_coach_work" in row[3] for row in plan)
    finally:
        database.close()


@pytest.mark.parametrize("busy", [False, True])
def test_optional_lookup_defers_only_transient_database_errors(tmp_path, monkeypatch, busy):
    database = Database(tmp_path / "busy-error.sqlite3")
    coach = coach_for(database)
    coach.contribution_enabled = lambda: True

    def fail(*args, **kwargs):
        error = sqlite3.OperationalError("injected database failure")
        error.sqlite_errorcode = sqlite3.SQLITE_BUSY if busy else sqlite3.SQLITE_ERROR
        raise error

    monkeypatch.setattr(database, "get_setting", fail)
    try:
        if busy:
            assert coach.ready_contribution() is None
        else:
            with pytest.raises(sqlite3.OperationalError):
                coach.ready_contribution()
        monkeypatch.undo()
        assert coach.ready_contribution() is None
    finally:
        database.close()


def test_optional_contribution_lookup_does_not_wait_for_busy_reader(tmp_path):
    database = Database(tmp_path / "reader-busy.sqlite3")
    hypothesis = _hypothesis(datetime.now(UTC)).model_copy(
        update={
            "state": CoachExperimentState.PROMISING,
            "contribution_state": "ready",
        }
    )
    database.save_coach_hypothesis(hypothesis)
    coach = coach_for(database)
    coach.contribution_enabled = lambda: True
    try:
        with ThreadPoolExecutor(max_workers=1) as worker, database._reader_lock:
            assert worker.submit(coach.ready_contribution).result(timeout=1) is None
        assert coach.ready_contribution() == hypothesis
        assert database.coach_hypothesis(hypothesis.hypothesis_id) == hypothesis
    finally:
        database.close()


@pytest.mark.parametrize("operation", ["read", "refresh", "active"])
@pytest.mark.parametrize("worker_error", [False, True])
def test_repeated_cancellation_joins_coach_workers(tmp_path, monkeypatch, operation, worker_error):
    database = Database(tmp_path / "cancel.sqlite3")
    coach = coach_for(database)
    entered, release, exited = threading.Event(), threading.Event(), threading.Event()

    def blocked(*args, **kwargs):
        entered.set()
        try:
            assert release.wait(5)
            if worker_error:
                raise RuntimeError("injected worker failure")
            return []
        finally:
            exited.set()

    target = {
        "read": "recent_learning_observations",
        "refresh": "_refresh_hypotheses",
        "active": "_active_hypothesis",
    }[operation]
    monkeypatch.setattr(database if operation == "read" else coach, target, blocked)

    async def exercise():
        task = asyncio.create_task(coach.tick())
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0.02)
            assert not task.done(), "Coach abandoned a live worker during shutdown"
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert await asyncio.to_thread(exited.wait, 3)

    try:
        asyncio.run(exercise())
    finally:
        database.close()


def test_work_pages_advance_over_equal_times_and_damaged_rows(tmp_path):
    database = Database(tmp_path / "pages.sqlite3")
    now = datetime.now(UTC)
    try:
        for index in range(29):
            database.save_coach_hypothesis(
                _hypothesis(now).model_copy(
                    update={
                        "hypothesis_id": f"study-{index:02}",
                        "signature": f"signature-{index}",
                    }
                )
            )
        with database._conn:
            database._conn.execute(
                "UPDATE coach_hypotheses SET record_json='broken' WHERE hypothesis_id='study-24'"
            )
        first, cursor = database.coach_work_page()
        second, final = database.coach_work_page(cursor)
        assert len(first) == 24 and len(second) == 4 and final is None
        assert cursor == (now.isoformat(), "study-24")
        assert not set(item.hypothesis_id for item in first).intersection(
            item.hypothesis_id for item in second
        )
        assert len(coach_for(database).hypotheses) == 28
    finally:
        database.close()


@pytest.mark.parametrize(
    "difference",
    [None, "dependency", "configuration_fingerprint", "baseline_version", "feature_schema_version"],
)
def test_retained_work_respects_exact_contract_and_dependency_order(tmp_path, difference):
    database = Database(tmp_path / "context.sqlite3")
    now = datetime.now(UTC)
    hypothesis = _hypothesis(now).model_copy(
        update={
            "dependency_versions": {"exit": "exit-v1", "sizing": "size-v2"},
            "state": CoachExperimentState.PROMISING,
            "contribution_state": "ready",
        }
    )
    database.save_coach_hypothesis(hypothesis)
    coach = coach_for(database)
    context = coach._context_provenance()
    context["dependency_versions"] = {"sizing": "size-v2", "exit": "exit-v1"}
    if difference == "dependency":
        context["dependency_versions"]["entry"] = "new-entry"
    elif difference:
        context[difference] = "different"
    try:
        assert bool(database.coach_context_hypotheses(context, contributions=True)) == (
            difference is None
        )
    finally:
        database.close()


def test_stale_refresh_cannot_overwrite_durable_contribution(tmp_path):
    database = Database(tmp_path / "cas.sqlite3")
    hypothesis = _hypothesis(datetime.now(UTC)).model_copy(
        update={
            "state": CoachExperimentState.PROMISING,
            "contribution_state": "ready",
        }
    )
    database.save_coach_hypothesis(hypothesis)
    coach = coach_for(database)
    try:
        coach.mark_contribution(hypothesis.hypothesis_id, "handed_off", "artifact")
        assert not database.save_coach_hypothesis_if_current(
            hypothesis, hypothesis.model_copy(update={"forward_observed_count": 99})
        )
        coach.mark_contribution(hypothesis.hypothesis_id, "waiting_for_champion")
        assert database.list_coach_hypotheses()[0].contribution_state == "handed_off"
        assert database.get_setting("coach_contribution_cursor") is None
    finally:
        database.close()


def test_old_active_study_blocks_new_study_and_old_ready_study_can_handoff(tmp_path):
    database = Database(tmp_path / "old-work.sqlite3")
    now = datetime.now(UTC)
    active = _hypothesis(now - timedelta(days=2))
    ready = active.model_copy(
        update={
            "hypothesis_id": "ready-old",
            "signature": "ready-old",
            "state": CoachExperimentState.PROMISING,
            "contribution_state": "ready",
        }
    )
    database.save_coach_hypothesis(active)
    database.save_coach_hypothesis(ready)
    for index in range(101):
        database.save_coach_hypothesis(
            _hypothesis(now).model_copy(
                update={
                    "hypothesis_id": f"terminal-{index}",
                    "signature": f"terminal-{index}",
                    "state": CoachExperimentState.INCONCLUSIVE,
                }
            )
        )
    try:
        coach = coach_for(database)
        assert coach._active_hypothesis(coach._context_provenance()) == active
        assert coach.ready_contribution() is None  # Permission remains mandatory.
        coach.contribution_enabled = lambda: True
        assert coach.ready_contribution() == ready
        coach.mark_contribution(ready.hypothesis_id, "handed_off", "artifact")
        assert coach.ready_contribution() is None
        assert len(coach.hypotheses) <= 100
    finally:
        database.close()


def test_refresh_preserves_concurrent_handoff(tmp_path, monkeypatch):
    database = Database(tmp_path / "handoff.sqlite3")
    hypothesis = _hypothesis(datetime.now(UTC)).model_copy(
        update={
            "state": CoachExperimentState.PROMISING,
            "contribution_state": "ready",
        }
    )
    database.save_coach_hypothesis(hypothesis)
    coach = coach_for(database)
    original = coach_module._evaluate_hypothesis

    def overlapping(item, rows, now):
        coach.mark_contribution(item.hypothesis_id, "handed_off", "durable-artifact")
        return original(item, rows, now)

    monkeypatch.setattr(coach_module, "_evaluate_hypothesis", overlapping)
    try:
        coach._refresh_hypotheses(datetime.now(UTC), [])
        assert coach.hypotheses[0].contribution_state == "handed_off"
        assert coach.hypotheses[0].contributed_artifact_version == "durable-artifact"
        assert database.list_coach_hypotheses()[0] == coach.hypotheses[0]
    finally:
        database.close()


def test_waiting_contributions_retry_fairly_across_restart(tmp_path):
    database = Database(tmp_path / "fair.sqlite3")
    now = datetime.now(UTC)
    for index in range(3):
        database.save_coach_hypothesis(
            _hypothesis(now + timedelta(seconds=index)).model_copy(
                update={
                    "hypothesis_id": f"waiting-{index}",
                    "signature": f"signature-{index}",
                    "state": CoachExperimentState.PROMISING,
                    "contribution_state": "waiting_for_champion",
                }
            )
        )
    selected_ids = []
    try:
        for _ in range(3):
            coach = coach_for(database)
            coach.contribution_enabled = lambda: True
            selected = coach.ready_contribution()
            assert selected is not None
            selected_ids.append(selected.hypothesis_id)
            coach.mark_contribution(selected.hypothesis_id, "waiting_for_champion")
        assert len(set(selected_ids)) == 3
    finally:
        database.close()


def test_protected_study_older_than_display_window_is_processed(tmp_path):
    database = Database(tmp_path / "retained.sqlite3")
    now = datetime.now(UTC)
    old = _hypothesis(now - timedelta(days=91))
    database.save_coach_hypothesis(old)
    for index in range(101):
        database.save_coach_hypothesis(
            _hypothesis(now).model_copy(
                update={
                    "hypothesis_id": f"terminal-{index}",
                    "signature": f"terminal-signature-{index}",
                    "state": CoachExperimentState.INCONCLUSIVE,
                }
            )
        )
    database.prune_coach_history()
    try:
        coach = coach_for(database)
        coach._refresh_hypotheses(now, [])
        persisted = next(
            item
            for item in database.list_coach_hypotheses(200)
            if item.hypothesis_id == old.hypothesis_id
        )
        assert persisted.state == CoachExperimentState.INCONCLUSIVE
    finally:
        database.close()
