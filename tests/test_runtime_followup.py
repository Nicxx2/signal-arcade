"""Deterministic regressions for the September 18 natural-traffic review."""

# ruff: noqa: F811 -- shared pytest fixture

import asyncio
from datetime import UTC, datetime
from threading import Event

import pytest
from signal_arcade.diagnostics import DiagnosticsRecorder
from test_probe_retention import engine  # noqa: F401


def test_optional_storage_cannot_evict_training_or_proof(tmp_path):
    recorder = DiagnosticsRecorder(tmp_path)
    recorder.event({"kind": "training", "at": 1})
    for index in range(6):
        recorder.event({"kind": "proof", "index": index})
    recorder.event({"kind": "storage", "at": 2})
    recorder.event({"kind": "storage", "at": 3})
    assert recorder.events[0] == {"kind": "training", "at": 1}
    assert sum(event["kind"] == "proof" for event in recorder.events) == 6
    assert len(recorder.events) == 8
    assert recorder.total_dropped == 1


def test_lock_deferral_does_not_shrink_cleanup_chunk(engine, monkeypatch):
    before = engine._storage_maintenance_chunk_rows

    def lock_contended(*_args, **kwargs):
        if (timing := kwargs.get("timing")) is not None:
            timing["lock_wait_seconds"] = 0.025
            timing["lock_timeouts"] = 1
        return {"work_remaining": 1}

    monkeypatch.setattr(engine.database, "prune_history", lock_contended)
    asyncio.run(engine._storage_maintenance_pass(datetime.now(UTC), Event()))
    assert engine._storage_maintenance_chunk_rows == before
    assert engine._storage_maintenance_requested


def test_stale_browser_queues_one_refresh_during_storage(engine, monkeypatch):
    calls = []

    def snapshot():
        calls.append(True)
        return {}

    monkeypatch.setattr(engine, "snapshot", snapshot)

    async def scenario():
        await engine.snapshot_view()
        engine.invalidate_snapshot_cache()
        engine._storage_maintenance_active = True
        old = engine._ui_snapshot_task
        responses = await asyncio.gather(*(engine.snapshot_view() for _ in range(4)))
        queued = engine._ui_snapshot_task
        assert queued is not old and not queued.done()
        assert len(calls) == 1
        assert len({view["snapshot_generated_at"] for view in responses}) == 1
        engine._storage_maintenance_active = False
        engine._storage_idle.set()
        await asyncio.wait_for(queued, 2)
        assert len(calls) == 2

    asyncio.run(scenario())


@pytest.mark.parametrize("refresh_fails", [False, True])
def test_waiting_refresh_survives_storage_error_and_reads_current_context(
    engine, monkeypatch, refresh_fails
):
    entered, release = Event(), Event()
    context = ["before"]

    def capacity():
        entered.set()
        assert release.wait(5)
        raise RuntimeError("capacity read failed")

    def snapshot():
        if refresh_fails and context[0] == "after":
            raise ValueError("snapshot read failed")
        return {"context": context[0]}

    monkeypatch.setattr(engine, "snapshot", snapshot)
    monkeypatch.setattr(engine.database, "storage_capacity_stats", capacity)

    async def scenario():
        old = await engine.snapshot_view()
        engine.invalidate_snapshot_cache()
        storage = asyncio.create_task(engine._run_storage_maintenance(datetime.now(UTC)))
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            stale = await engine.snapshot_view()
            refresh = engine._ui_snapshot_task
            await asyncio.sleep(0)
            assert not refresh.done()
            assert not engine._event_lock.locked()
            assert stale["snapshot_generated_at"] == old["snapshot_generated_at"]
            # Held-position work or a season change can still own this boundary.
            async with engine._event_lock:
                context[0] = "after"
        finally:
            release.set()
        with pytest.raises(RuntimeError, match="capacity read failed"):
            await storage
        assert engine._storage_idle.is_set()
        if refresh_fails:
            with pytest.raises(ValueError, match="snapshot read failed"):
                await refresh
            assert engine._ui_snapshot_cache[2]["context"] == "before"
            context[0] = "retry"
            assert (await engine.snapshot_view())["context"] == "retry"
        else:
            assert (await refresh)["context"] == "after"
        assert not engine._event_lock.locked()

    asyncio.run(scenario())
