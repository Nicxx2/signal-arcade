"""New timings remain bounded observations and keep worker ownership."""

# ruff: noqa: F811 -- shared pytest fixture

import asyncio
import time
from threading import Event

import pytest
from signal_arcade.diagnostics import DiagnosticsRecorder
from signal_arcade.diagnostics_store import MAX_EVENT_PAYLOAD, decode, encode
from signal_arcade.runtime_evidence import SLOW_FIELDS, RuntimeEvidence
from test_probe_retention import engine  # noqa: F401


@pytest.mark.parametrize("cancel", [False, True])
def test_capacity_read_keeps_original_deadline_and_joins_before_reporting(
    engine, monkeypatch, cancel
):
    entered, release = Event(), Event()
    deadlines = []

    def read(function, *, deadline, stop_requested, timing):
        deadlines.append(deadline)
        entered.set()
        assert release.wait(3)
        return function()

    monkeypatch.setattr(engine.database, "maintenance_read", read)
    monkeypatch.setattr(engine.database, "storage_capacity_stats", lambda: {"live_bytes": 42})

    async def run():
        phases = {}
        deadline = time.monotonic() + 0.05
        task = asyncio.create_task(
            engine._storage_capacity_read(Event(), phases, "capacity", deadline)
        )
        assert await asyncio.to_thread(entered.wait, 2)
        try:
            if cancel:
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
                assert not task.done() and not phases
        finally:
            release.set()
        if cancel:
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            assert await task == {"live_bytes": 42}
        assert deadlines == [deadline]
        assert set(phases) == {
            "capacity_" + x for x in ("dispatch", "worker", "cpu", "read", "resume")
        }
        assert all(value >= 0 for value in phases.values())

    asyncio.run(run())


def test_new_slow_phase_payloads_stay_inside_existing_caps(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    evidence = RuntimeEvidence()
    for lane in ("market", "storage", "capacity"):
        phases = {name: 123.456789 + i for i, name in enumerate(SLOW_FIELDS[lane])}
        evidence.observe_slow(
            lane, started=1, finished=500, at=1000, phases=phases, outcome="complete"
        )
    for lane in ("market", "storage", "capacity"):
        event = evidence.slow_event(lane, "fixture")
        assert event is not None
        assert recorder._detached_event(event) == event
        assert decode(encode(event, max_payload=MAX_EVENT_PAYLOAD)) == event


def test_initial_capacity_deferral_survives_saved_slow_sample():
    evidence = RuntimeEvidence()
    phases = {
        "stage": 0,
        "setup": 0.05,
        "setup_deferred": 1.0,
        "restore": 0.001,
    }
    evidence.observe_slow(
        "capacity", started=1, finished=1.06, at=1000, phases=phases, outcome="yielded"
    )
    event = evidence.slow_event("capacity", "fixture")
    assert event is not None
    # This pass did not reach its final read. Losing the initial-read markers would
    # misleadingly leave only the umbrella storage_reader_busy status for diagnosis.
    saved = decode(encode(event, max_payload=MAX_EVENT_PAYLOAD))
    assert saved["phases"]["stage"] == 0
    assert saved["phases"]["setup_deferred"] == 1
    assert saved["phases"]["setup"] == 0.05
