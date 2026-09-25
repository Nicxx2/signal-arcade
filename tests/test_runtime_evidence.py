"""Observational evidence remains bounded and cannot take trading authority."""

# ruff: noqa: F811 -- shared fixtures

import asyncio
import json
import random
import sqlite3
from threading import Event, get_ident

import pytest
from signal_arcade.diagnostics_store import MAX_EVENT_PAYLOAD, encode
from signal_arcade.models import EventKind, MarketEvent
from signal_arcade.orchestrator import _timed_to_thread
from signal_arcade.runtime_evidence import ADMISSION_REASONS, SLOW_FIELDS, RuntimeEvidence
from signal_arcade.work_timing import WORK_DETAIL, measure_work
from test_probe_retention import engine  # noqa: F401
from test_publication_diagnostics import clock  # noqa: F401


@pytest.mark.parametrize("lane", list(SLOW_FIELDS))
def test_slowest_sample_is_coherent_detached_and_released_only_on_exact_handoff(lane):
    evidence = RuntimeEvidence()
    field = SLOW_FIELDS[lane][0]
    phases = {field: 3.0, "not-a-fixed-dimension": 100.0}
    evidence.observe_slow(lane, started=10, finished=14, at=100, phases=phases, outcome="yielded")
    phases[field] = 999
    evidence.observe_slow(
        lane, started=20, finished=21, at=110, phases={field: 0.5}, outcome="complete"
    )
    sample = evidence.slow_event(lane, "boot")
    assert sample["elapsed"] == 4 and sample["phases"] == {field: 3}
    sample["phases"][field] = 888
    assert evidence.slow[lane]["phases"][field] == 3
    evidence.observe_slow(lane, started=30, finished=35, at=120, phases={}, outcome="error")
    evidence.collected(sample)
    assert evidence.slow[lane]["outcome"] == "error"
    evidence.collected(evidence.slow_event(lane, "boot"))
    assert not evidence.slow


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_bad_clocks_or_phases_do_not_create_invented_measurements(value):
    evidence = RuntimeEvidence()
    evidence.observe_slow("storage", started=value, finished=2, at=100, phases={}, outcome="error")
    assert not evidence.slow
    evidence.observe_slow(
        "storage",
        started=1,
        finished=2,
        at=100,
        phases={"history_seconds": value},
        outcome="complete",
    )
    assert evidence.slow["storage"]["phases"] == {}
    evidence.wake_delay(value)
    assert evidence.wake == [0, 0, 0]


def test_fixed_counters_and_samples_fit_real_encoding_limits():
    rng = random.Random(915)  # noqa: S311 -- repeatable high-entropy payload fixture
    evidence = RuntimeEvidence()
    for counts in (evidence.collection, evidence.before, evidence.after, evidence.writer):
        for key in counts:
            counts[key] = rng.randrange(2**52, 2**53)
    for lane, fields in SLOW_FIELDS.items():
        evidence.observe_slow(
            lane,
            started=123456.123456,
            finished=123456.987654,
            at=1800000000.654321,
            phases={key: rng.random() * 1e12 for key in fields},
            outcome="complete",
        )
    events = [evidence.collector_event("a" * 32, 1800000000.123456)]
    events.extend(evidence.slow_event(lane, "a" * 32) for lane in SLOW_FIELDS)
    for event in events:
        if event["kind"] == "slow_work":
            event["sample"] = 2**53 - 1
        assert len(json.dumps(event, separators=(",", ":")).encode()) <= 2048
        encode(event, max_payload=MAX_EVENT_PAYLOAD)
    evidence.collection["attempt"] = 2**53 - 1
    for _ in range(10):
        evidence.collection_result("attempt")
        evidence.collection_result("unknown", "unbounded-name")
    assert evidence.collection["attempt"] == 2**53 - 1
    assert set(evidence.before) == set(ADMISSION_REASONS)
    assert len(evidence.slow) == len(SLOW_FIELDS)


def test_due_deferrals_use_one_primary_reason_and_keep_the_lock_counter_meaning(
    engine, clock, monkeypatch
):
    clock[0] += 61
    engine._maintenance_requested = True
    engine._storage_maintenance_active = True
    engine.diagnostics.queue.append(b"{}")
    turns = []

    async def wait(_seconds):
        turns.append(True)
        clock[0] += 7
        if len(turns) == 2:
            engine.stop_event.set()

    monkeypatch.setattr(engine, "_wait_for_stop", wait)
    asyncio.run(engine._diagnostics_loop())
    observed = engine.diagnostics.runtime_evidence
    assert observed.collection["attempt"] == 2
    assert observed.before["maintenance"] == 2
    assert sum(observed.before.values()) == 2
    assert observed.writer["maintenance"] == 2
    assert observed.wake == [1, 2, 2]
    assert engine.diagnostics.collection_deferred == 0
    assert engine.diagnostics.collection_due()
    assert engine.diagnostics.total_dropped == 0


def test_proof_pressure_keeps_slow_sample_pending_then_releases_detached_copy(engine, clock):
    recorder = engine.diagnostics
    recorder.runtime_evidence.observe_slow(
        "storage", started=1, finished=8, at=100, phases={"history_seconds": 6}, outcome="complete"
    )
    for _ in range(8):
        recorder.event({"kind": "proof"})
    engine._record_collection_detail_diagnostics()
    assert "storage" in recorder.runtime_evidence.slow
    assert recorder.total_dropped == 0
    recorder.events.clear()
    engine._record_collection_detail_diagnostics()
    sample = next(e for e in recorder.events if e["kind"] == "slow_work")
    assert sample["elapsed"] == 7 and "storage" in recorder.runtime_evidence.slow
    recorder._take_events(100)
    assert not recorder.runtime_evidence.slow
    recorder.runtime_evidence.observe_slow(
        "storage", started=10, finished=12, at=110, phases={}, outcome="complete"
    )
    engine._record_collection_detail_diagnostics()
    assert "storage" in recorder.runtime_evidence.slow  # Five-minute optional cooldown.
    assert sample["elapsed"] == 7


@pytest.mark.parametrize("ending", ["success", "error", "cancel"])
def test_persistence_measurement_joins_worker_and_keeps_its_result(engine, monkeypatch, ending):
    entered, release, finished = Event(), Event(), Event()
    owner = get_ident()
    original = engine.diagnostics.observe_work_detail

    def observe(lane, detail):
        assert finished.is_set() and get_ident() == owner
        original(lane, detail)

    def worker():
        with measure_work("persist_sql"):
            entered.set()
            assert release.wait(2)
            finished.set()
            if ending == "error":
                raise ValueError("original worker error")
            return 17

    monkeypatch.setattr(engine.diagnostics, "observe_work_detail", observe)

    async def run():
        task = asyncio.create_task(_timed_to_thread(engine.diagnostics, "event_persist", worker))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            if ending == "cancel":
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
                assert not task.done()
        finally:
            release.set()
        if ending == "success":
            assert await task == 17
        else:
            with pytest.raises(asyncio.CancelledError if ending == "cancel" else ValueError):
                await task
        assert WORK_DETAIL.get() is None

    asyncio.run(run())
    detail = engine.diagnostics.work_detail_since_boot["persist"]
    assert detail["persist_sql"][0] == detail["persist_worker"][0] == 1
    sample = engine.diagnostics.runtime_evidence.slow["persist"]
    assert (
        sample["outcome"]
        == {"success": "complete", "error": "error", "cancel": "cancelled"}[ending]
    )


@pytest.mark.parametrize("failure", ["none", "sql", "serialization", "commit"])
def test_persist_transaction_and_duplicates_preserve_atomicity(engine, monkeypatch, failure):
    database = engine.database
    rows = [
        MarketEvent(event_id=f"event-{i}", source="test", kind=EventKind.TRADE) for i in range(2)
    ]
    if failure == "sql":
        database._conn.execute(
            "CREATE TEMP TRIGGER deny_event BEFORE INSERT ON market_events "
            "WHEN NEW.event_id='event-1' BEGIN SELECT RAISE(ABORT, 'fixture denial'); END"
        )
    elif failure == "serialization":
        rows[1].payload = {"not_serializable": object()}
    elif failure == "commit":
        connection = database._conn

        class FailingCommit:
            def __enter__(self):
                return connection.__enter__()

            def __exit__(self, *_args):
                connection.rollback()
                raise sqlite3.OperationalError("fixture commit failure")

            def execute(self, *args, **kwargs):
                return connection.execute(*args, **kwargs)

        monkeypatch.setattr(database, "_conn", FailingCommit())
    if failure == "none":
        assert asyncio.run(
            _timed_to_thread(engine.diagnostics, "event_persist", database.append_events, rows)
        ) == {r.event_id for r in rows}
        assert database.append_events(rows) == set()
        assert len(database.recent_events()) == 2
        assert database.append_events([]) == set()
    else:
        with pytest.raises(TypeError if failure == "serialization" else sqlite3.Error):
            asyncio.run(
                _timed_to_thread(engine.diagnostics, "event_persist", database.append_events, rows)
            )
        assert database.recent_events() == []
    assert database._lock.acquire(timeout=0.1)
    database._lock.release()
    assert engine.diagnostics.work_detail_since_boot["persist"]["persist_transaction"][0] == 1
    monkeypatch.undo()


def test_reporting_failure_or_disabled_diagnostics_cannot_change_persistence(engine, monkeypatch):
    recorder = engine.diagnostics

    def fail(*_args):
        raise ValueError("reporting only")

    monkeypatch.setattr(recorder, "observe_work_detail", fail)
    row = MarketEvent(event_id="saved", source="test", kind=EventKind.TRADE)
    assert asyncio.run(
        _timed_to_thread(recorder, "event_persist", engine.database.append_event, row)
    )
    assert len(engine.database.recent_events()) == 1
    assert recorder.loss_counts()["reporting_error"] == 1
    recorder.enabled = False
    assert not asyncio.run(
        _timed_to_thread(recorder, "event_persist", engine.database.append_event, row)
    )
    assert not recorder.runtime_evidence.slow
