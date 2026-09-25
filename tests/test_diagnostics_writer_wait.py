"""Writer wait visibility must not change admission or protected publication behavior."""

# ruff: noqa: F811 -- shared fixture

import asyncio
import itertools
import random
import time

import pytest
from signal_arcade.diagnostics import DiagnosticsRecorder
from signal_arcade.diagnostics_optional import optional_key
from signal_arcade.diagnostics_store import MAX_EVENT_PAYLOAD, encode, read_page
from signal_arcade.diagnostics_worker import WRITER_WAIT_REASONS, DiagnosticsWriter
from test_diagnostics import interval
from test_probe_retention import engine  # noqa: F401


@pytest.mark.parametrize("flags", list(itertools.product((False, True), repeat=4)))
def test_explanation_matches_unchanged_writer_guard(engine, flags):
    market, storage, maintenance, training = flags
    if market:
        engine._storage_market_yield_requested.set()
    else:
        engine._storage_market_yield_requested.clear()
    engine._storage_maintenance_active = storage
    engine._maintenance_requested = maintenance
    engine.learning._training_active = "balanced" if training else None
    expected = next(
        (
            key
            for key, flag in zip(
                ("market_yield", "storage", "maintenance", "training"), flags, strict=True
            )
            if flag
        ),
        None,
    )
    assert engine._diagnostics_writer_blocked_reason() == expected
    assert engine.diagnostics.can_write() == (not any(flags))
    assert engine._storage_market_yield_requested.is_set() == market


def test_reason_transitions_are_disjoint_detached_and_bounded(tmp_path, monkeypatch):
    clock = [10.0]
    monkeypatch.setattr("signal_arcade.diagnostics_worker.time.monotonic", lambda: clock[0])
    writer = DiagnosticsWriter(tmp_path)
    writer._observe_wait("market_yield")
    clock[0] = 13
    writer._observe_wait("market_yield")
    writer._observe_wait("training")
    clock[0] = 15
    current = writer.wait_status()
    assert current["reason"] == "training" and current["reason_age_seconds"] == 2
    assert current["seconds_since_boot"]["market_yield"] == 3
    assert current["seconds_since_boot"]["training"] == 2
    assert sum(current["episodes_since_boot"].values()) == 2
    current["episodes_since_boot"]["training"] = 999
    writer._observe_wait(None)
    clock[0] = 100
    assert writer.wait_status()["seconds_since_boot"] == current["seconds_since_boot"]
    assert writer.wait_status()["episodes_since_boot"]["training"] == 1
    assert writer.wait_status()["reason"] is None


@pytest.mark.parametrize("reason", ["market_yield", None, "unbounded-private-id", "raises"])
def test_writer_waits_for_authority_even_when_reporting_fails(tmp_path, reason):
    permitted = False

    def explain():
        if reason == "raises":
            raise ValueError("private fixture")
        return reason

    async def wait_until(predicate):
        deadline = time.monotonic() + 3
        for _ in range(300):
            if time.monotonic() >= deadline or predicate():
                break
            await asyncio.sleep(0.01)
        assert predicate()

    async def scenario():
        nonlocal permitted
        recorder = DiagnosticsRecorder(
            tmp_path, can_write=lambda: permitted, writer_blocked_reason=explain
        )
        await recorder.start()
        try:
            values = interval()
            recorder.collect(
                pipeline=values["pipeline"], context=values["context"], gauges={}, skills=[]
            )
            await recorder.flush_one(allowed=True)
            await wait_until(lambda: recorder.status()["writer_wait"]["reason"] is not None)
            expected = "market_yield" if reason == "market_yield" else "guard"
            assert recorder.status()["writer_wait"]["reason"] == expected
            assert read_page(tmp_path, tier=0) == []
            event = recorder.writer_wait_event()
            assert event["lane"] == "writer" and optional_key(event) is not None
            encode(event, max_payload=MAX_EVENT_PAYLOAD)
            permitted = True
            await wait_until(
                lambda: recorder.status().get("ranges", {}).get("minute", {}).get("rows") == 1
            )
            assert recorder.status()["writer_wait"]["reason"] is None
            assert recorder.total_dropped == 0
            assert len(read_page(tmp_path, tier=0)) == 1
        finally:
            await recorder.stop()
        assert not recorder.writer.thread.is_alive()

    asyncio.run(scenario())


def test_report_fits_existing_limits_at_saturation(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    recorder.writer = DiagnosticsWriter(tmp_path)
    rng = random.Random(81)  # noqa: S311 -- deterministic high-entropy fixture
    for reason in WRITER_WAIT_REASONS:
        recorder.writer._wait_counts[reason] = rng.randrange(2**52, 2**53)
        recorder.writer._wait_seconds[reason] = rng.random() * 1e12
    event = recorder.writer_wait_event()
    encode(event, max_payload=MAX_EVENT_PAYLOAD)
    assert optional_key(event) == ("collector_work", "writer", ())
    assert optional_key({**event, "lane": "anything-else"}) is None


def test_admission_denial_does_not_call_explanation(tmp_path):
    writer = DiagnosticsWriter(tmp_path, blocked_reason=lambda: pytest.fail("no guard check"))
    writer._record_blocked_wait(False)
    assert writer.wait_status()["reason"] == "admission"


def test_status_reporting_failure_is_honest_and_does_not_break_health(tmp_path, monkeypatch):
    recorder = DiagnosticsRecorder(tmp_path)
    recorder.writer = DiagnosticsWriter(tmp_path)

    def fail():
        raise ValueError("isolated reporter failure")

    monkeypatch.setattr(recorder.writer, "wait_status", fail)
    assert recorder.status()["writer_wait"] is None
    assert recorder.writer_wait_event() is None
    assert recorder.loss_reasons["reporting_error"] == 2
