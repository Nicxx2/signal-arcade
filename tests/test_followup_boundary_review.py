"""Independent edge review of the v1.10.11 local follow-up."""

# ruff: noqa: F811 -- shared pytest fixture

import asyncio
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from types import SimpleNamespace

import pytest
import signal_arcade.orchestrator as orchestration
from signal_arcade.database import Database
from signal_arcade.diagnostics import DiagnosticsRecorder
from test_probe_retention import engine  # noqa: F401
from test_reserve_contract_integration import public_config_route


def test_writer_rejection_during_collection_is_not_swallowed(tmp_path):
    class LateReject:
        reads = 0

        @property
        def rejected(self):
            self.reads += 1
            # Simulate the writer completing a rejected append just after the
            # recorder's first read. The next collection must still flag that loss.
            return 0 if self.reads == 1 else 1

    recorder = DiagnosticsRecorder(tmp_path)
    recorder.writer = LateReject()
    recorder.collect(pipeline={}, context={}, gauges={}, skills=[])
    recorder.collect(pipeline={}, context={}, gauges={}, skills=[])
    first, second = (json.loads(raw) for raw in recorder.queue)
    assert "recording_gap" in second["flags"]
    assert first["gauges"]["diagnostics_dropped"] == 0
    assert second["gauges"]["diagnostics_dropped"] == 1


@pytest.mark.parametrize(
    ("capacity_age", "deferred_for", "byte_offset", "defer"),
    [
        (0, 7.999999, 0, True),
        (60, 0, 0, True),
        (60.000001, 0, 0, False),
        (-0.000001, 0, 0, False),
        (0, 8, 0, False),
        (0, 0, 1, False),
    ],
)
def test_storage_rpc_deferral_exact_time_and_capacity_edges(
    engine, monkeypatch, capacity_age, deferred_for, byte_offset, defer
):
    now = datetime.now(UTC)
    engine._learning_reserve_in_flight = 1
    engine._storage_maintenance_last_completed_at = now - timedelta(seconds=capacity_age)
    engine._storage_snapshot["live_bytes"] = int(engine.storage_max_bytes * 0.90) + byte_offset
    engine._storage_rpc_deferred_at = 1000 - deferred_for
    # Maintenance now carries its absolute deadline across the worker boundary. Both sides
    # must share this fixture's clock; real deadline/lock behaviour is tested separately.
    clock = SimpleNamespace(
        monotonic=lambda: 1000.0,
        time=time.time,
        sleep=time.sleep,
        thread_time=time.thread_time,
    )
    monkeypatch.setattr(orchestration, "time", clock)
    monkeypatch.setattr("signal_arcade.database.time", clock)
    calls = []

    def prune(*_args, **_kwargs):
        calls.append(True)
        return {}

    monkeypatch.setattr(engine.database, "prune_history", prune)
    asyncio.run(engine._storage_maintenance_pass(now, Event()))
    assert bool(calls) is not defer
    assert not engine._storage_maintenance_active
    assert engine._storage_idle.is_set()


def test_one_cancelled_request_does_not_release_another_requests_reservation(engine, monkeypatch):
    state, *_ = public_config_route("pump_curve")
    engine.features.tokens[state.mint] = state
    engine._storage_maintenance_last_completed_at = datetime.now(UTC)
    engine._storage_snapshot["live_bytes"] = 1
    monkeypatch.setattr(engine, "_learning_reserve_blocked_reason", lambda: None)
    monkeypatch.setattr(engine.learning, "due_checkpoint_mints", lambda *a, **k: [state.mint])
    monkeypatch.setattr(
        engine.database,
        "storage_capacity_stats",
        lambda: pytest.fail("the second request still owns its reservation"),
    )

    async def scenario():
        both_entered, finish = asyncio.Event(), asyncio.Event()
        entered = 0

        async def fetch(*_args, **_kwargs):
            nonlocal entered
            entered += 1
            if entered == 2:
                both_entered.set()
            await finish.wait()
            return None

        monkeypatch.setattr(engine.http, "solana_multiple_accounts", fetch)
        requests = [asyncio.create_task(engine._learning_reserve_tick()) for _ in range(2)]
        try:
            await asyncio.wait_for(both_entered.wait(), 3)
            assert engine._learning_reserve_in_flight == 2
            requests[0].cancel()
            with pytest.raises(asyncio.CancelledError):
                await requests[0]
            assert engine._learning_reserve_in_flight == 1
            await engine._storage_maintenance_pass(datetime.now(UTC), Event())
            assert engine._storage_maintenance_requested
        finally:
            finish.set()
            await asyncio.gather(*requests, return_exceptions=True)
        assert engine._learning_reserve_in_flight == 0
        assert not engine._event_lock.locked()

    asyncio.run(scenario())


def test_shutdown_of_storage_waiter_preserves_cache_and_allows_later_refresh(engine, monkeypatch):
    calls = []

    def snapshot():
        calls.append(True)
        return {"generation": len(calls)}

    monkeypatch.setattr(engine, "snapshot", snapshot)

    async def scenario():
        first = await engine.snapshot_view()
        engine.invalidate_snapshot_cache()
        engine._storage_maintenance_active = True
        assert (await engine.snapshot_view())["generation"] == first["generation"]
        waiter = engine._ui_snapshot_task
        await asyncio.sleep(0)
        for _ in range(3):
            waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        await asyncio.sleep(0)
        assert waiter not in engine.tasks
        assert not engine._event_lock.locked()
        assert len(calls) == 1
        engine._storage_maintenance_active = False
        engine._storage_idle.set()
        assert (await engine.snapshot_view())["generation"] == 2
        assert engine._ui_snapshot_task is not waiter

    asyncio.run(scenario())


def test_failed_sql_releases_writer_and_removes_cleanup_progress_handler(tmp_path):
    database = Database(tmp_path / "failed-cleanup.sqlite3")
    stop = Event()
    timing = {}

    def authorize(action, *_args):
        return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_DELETE else sqlite3.SQLITE_OK

    def another_writer_can_lock():
        acquired = database._lock.acquire(timeout=1)
        if acquired:
            database._lock.release()
        return acquired

    try:
        database._conn.set_authorizer(authorize)
        with pytest.raises(sqlite3.DatabaseError):
            database.prune_history(
                datetime.now(UTC),
                max_duration_seconds=0.05,
                stop_requested=stop.is_set,
                timing=timing,
            )
        database._conn.set_authorizer(None)
        stop.set()
        # More than 500 VM instructions: a leaked cleanup callback would interrupt this.
        assert (
            database._conn.execute(
                "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<1000) "
                "SELECT SUM(x) FROM n"
            ).fetchone()[0]
            == 500500
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(another_writer_can_lock).result(timeout=3)
        assert timing["completed_queries"] == 0
        assert timing["query_seconds"] >= 0
        database.set_setting("after-failed-cleanup", True)
        assert database.get_setting("after-failed-cleanup") is True
    finally:
        database._conn.set_authorizer(None)
        database.close()
