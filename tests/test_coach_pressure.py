from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.coach import AiCoach
from signal_arcade.database import AdvisoryReadDeferred, Database
from signal_arcade.models import LearningObservation, RiskMode
from test_coach import FakeCoachHttp, _observation


def coach_for(database, *, can_run=lambda: (True, None)):
    return AiCoach(
        database,
        FakeCoachHttp(),
        enabled=lambda: True,
        context=lambda: (RiskMode.BALANCED, "fp"),
        outcomes_seen=lambda: 80,
        model_provenance=lambda: ("fixture", "fixture-digest"),
        can_run=can_run,
    )


def seed(database, count=80):
    now = datetime.now(UTC) - timedelta(hours=1)
    for index in range(count):
        # Include equal timestamps and unknown outcomes in the cohort boundary checks.
        database.save_learning_observation(
            _observation(
                index, now + timedelta(seconds=index // 3), outcome=None if index % 4 == 0 else 0.2
            )
        )


@pytest.mark.parametrize("limit", [0, 1, 5, 75, 5000])
def test_detached_history_preserves_the_original_cohort_and_order(tmp_path, limit):
    database = Database(tmp_path / "history.sqlite3")
    try:
        seed(database)
        original = database._reader_conn.execute(
            "SELECT record_json FROM learning_observations ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        expected = [LearningObservation.model_validate_json(row[0]) for row in reversed(original)]
        assert database.recent_learning_observations(limit) == expected
    finally:
        database.close()


def test_coach_does_not_read_or_refresh_evidence_during_pressure(tmp_path, monkeypatch):
    database = Database(tmp_path / "pressure.sqlite3")
    coach = coach_for(database, can_run=lambda: (False, "protecting_market_throughput"))
    monkeypatch.setattr(
        database,
        "recent_learning_observations",
        lambda *_args, **_kw: pytest.fail("read while busy"),
    )
    monkeypatch.setattr(
        coach, "_refresh_hypotheses", lambda *_: pytest.fail("evaluated while busy")
    )
    try:
        asyncio.run(coach.tick())
        assert coach.paused_reason == "protecting_market_throughput"
        assert coach.last_error is None
        assert coach.http.calls == 0
    finally:
        database.close()


def test_history_read_does_not_use_either_core_database_lock(tmp_path):
    database = Database(tmp_path / "locks.sqlite3")
    try:
        seed(database, 30)
        with (
            ThreadPoolExecutor(max_workers=1) as worker,
            database._reader_lock,
            database._lock,
        ):
            future = worker.submit(database.recent_learning_observations, 5000)
            assert len(future.result(timeout=2)) == 30
    finally:
        database.close()


def test_pressure_during_read_discards_partial_cohort_and_then_recovers(tmp_path):
    database = Database(tmp_path / "partial.sqlite3")
    checks = 0

    def pressure():
        nonlocal checks
        checks += 1
        return checks > 35

    try:
        seed(database)
        with pytest.raises(AdvisoryReadDeferred):
            database.recent_learning_observations(5000, should_yield=pressure)
        assert len(database.recent_learning_observations(5000, should_yield=lambda: False)) == 80
    finally:
        database.close()


def test_deferred_coach_read_cannot_evaluate_a_partial_experiment(tmp_path, monkeypatch):
    database = Database(tmp_path / "deferred.sqlite3")
    coach = coach_for(database)

    def defer(*_args, **_kwargs):
        raise AdvisoryReadDeferred

    monkeypatch.setattr(database, "recent_learning_observations", defer)
    monkeypatch.setattr(
        coach, "_refresh_hypotheses", lambda *_: pytest.fail("partial evidence used")
    )
    try:
        asyncio.run(coach.tick())
        assert coach.last_error is None
        assert coach.http.calls == 0
        assert database.list_coach_reviews() == []
    finally:
        database.close()


def test_cancelled_coach_read_stops_its_detached_worker(tmp_path, monkeypatch):
    database = Database(tmp_path / "cancel.sqlite3")
    coach = coach_for(database)
    entered, finished = threading.Event(), threading.Event()

    def wait_for_cancel(*_args, should_yield, pause):
        entered.set()
        try:
            while not should_yield():
                finished.wait(0.01)
            raise AdvisoryReadDeferred
        finally:
            finished.set()

    monkeypatch.setattr(database, "recent_learning_observations", wait_for_cancel)

    async def scenario():
        task = asyncio.create_task(coach.tick())
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await asyncio.to_thread(finished.wait, 2)

    try:
        asyncio.run(scenario())
        assert coach.http.calls == 0
    finally:
        database.close()


@pytest.mark.parametrize("change", ["pressure", "context", "paused"])
def test_candidate_screening_yields_and_rechecks_context_before_inference(
    tmp_path, monkeypatch, change
):
    import signal_arcade.coach as module

    monkeypatch.setattr(module, "COACH_OPTIONAL_WORK_SECONDS", 0.3)

    database = Database(tmp_path / "screen.sqlite3")
    seed(database, 30)
    permitted, enabled = True, True
    context = (RiskMode.BALANCED, "fp")
    coach = coach_for(database, can_run=lambda: (permitted, "protecting_market_throughput"))
    coach.enabled = lambda: enabled
    coach.context = lambda: context
    entered, release = threading.Event(), threading.Event()
    original = module._build_candidates

    def screen(*args, **kwargs):
        entered.set()
        assert release.wait(2), "screening blocked the event loop"
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "_build_candidates", screen)

    async def scenario():
        nonlocal permitted, enabled, context
        task = asyncio.create_task(coach.tick())
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            if change == "pressure":
                permitted = False
            elif change == "context":
                context = (RiskMode.SAFE, "changed")
            else:
                enabled = False
        finally:
            release.set()
        await task

    try:
        asyncio.run(scenario())
        assert coach.http.calls == 0
        assert coach.busy is False
        assert database.list_coach_reviews() == []
    finally:
        database.close()


def test_coach_yields_to_active_learning_fit(settings, monkeypatch):
    from signal_arcade.orchestrator import Orchestrator

    engine = Orchestrator(settings)
    try:
        engine.demo_mode = False
        assert engine._coach_can_run() == (True, None)
        monkeypatch.setattr(engine.learning, "_training_active", object())
        assert engine._coach_can_run() == (False, "protecting_market_throughput")
    finally:
        engine.database.close()


def test_normal_market_batches_and_healthy_positions_allow_optional_research(settings):
    from signal_arcade.models import Position
    from signal_arcade.orchestrator import Orchestrator

    engine = Orchestrator(settings)
    now = datetime.now(UTC)
    position = Position(
        position_id="held",
        mint="mint",
        symbol="T",
        token_units=1,
        entry_cost_lamports=1,
        book_value_lamports=1,
        opened_at=now,
        entry_fill_id="fill",
        last_marked_at=now,
        mark_is_stale=False,
        mark_is_executable=True,
        market_status="active",
    )
    try:
        engine.demo_mode = False
        engine._event_batches_in_flight = 1
        engine.broker.positions[position.mint] = position
        assert engine._coach_can_run() == (True, None)
        for updates in (
            {"mark_is_executable": False},
            {"mark_is_stale": True},
            {"last_marked_at": now - timedelta(hours=1)},
            {"opened_at": now - timedelta(hours=1)},
        ):
            engine.broker.positions[position.mint] = position.model_copy(update=updates)
            assert engine._coach_can_run() == (False, "protecting_open_positions")
        engine.broker.positions.clear()
        engine.last_processing_lag_seconds = 2
        assert engine._coach_can_run() == (False, "protecting_market_throughput")
    finally:
        engine.database.close()


def test_coach_pauses_and_resumes_the_same_complete_snapshot(tmp_path, monkeypatch):
    database = Database(tmp_path / "resume.sqlite3")
    seed(database)
    coach = coach_for(database)
    expected = database.recent_learning_observations(5000)
    pressure, entered = threading.Event(), threading.Event()
    coach.can_run = lambda: (not pressure.is_set(), "protecting_market_throughput")
    original = database.recent_learning_observations

    def read(*args, pause, **kwargs):
        count = 0

        def checkpoint():
            nonlocal count
            count += 1
            if count == 3:
                pressure.set()
                entered.set()
            pause()

        return original(*args, pause=checkpoint, **kwargs)

    monkeypatch.setattr(database, "recent_learning_observations", read)

    async def scenario():
        task = asyncio.create_task(
            coach._optional_work(database.recent_learning_observations, 5000)
        )
        assert await asyncio.to_thread(entered.wait, 2)
        assert not task.done()
        pressure.clear()
        assert await task == expected

    try:
        asyncio.run(scenario())
    finally:
        database.close()


def test_cooperative_screening_preserves_candidate_values(tmp_path):
    from signal_arcade.coach import _build_candidates

    database = Database(tmp_path / "screen-parity.sqlite3")
    try:
        seed(database)
        observations = database.recent_learning_observations(5000)
        checkpoints = []
        assert _build_candidates(observations, RiskMode.BALANCED, "fp", set()) == _build_candidates(
            observations, RiskMode.BALANCED, "fp", set(), pause=lambda: checkpoints.append(True)
        )
        assert len(checkpoints) > 10
    finally:
        database.close()


def test_retry_backoff_without_forward_work_skips_history_read(tmp_path, monkeypatch):
    database = Database(tmp_path / "backoff.sqlite3")
    coach = coach_for(database)
    coach.next_attempt_at = datetime.now(UTC) + timedelta(minutes=5)
    monkeypatch.setattr(
        database,
        "recent_learning_observations",
        lambda *args, **kwargs: pytest.fail("unnecessary history read during backoff"),
    )
    try:
        asyncio.run(coach.tick())
        assert coach.paused_reason == "retry_backoff"
    finally:
        database.close()


def test_retry_backoff_still_advances_forward_evidence(tmp_path):
    from test_coach import _hypothesis

    database = Database(tmp_path / "forward-backoff.sqlite3")
    seed(database, 30)
    hypothesis = _hypothesis(datetime.now(UTC) - timedelta(hours=2))
    database.save_coach_hypothesis(hypothesis)
    coach = coach_for(database)
    coach.next_attempt_at = datetime.now(UTC) + timedelta(minutes=5)
    try:
        asyncio.run(coach.tick())
        assert database.coach_hypothesis(hypothesis.hypothesis_id).forward_observed_count == 30
        assert coach.http.calls == 0
    finally:
        database.close()


def test_pressure_during_forward_refresh_defers_then_recovers_complete_proof(tmp_path, monkeypatch):
    import signal_arcade.coach as module
    from test_coach import _hypothesis

    database = Database(tmp_path / "forward-pressure.sqlite3")
    seed(database, 30)
    hypothesis = _hypothesis(datetime.now(UTC) - timedelta(hours=2))
    database.save_coach_hypothesis(hypothesis)
    permitted = True
    coach = coach_for(database, can_run=lambda: (permitted, "protecting_market_throughput"))
    original = module._evaluate_hypothesis
    monkeypatch.setattr(module, "COACH_OPTIONAL_WORK_SECONDS", 0.05)

    def pressure(*args, **kwargs):
        nonlocal permitted
        permitted = False
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "_evaluate_hypothesis", pressure)
    try:
        asyncio.run(coach.tick())
        assert database.coach_hypothesis(hypothesis.hypothesis_id) == hypothesis
        assert coach.last_error is None
        assert coach.paused_reason == "protecting_market_throughput"
        permitted = True
        monkeypatch.setattr(module, "_evaluate_hypothesis", original)
        monkeypatch.setattr(module, "COACH_OPTIONAL_WORK_SECONDS", 30)
        asyncio.run(coach.tick())
        assert database.coach_hypothesis(hypothesis.hypothesis_id).forward_observed_count == 30
    finally:
        database.close()
