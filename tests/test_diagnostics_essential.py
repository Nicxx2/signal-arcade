"""Reduced observation never bypasses trading/writer guards or invents healthy detail."""

# ruff: noqa: F811 -- shared pytest fixtures
import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from signal_arcade.diagnostics_store import MAX_EVENT_PAYLOAD, DiagnosticsStore, encode, read_events
from test_probe_retention import engine  # noqa: F401
from test_publication_backlog import reports
from test_publication_diagnostics import clock  # noqa: F401


@pytest.mark.parametrize("pressure", ["queue", "lag", "storage", "training"])
def test_essential_capture_is_bounded_read_only_and_keeps_writer_guard(
    engine, clock, monkeypatch, pressure
):
    clock[0] += 76
    monkeypatch.setattr(engine.event_queue, "qsize", lambda: 101 if pressure == "queue" else 1)
    if pressure == "lag":
        engine.last_processing_lag_seconds = 2
    elif pressure == "storage":
        engine._storage_maintenance_active = True
    elif pressure == "training":
        engine.learning._training_active = (engine.risk_mode, None)
    engine._record_pipeline_recent("enqueued")
    engine._record_pipeline_recent("processed", lag_seconds=2, critical=True)
    engine.diagnostics.publication(reports(at=42, proofs=6))
    queries = []
    engine.database._conn.set_trace_callback(queries.append)
    engine.database._reader_conn.set_trace_callback(queries.append)
    monkeypatch.setattr(engine, "_collect_diagnostics", lambda: pytest.fail("rich collection"))

    async def stop(_seconds):
        engine.stop_event.set()

    monkeypatch.setattr(engine, "_wait_for_stop", stop)
    asyncio.run(engine._diagnostics_loop())
    assert queries == []
    assert engine.diagnostics.sequence == 1
    record = json.loads(engine.diagnostics.queue[0])
    assert record["gauges"]["capture_mode"] == "essential"
    assert record["gauges"]["detail_omitted"] is True and record["skills"] == []
    assert record["pipeline"]["enqueued"] == record["pipeline"]["processed"] == 1
    assert record["pipeline"]["critical_lag_max"] == 2
    assert len(record["events"]) == 7
    assert {event["at"] for event in record["events"]} == {42}
    assert not engine.diagnostics.writer.allowed.is_set()
    assert not engine._event_lock.locked()
    assert engine.diagnostics.total_dropped == 0
    encode({key: value for key, value in record.items() if key != "events"})


@pytest.mark.parametrize(
    "block",
    [
        "maintenance",
        "invalid_lag",
        "sell",
        "disabled",
        "stopped",
        "early",
        "full",
        "event_lock",
        "pipeline_lock",
    ],
)
def test_essential_deferral_keeps_cursor_reports_and_authority(engine, clock, monkeypatch, block):
    clock[0] += 74.999 if block == "early" else 100
    monkeypatch.setattr(engine.event_queue, "qsize", lambda: 101)
    if block == "maintenance":
        engine._maintenance_requested = True
    elif block == "invalid_lag":
        engine.last_processing_lag_seconds = float("nan")
    elif block == "sell":
        monkeypatch.setattr(engine, "_has_pending_sell", lambda: True)
    elif block == "disabled":
        engine.diagnostics.enabled = False
    elif block == "stopped":
        engine.stop_event.set()
    elif block == "full":
        engine.diagnostics.queue.extend([b"{}"] * 4)
    engine.diagnostics.publication(reports())
    pending = engine.diagnostics.pending_publication_events
    cursor = engine.diagnostics.cursor.serial

    async def run():
        if block == "event_lock":
            await engine._event_lock.acquire()
        if block == "pipeline_lock":
            engine._pipeline_recent_lock.acquire()
        try:
            await engine._try_essential_diagnostics()
        finally:
            if block == "event_lock":
                engine._event_lock.release()
            if block == "pipeline_lock":
                engine._pipeline_recent_lock.release()

    asyncio.run(run())
    assert engine.diagnostics.sequence == 0
    assert engine.diagnostics.cursor.serial == cursor
    assert engine.diagnostics.pending_publication_events == pending
    assert engine.diagnostics.total_dropped == 0


def test_essential_queue_drains_fifo_with_original_proof_groups_and_honest_gaps(
    engine, clock, monkeypatch, tmp_path
):
    monkeypatch.setattr(engine.event_queue, "qsize", lambda: 101)
    for at in (10, 20):
        engine.diagnostics.publication(reports(at, proofs=6))
    for seconds in (76, 200):
        clock[0] += seconds
        asyncio.run(engine._try_essential_diagnostics())
    records = [json.loads(raw) for raw in engine.diagnostics.queue]
    assert [record["seq"] for record in records] == [0, 1]
    assert "recording_gap" in records[1]["flags"]
    assert engine.diagnostics.pending_publication_events == 0
    store = DiagnosticsStore(tmp_path / "durable")
    try:
        for record in records:
            assert store.append(record)
            assert store.append(record)
    finally:
        store.close()
    events = read_events(tmp_path / "durable", before=2e9)
    assert len(events) == 14
    assert [row["record"]["at"] for row in events] == [10] * 7 + [20] * 7
    assert [row["record"]["publication"][1] for row in events] == list(range(7)) * 2


def test_storage_sample_retains_actual_measurement_time_and_unknown_history(engine):
    measured = datetime.now(UTC) - timedelta(hours=2)
    engine._storage_capacity_checked_at = measured
    engine._storage_snapshot.update(live_bytes=123, reclaimable_bytes=456, wal_bytes=789)
    first = engine._diagnostic_storage_sample()
    assert first["history_at"] is first["oldest_trade_at"] is None
    engine._storage_history_checked_at = measured + timedelta(minutes=1)
    engine._oldest_retained_trade_at = (measured - timedelta(days=2)).isoformat()
    second = engine._diagnostic_storage_sample()
    assert second["capacity_at"] == first["capacity_at"] == measured.isoformat()
    assert second["live_bytes"] == first["live_bytes"] == 123
    assert second["history_at"] == engine._storage_history_checked_at.isoformat()
    assert second["oldest_trade_at"] == engine._oldest_retained_trade_at
    event = next(
        item
        for item in engine._collection_detail_diagnostic_events()
        if item["kind"] == "retention_sample"
    )
    assert event["capacity_at"] == first["capacity_at"]
    encode(event, max_payload=MAX_EVENT_PAYLOAD)
    for _ in range(8):
        engine.diagnostics.event({"kind": "proof"})
    engine.diagnostics.optional_events([event])
    assert all(item["kind"] == "proof" for item in engine.diagnostics.events)
    assert engine.diagnostics.total_dropped == 0


def test_essential_reporting_failure_releases_lock_and_reports_loss(engine, clock, monkeypatch):
    clock[0] += 76
    monkeypatch.setattr(engine.event_queue, "qsize", lambda: 101)

    def fail():
        raise ValueError("fixture reporting failure")

    monkeypatch.setattr(engine, "_diagnostic_context", fail)
    asyncio.run(engine._try_essential_diagnostics())
    assert not engine._event_lock.locked()
    assert engine.diagnostics.loss_counts()["collector_error"] == 1
    assert engine.diagnostics.total_dropped == 1


@pytest.mark.parametrize("arrival", ["maintenance", "sell", "disabled", "full", "stop"])
def test_essential_rechecks_after_acquisition(engine, clock, monkeypatch, arrival):
    clock[0] += 76
    monkeypatch.setattr(engine.event_queue, "qsize", lambda: 101)
    original = engine._event_lock.acquire

    async def acquire():
        if arrival == "maintenance":
            engine._maintenance_requested = True
        elif arrival == "sell":
            monkeypatch.setattr(engine, "_has_pending_sell", lambda: True)
        elif arrival == "disabled":
            engine.diagnostics.enabled = False
        elif arrival == "full":
            engine.diagnostics.queue.extend([b"{}"] * 4)
        else:
            engine.stop_event.set()
        return await original()

    monkeypatch.setattr(engine._event_lock, "acquire", acquire)
    asyncio.run(engine._try_essential_diagnostics())
    assert not engine._event_lock.locked()
    assert engine.diagnostics.sequence == engine.diagnostics.total_dropped == 0
