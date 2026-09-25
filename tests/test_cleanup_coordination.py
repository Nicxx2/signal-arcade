"""Cleanup fairness, absolute budgets and reserve-request ownership under contention."""

# ruff: noqa: F811 -- shared pytest fixture

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from types import SimpleNamespace

import pytest
import signal_arcade.database as database_module
from signal_arcade.database import Database
from test_learning import make_decision, make_state, policy_episode_for
from test_probe_retention import engine  # noqa: F401
from test_reserve_contract_integration import public_config_route


def test_real_lock_timeout_is_not_sql_work_and_preserves_deadline(tmp_path):
    database = Database(tmp_path / "busy.sqlite3")
    timing = {}
    try:
        with ThreadPoolExecutor(max_workers=1) as pool, database._lock:
            result = pool.submit(
                database.prune_history,
                datetime.now(UTC),
                max_duration_seconds=0.05,
                timing=timing,
            ).result(timeout=3)
        assert result["work_remaining"] == 1
        assert timing["lock_timeouts"] == 1
        assert timing["lock_wait_seconds"] > 0
        assert timing["query_seconds"] == timing["completed_queries"] == 0
        assert timing["query_budget_exhausted"] == 0
        database.set_setting("writer-still-usable", True)
        assert database.get_setting("writer-still-usable") is True
    finally:
        database.close()


def test_lock_acquisition_does_not_restart_the_absolute_cleanup_budget(tmp_path, monkeypatch):
    database = Database(tmp_path / "deadline.sqlite3")
    original_lock = database._lock
    clock = [0.0]
    queries = []
    timing = {}

    class DelayedLock:
        def acquire(self, *, timeout):
            assert timeout == 0.025
            clock[0] = 0.051
            return original_lock.acquire()

        def release(self):
            original_lock.release()

    try:
        monkeypatch.setattr(database_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
        monkeypatch.setattr(database, "_lock", DelayedLock())
        database._conn.set_trace_callback(queries.append)
        result = database.prune_history(datetime.now(UTC), max_duration_seconds=0.05, timing=timing)
        assert result["work_remaining"] == 1
        assert timing["worker_seconds"] == 0.051
        assert timing["query_seconds"] == timing["completed_queries"] == 0
        assert not queries, "deadline expired while acquiring the lock; no SQL may start"
    finally:
        monkeypatch.undo()
        database.close()


@pytest.mark.parametrize(
    ("timing", "remaining", "expected"),
    [
        ({"query_seconds": 0.001, "worker_seconds": 10, "completed_queries": 3}, False, 25),
        (
            {"query_seconds": 0.001, "lock_wait_seconds": 0.049, "query_budget_exhausted": 1},
            True,
            20,
        ),
        (
            {"query_seconds": 0.04, "query_budget_seconds": 0.05, "query_budget_exhausted": 1},
            True,
            10,
        ),
        ({"query_seconds": 0.051, "completed_queries": 3}, False, 10),
        ({"lock_timeouts": 1}, True, 20),
        ({}, True, 20),
    ],
)
def test_adaptation_uses_query_cost_not_wait_or_missing_measurement(
    engine, monkeypatch, timing, remaining, expected
):
    # This test supplies SQL timings to the controller; real reader admission is covered
    # separately. Executor descheduling must not decide whether this fixture reaches history.
    monkeypatch.setattr(engine.database, "maintenance_read", lambda read, **_: read())
    engine._storage_history_chunk_rows["raw_trades"] = 20

    def prune(*_args, **kwargs):
        kwargs["timing"].update({f"raw_trades_{key}": value for key, value in timing.items()})
        return {"raw_trades": 20, "work_remaining": int(remaining)}

    monkeypatch.setattr(engine.database, "prune_history", prune)
    asyncio.run(engine._storage_maintenance_pass(datetime.now(UTC), Event()))
    assert engine._storage_history_chunk_rows["raw_trades"] == expected
    assert engine._storage_history_chunk_rows["equity_points"] == 50
    assert engine._storage_maintenance_chunk_rows == 50
    assert engine._storage_maintenance_last_phases["history_dispatch_resume_seconds"] >= 0


@pytest.mark.parametrize("case", ["normal", "urgent", "stale", "unknown", "limit", "upgrade"])
def test_rpc_deferral_is_short_and_never_starves_urgent_or_unknown_storage(
    engine, monkeypatch, case
):
    # This fixture checks RPC admission policy, not executor scheduling. Real bounded
    # reader contention/deadlines are exercised by test_maintenance_reads separately.
    monkeypatch.setattr(engine.database, "maintenance_read", lambda read, **_: read())
    now = datetime.now(UTC)
    engine._learning_reserve_in_flight = 1
    engine._storage_maintenance_last_completed_at = now
    engine._storage_snapshot["live_bytes"] = 1
    if case == "urgent":
        engine._storage_snapshot["live_bytes"] = engine.storage_max_bytes
    elif case == "stale":
        engine._storage_maintenance_last_completed_at = now - timedelta(seconds=61)
    elif case == "unknown":
        engine._storage_maintenance_last_completed_at = None
    elif case == "limit":
        engine._storage_rpc_deferred_at = time.monotonic() - 8
    elif case == "upgrade":
        engine._maintenance_requested = True
    calls = []

    def prune(*_args, **_kwargs):
        calls.append(True)
        return {}

    monkeypatch.setattr(engine.database, "prune_history", prune)
    asyncio.run(engine._storage_maintenance_pass(now, Event()))
    # Upgrade preparation now stops before capacity/catalog reads as well as deletes.
    assert bool(calls) is (case not in {"normal", "upgrade"})
    assert not engine._storage_maintenance_active
    if case == "normal":
        assert engine._storage_maintenance_requested
        assert engine._storage_maintenance_deferred_reason == "protecting_inflight_learning_rpc"
        engine._learning_reserve_in_flight = 0
        asyncio.run(engine._storage_maintenance_pass(now, Event()))
        assert calls == [True]


def test_admitted_rpc_finishes_both_lanes_before_nonurgent_cleanup(engine, monkeypatch):
    state, response, _, now = public_config_route("pump_curve")
    state.last_reserve_at = now - timedelta(minutes=5)
    engine.features.tokens[state.mint] = state
    decision = make_decision(now - timedelta(seconds=301), state.mint)
    decision.configuration_fingerprint = engine.learning.configuration_fingerprint()
    assert engine.learning.register(
        decision, make_state(state.mint), live=True, evaluation_actionable=True
    )
    engine.demo_mode = False
    engine.settings.learning_reserve_refresh_enabled = True
    engine._storage_maintenance_last_completed_at = datetime.now(UTC)
    engine._storage_snapshot["live_bytes"] = 1
    monkeypatch.setattr(engine, "_rollover_market_data_healthy", lambda _: True)
    monkeypatch.setattr(
        engine.database,
        "storage_capacity_stats",
        lambda: pytest.fail("nonurgent cleanup started during admitted RPC"),
    )

    async def fetch(*_args, **_kwargs):
        assert engine._learning_reserve_in_flight == 1
        await engine._storage_maintenance_pass(datetime.now(UTC), Event())
        assert engine._storage_maintenance_requested
        return response

    monkeypatch.setattr(engine.http, "solana_multiple_accounts", fetch)
    asyncio.run(engine._learning_reserve_tick())
    assert engine._learning_reserve_in_flight == 0
    assert engine._learning_refresh_status["accepted_routes"] == 1
    assert sum(engine._learning_refresh_status["discarded_by_reason"].values()) == 0
    for item in (
        engine.learning.observations[state.mint],
        policy_episode_for(engine.learning, state.mint),
    ):
        assert item.checkpoints["300"].net_return is not None


@pytest.mark.parametrize("failure", ["cancel", "error", "unavailable"])
def test_rpc_releases_cleanup_reservation_on_every_exit(engine, monkeypatch, failure):
    state, response, *_ = public_config_route("pump_curve")
    engine.features.tokens[state.mint] = state
    monkeypatch.setattr(engine, "_learning_reserve_blocked_reason", lambda: None)
    monkeypatch.setattr(engine.learning, "due_checkpoint_mints", lambda *a, **k: [state.mint])

    async def fetch(*_args, **_kwargs):
        assert engine._learning_reserve_in_flight == 1
        if failure == "cancel":
            raise asyncio.CancelledError
        if failure == "error":
            raise ValueError("provider failure")
        return None

    monkeypatch.setattr(engine.http, "solana_multiple_accounts", fetch)
    if failure == "unavailable":
        asyncio.run(engine._learning_reserve_tick())
    else:
        with pytest.raises(asyncio.CancelledError if failure == "cancel" else ValueError):
            asyncio.run(engine._learning_reserve_tick())
    assert engine._learning_reserve_in_flight == 0
    assert not engine._event_lock.locked()


def test_maintenance_source_counts_remain_a_subset_of_guard_deferrals(engine):
    engine._storage_maintenance_active = True
    engine._learning_refresh_deferred("maintenance")
    engine._record_learning_maintenance_guard("discarded")
    engine._maintenance_requested = True
    engine._learning_refresh_deferred("maintenance")
    assert engine._learning_maintenance_guards["storage"] == {"deferred": 1, "discarded": 1}
    assert engine._learning_maintenance_guards["upgrade"] == {"deferred": 1, "discarded": 0}
    assert engine._learning_refresh_status["deferred"]["maintenance"] == 2
