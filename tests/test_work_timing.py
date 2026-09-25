"""Optional measurements cannot change transactions, worker ownership or evidence."""

# ruff: noqa: F811 -- shared pytest fixtures

import asyncio
import copy
import json
import random
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from threading import Event, get_ident

import pytest
from signal_arcade.diagnostics_store import MAX_EVENT_PAYLOAD, encode
from signal_arcade.models import EventKind, RiskMode
from signal_arcade.orchestrator import _detailed_to_thread
from signal_arcade.work_timing import WORK_DETAIL, WORK_FIELDS, measure_work, measured_context
from test_broker import make_decision, make_features
from test_broker_work_budget import held  # noqa: F401
from test_probe_retention import engine  # noqa: F401


@pytest.mark.parametrize("ending", ["success", "error", "cancel"])
def test_measurement_waits_for_worker_even_on_repeated_cancellation(
    engine,
    monkeypatch,
    ending,  # noqa: F811
):
    started, release, finished = Event(), Event(), Event()
    marker = object()
    aggregate = engine.diagnostics.observe_work_detail
    owners = []

    def worker():
        with measure_work("rpc_validate"):
            started.set()
            assert release.wait(2)
            finished.set()
            if ending == "error":
                raise ValueError("worker error")
            return marker

    def observe(lane, detail):
        assert finished.is_set()
        owners.append(get_ident())
        aggregate(lane, detail)

    monkeypatch.setattr(engine.diagnostics, "observe_work_detail", observe)

    async def exercise():
        task = asyncio.create_task(_detailed_to_thread(engine.diagnostics, "rpc", worker))
        try:
            for _ in range(1000):
                if started.is_set():
                    break
                await asyncio.sleep(0.001)
            assert started.is_set() and not engine.diagnostics.work_detail_since_boot
            if ending == "cancel":
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
                assert not task.done()
        finally:
            release.set()
        if ending == "success":
            assert await task is marker
        else:
            with pytest.raises(asyncio.CancelledError if ending == "cancel" else ValueError):
                await task
        assert owners == [get_ident()]
        assert WORK_DETAIL.get() is None

    asyncio.run(exercise())
    assert engine.diagnostics.work_detail_since_boot["rpc"]["rpc_validate"][0] == 1


def test_disabled_and_failed_reporting_preserve_worker_result(engine, monkeypatch):  # noqa: F811
    marker = object()

    def worker():
        with measure_work("rpc_validate"):
            return marker

    engine.diagnostics.enabled = False
    assert asyncio.run(_detailed_to_thread(engine.diagnostics, "rpc", worker)) is marker
    assert not engine.diagnostics.work_detail_since_boot
    engine.diagnostics.enabled = True

    def fail(*args):
        raise ValueError("reporting failure")

    monkeypatch.setattr(engine.diagnostics, "observe_work_detail", fail)
    assert asyncio.run(_detailed_to_thread(engine.diagnostics, "rpc", worker)) is marker
    assert engine.diagnostics.loss_counts()["reporting_error"] == 1


def test_concurrent_worker_contexts_are_isolated(engine):  # noqa: F811
    def work(name):
        with measure_work(name):
            assert WORK_DETAIL.get() is not None

    async def exercise():
        await asyncio.gather(
            _detailed_to_thread(engine.diagnostics, "broker", work, "broker_mark"),
            _detailed_to_thread(engine.diagnostics, "rpc", work, "rpc_validate"),
        )

    asyncio.run(exercise())
    detail = engine.diagnostics.work_detail_since_boot
    assert set(detail["broker"]) == {"broker_mark", "broker_dispatch", "broker_resume"}
    assert set(detail["rpc"]) == {"rpc_validate", "rpc_dispatch", "rpc_resume"}


@pytest.mark.parametrize("failure", ["none", "sql", "commit"])
def test_decision_measurements_preserve_commit_and_failure_semantics(
    engine,
    monkeypatch,
    failure,  # noqa: F811
):
    database = engine.database
    decision = make_decision(datetime.now(UTC))
    if failure == "sql":
        database._conn.execute(
            "CREATE TEMP TRIGGER deny_decision BEFORE INSERT ON decisions "
            "BEGIN SELECT RAISE(ABORT, 'isolated denial'); END"
        )
    elif failure == "commit":
        connection = database._conn

        class FailingCommit:
            def __enter__(self):
                return connection.__enter__()

            def __exit__(self, *_args):
                connection.rollback()
                raise sqlite3.OperationalError("isolated commit failure")

            def execute(self, *args, **kwargs):
                return connection.execute(*args, **kwargs)

        monkeypatch.setattr(database, "_conn", FailingCommit())
    cache = database._season_strategy_cache
    if failure == "none":
        asyncio.run(
            _detailed_to_thread(engine.diagnostics, "decision", database.save_decision, decision)
        )
        saved = database.list_decisions()[0].model_dump(mode="json")
        assert saved == decision.model_dump(mode="json")
        # An unmeasured duplicate must preserve exactly the same durable decision.
        database.save_decision(decision)
        assert [row.model_dump(mode="json") for row in database.list_decisions()] == [saved]
    else:
        with pytest.raises(sqlite3.Error):
            asyncio.run(
                _detailed_to_thread(
                    engine.diagnostics, "decision", database.save_decision, decision
                )
            )
        assert not database.list_decisions()
        assert database._season_strategy_cache == cache
        assert database._lock.acquire(timeout=0.1)
        database._lock.release()
    assert set(engine.diagnostics.work_detail_since_boot["decision"]) == WORK_FIELDS["decision"]
    monkeypatch.undo()  # Restore the connection before the engine fixture closes it.


@pytest.mark.parametrize("body_error,exit_error", [(False, False), (True, False), (False, True)])
def test_context_wrapper_preserves_body_and_exit_exceptions(body_error, exit_error):
    trace, detail = [], {}

    @contextmanager
    def manager():
        try:
            yield
        finally:
            trace.append("exit")
            if exit_error:
                raise LookupError("exit")

    token = WORK_DETAIL.set(detail)
    try:

        def exercise():
            with measured_context(manager(), enter="decision_lock", exit="decision_commit"):
                trace.append("body")
                if body_error:
                    raise ValueError("body")

        if body_error or exit_error:
            with pytest.raises(ValueError if body_error else LookupError):
                exercise()
        else:
            exercise()
    finally:
        WORK_DETAIL.reset(token)
    assert trace == ["body", "exit"]
    assert detail["decision_lock"][0] == detail["decision_commit"][0] == 1


def test_measured_broker_update_preserves_mark_and_durable_assessment(held):  # noqa: F811
    broker, database, state, now = held
    state.last_event_at = state.last_reserve_at = now
    kwargs = dict(
        state=state,
        features=make_features(now),
        event_kind=EventKind.TRADE,
        source_event_id="tick",
        now=now,
        mode=RiskMode.BALANCED,
    )
    assert broker.on_market_state(**kwargs) == []
    before = copy.deepcopy(broker.positions)
    detail = {}
    token = WORK_DETAIL.set(detail)
    try:
        assert broker.on_market_state(**kwargs) == []
    finally:
        WORK_DETAIL.reset(token)
    assert broker.positions == before
    assert database.list_positions() == list(before.values())
    assert detail["position_save"][0] == 2
    assert detail["broker_mark"][0] == detail["broker_assess"][0] == 1


def test_detail_payloads_remain_bounded_and_yield_to_proof(engine):  # noqa: F811
    rng = random.Random(18)  # noqa: S311 -- deterministic payload compression fixture
    for lane, names in WORK_FIELDS.items():
        engine.diagnostics.observe_work_detail(
            lane,
            {
                name: [rng.randrange(2**51, 2**52), rng.random() * 1e12, rng.random() * 1e11]
                for name in names
            },
        )
    for _ in range(8):
        engine.diagnostics.event({"kind": "proof"})
    engine._record_collection_detail_diagnostics()
    assert len(engine.diagnostics.events) == 8
    assert engine.diagnostics.total_dropped == 0
    engine.diagnostics._take_events(0)
    engine._record_collection_detail_diagnostics()
    events = [event for event in engine.diagnostics.events if event["kind"] == "work_detail"]
    assert len(events) == len(WORK_FIELDS)
    for event in events:
        assert len(json.dumps(event).encode()) <= 2048
        encode(event, max_payload=MAX_EVENT_PAYLOAD)
    engine.diagnostics._take_events(0)
    engine._record_collection_detail_diagnostics()
    assert not engine.diagnostics.events


def test_invalid_dimensions_and_saturation_stay_bounded(engine):  # noqa: F811
    recorder = engine.diagnostics
    recorder.observe_work_detail(
        "rpc", {"unknown": [1, 2, 3], "rpc_validate": [1, float("nan"), 2]}
    )
    assert not recorder.work_detail_since_boot
    for _ in range(2):
        recorder.observe_work_detail("rpc", {"rpc_validate": [2**53 - 1, 1e12, 1e12]})
    assert recorder.work_detail_since_boot["rpc"]["rpc_validate"] == [2**53 - 1, 1e12, 1e12]
