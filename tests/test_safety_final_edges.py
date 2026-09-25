"""Cross-boundary checks for the idle recovery and immutable receipt additions."""

# ruff: noqa: F811 -- shared pytest fixtures

import asyncio
import json
from datetime import UTC, datetime
from threading import Event

import pytest
from signal_arcade.database import Database, MaintenanceReadDeferred
from signal_arcade.intelligence.features import TokenState
from signal_arcade.models import EventKind, MarketEvent
from signal_arcade.paper.broker import PaperBroker
from signal_arcade.paper.receipt_audit import fee_quote_replay_status
from test_broker import make_broker, make_decision, make_features
from test_probe_retention import engine  # noqa: F401
from test_publication_diagnostics import clock  # noqa: F401
from test_publication_pressure import queued_job


@pytest.mark.parametrize("arrival", ["urgent", "stop", "storage", "clock"])
def test_idle_training_rechecks_after_waiting_for_the_market_lock(
    engine, clock, monkeypatch, arrival
):
    engine.last_processing_lag_seconds = 2
    engine._last_market_batch_completed_monotonic = clock[0] - 5
    monkeypatch.setattr(engine.learning, "has_pending_training", lambda: True)
    monkeypatch.setattr(
        engine.learning,
        "prepare_next_training",
        lambda *_args: pytest.fail("admission changed while waiting"),
    )

    async def wait(_seconds):
        engine.stop_event.set()

    monkeypatch.setattr(engine, "_wait_for_stop", wait)

    async def exercise():
        await engine._event_lock.acquire()
        task = asyncio.create_task(engine._learning_trainer_loop())
        await asyncio.sleep(0)
        assert not task.done()
        if arrival == "urgent":
            engine.event_queue.put_nowait(
                (0, 1, MarketEvent(event_id="urgent", source="test", kind=EventKind.HEALTH))
            )
        elif arrival == "stop":
            engine.stop_event.set()
        elif arrival == "storage":
            engine._storage_maintenance_active = True
        else:
            clock[0] -= 1
        engine._event_lock.release()
        await asyncio.wait_for(task, 1)
        assert not engine._event_lock.locked()

    asyncio.run(exercise())


@pytest.mark.parametrize("lag", [0.1, 2])
def test_source_switch_keeps_a_dequeued_receipt_protected_until_completion(
    engine, clock, monkeypatch, lag
):
    engine.demo_mode = False
    engine.last_processing_lag_seconds = lag
    engine._last_market_batch_completed_monotonic = clock[0] - 10
    old = MarketEvent(event_id="old-source", source="solana:test", kind=EventKind.HEALTH)
    engine._event_sequence = 2
    engine.event_queue.put_nowait((0, 1, old))
    engine.event_queue.get_nowait()
    engine.event_queue.begin_boundary(1)
    engine.event_queue.put_nowait((0, 2, old.model_copy(update={"event_id": "parked"})))

    async def no_source():
        pass

    monkeypatch.setattr(engine, "_start_source", no_source)

    async def exercise():
        await engine.set_demo_mode(True)
        assert engine.event_queue.qsize() == 0
        assert engine.event_queue.has_admitted_work and engine.event_queue.has_dequeued_work
        assert not engine._learning_training_can_run()
        assert not engine._learning_publication_can_run()
        assert not await engine._handle_persisted_event(old, sequence=1)
        engine.event_queue.task_done()
        await asyncio.wait_for(engine.event_queue.join(), 1)
        assert not engine.event_queue.has_admitted_work
        assert not engine.event_queue.has_dequeued_work
        assert engine._learning_training_can_run()
        assert engine._learning_publication_can_run()

    asyncio.run(exercise())


@pytest.mark.parametrize("age,expected", [(120, True), (120.000001, False)])
def test_idle_publication_cannot_extend_its_original_lifetime(
    engine, clock, monkeypatch, age, expected
):
    engine.last_processing_lag_seconds = 2
    engine._last_market_batch_completed_monotonic = clock[0] - 10
    job = queued_job(engine)
    job.started_monotonic = clock[0]
    calls = []

    def collect(_job):
        clock[0] = job.started_monotonic + age

    def finish(_job, *, runtime_context, **_kwargs):
        valid = not engine.learning.training_job_stale(job, runtime_context)
        calls.append(valid)
        return valid

    monkeypatch.setattr(engine, "_collect_before_publication", collect)
    monkeypatch.setattr(engine.learning, "finish_training_job", finish)
    assert asyncio.run(engine._publish_training_job(engine.learning, job, None)) is expected
    assert calls == [expected]


@pytest.mark.parametrize("primary_result", ["complete", "error", "deferred"])
def test_optional_slow_reporting_cannot_replace_storage_result_or_error(
    engine, monkeypatch, primary_result
):
    def report_failure(*_args, **_kwargs):
        raise ValueError("optional reporting failure")

    def storage_failure():
        raise RuntimeError("original storage failure")

    def admitted_read(function, **_kwargs):
        # The reporting contract must survive all three admission outcomes, without
        # depending on whether the test host dispatches a worker within 50 ms.
        if primary_result == "deferred":
            raise MaintenanceReadDeferred("busy")
        return function()

    monkeypatch.setattr(engine.database, "maintenance_read", admitted_read)
    monkeypatch.setattr(engine.diagnostics.runtime_evidence, "observe_slow", report_failure)
    if primary_result == "error":
        monkeypatch.setattr(engine.database, "storage_capacity_stats", storage_failure)
        with pytest.raises(RuntimeError, match="original storage failure"):
            asyncio.run(engine._storage_maintenance_pass(datetime.now(UTC), Event()))
    else:
        asyncio.run(engine._storage_maintenance_pass(datetime.now(UTC), Event()))
        assert (engine._storage_maintenance_last_completed_at is not None) == (
            primary_result == "complete"
        )
    assert not engine._storage_maintenance_active
    assert engine._storage_idle.is_set()
    # A deferred initial capacity read now permits bounded age work and a final read.
    # Both optional capacity reports, plus the overall storage report, fail honestly.
    assert engine.diagnostics.loss_counts()["reporting_error"] == (
        2 if primary_result == "error" else 3
    )


@pytest.mark.parametrize(
    "metadata,expected",
    [
        (None, "unavailable"),
        ("broken", "unavailable"),
        ([1, 2], "unavailable"),
        ({"version": []}, "unavailable"),
        ({"version": 2}, "unavailable"),
        ({"version": 1}, "invalid_inputs"),
        (
            {
                "version": 1,
                "rounding": "aggregate",
                "fee_components": None,
                "lp_fee_bps": True,
                "source": "observed_event",
            },
            "invalid_inputs",
        ),
        (
            {
                "version": 1,
                "rounding": "aggregate",
                "fee_components": None,
                "lp_fee_bps": 0,
                "source": {"malformed": True},
            },
            "invalid_inputs",
        ),
    ],
)
def test_malformed_optional_fee_metadata_cannot_hide_a_held_position_on_restart(
    settings, metadata, expected
):
    database = Database(settings.database_path)
    broker = make_broker(database, settings)
    now = datetime.now(UTC)
    state = TokenState(
        mint="mint",
        symbol="TEST",
        last_event_at=now,
        last_reserve_at=now,
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_quote_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
        real_quote_reserves=20_000_000_000,
        fee_bps=125,
        reserve_fee_components=(25, 100),
    )
    order = broker.submit_decision(make_decision(now))
    assert order is not None
    receipt = broker._fill(order, state, make_features(now), "entry", now, None)
    assert receipt is not None
    cash = broker.cash_lamports
    holding = broker.positions["mint"].model_dump(mode="json")
    raw = receipt.model_dump(mode="json")
    raw["execution_fee_provenance"] = metadata
    damaged_optional_json = json.dumps(raw)
    with database._conn:
        database._conn.execute(
            "UPDATE fills SET record_json=? WHERE fill_id=?",
            (damaged_optional_json, receipt.fill_id),
        )
    database.close()
    database = Database(settings.database_path)
    try:
        restored = PaperBroker(database, settings)
        assert restored.cash_lamports == cash == database.ledger_balance("cash")
        assert restored.positions["mint"].model_dump(mode="json") == holding
        assert not restored.chronology_issues()
        assert fee_quote_replay_status(database.list_fills()[0], order) == expected
        assert database._conn.execute("SELECT record_json FROM fills").fetchone()[0] == (
            damaged_optional_json
        )
    finally:
        database.close()
