"""Preparation/result timing is bounded and cannot change worker ownership or decisions."""

# ruff: noqa: F811 -- shared fixture

import asyncio
from threading import Event

import pytest
from signal_arcade.diagnostics import PHASES
from signal_arcade.diagnostics_store import MAX_EVENT_PAYLOAD, encode
from signal_arcade.orchestrator import _timed_to_thread
from test_probe_retention import engine  # noqa: F401


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("phase", ["event_candidate", "enrichment"])
def test_worker_timing_keeps_original_result_and_optional_dimensions(engine, enabled, phase):
    engine.diagnostics.enabled = enabled
    marker = object()
    lane = "market" if phase == "event_candidate" else "enrichment"

    async def run():
        operation = engine.diagnostics.begin_operation(lane)
        try:
            assert await _timed_to_thread(engine.diagnostics, phase, lambda: marker) is marker
        finally:
            engine.diagnostics.finish_operation(operation, "complete")

    asyncio.run(run())
    if not enabled:
        assert not engine.diagnostics.runtime_evidence.slow
        return
    sample = engine.diagnostics.runtime_evidence.slow[lane]
    assert set(sample["phases"]) == {
        phase + suffix for suffix in ("_cpu", "_wait", "_dispatch", "_resume", "_worker")
    }
    assert not set(sample["phases"]) & PHASES, "optional detail enlarged interval payloads"
    engine._record_collection_detail_diagnostics()
    event = next(e for e in engine.diagnostics.events if e.get("lane") == lane)
    encode(event, max_payload=MAX_EVENT_PAYLOAD)


@pytest.mark.parametrize("ending", ["success", "error", "cancel"])
def test_enrichment_boundary_keeps_worker_owned_and_records_after_join(engine, ending):
    entered, release = Event(), Event()
    marker = object()

    def work():
        entered.set()
        assert release.wait(3)
        if ending == "error":
            raise ValueError("fixture error")
        return marker

    async def run():
        task = asyncio.create_task(engine._enrichment_boundary("enrichment_prepare", work))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            if ending == "cancel":
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
            assert engine._event_lock.locked() and not task.done()
            assert "enrichment" not in engine.diagnostics.runtime_evidence.slow
        finally:
            release.set()
        if ending == "success":
            assert await task is marker
        else:
            with pytest.raises(ValueError if ending == "error" else asyncio.CancelledError):
                await task
        assert not engine._event_lock.locked()
        sample = engine.diagnostics.runtime_evidence.slow["enrichment"]
        assert (
            sample["outcome"]
            == {"success": "complete", "error": "error", "cancel": "cancelled"}[ending]
        )
        assert "enrichment_prepare" in sample["phases"]
        assert "enrichment_lock_wait" in sample["phases"]

    asyncio.run(run())


@pytest.mark.parametrize("reporter", ["observe_slow_work", "observe_duration"])
def test_failed_optional_reporting_does_not_replace_boundary_result(engine, monkeypatch, reporter):
    marker = object()

    def fail(*_args):
        raise ValueError("reporting unavailable")

    monkeypatch.setattr(engine.diagnostics, reporter, fail)
    result = asyncio.run(engine._enrichment_boundary("enrichment_prepare", lambda: marker))
    assert result is marker
    assert engine.diagnostics.loss_counts()["reporting_error"] > 0
    assert not engine._event_lock.locked()
