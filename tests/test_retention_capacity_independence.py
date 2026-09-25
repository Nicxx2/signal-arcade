"""Missing capacity never grants urgency or blocks independently eligible history forever."""

# ruff: noqa: F811 -- shared pytest fixture

import asyncio
import time
from datetime import UTC, datetime, timedelta
from threading import Event
from types import SimpleNamespace

import pytest
import signal_arcade.database as storage
import signal_arcade.orchestrator as runtime
from signal_arcade.database import MaintenanceReadDeferred
from signal_arcade.models import EventKind, MarketEvent
from test_probe_retention import engine  # noqa: F401


@pytest.fixture
def inline_workers(monkeypatch):
    # Deterministic admission-policy test; real worker deadlines/cancellation have their
    # own suites. CPU-quota scheduling must not turn this into an accidental timeout test.
    async def joined(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(runtime, "_joined_to_thread", joined)
    # Freeze elapsed time for this admission-policy fixture. Otherwise the test container's
    # CPU quota can legitimately exhaust a real 50ms SQL budget and remove no rows.
    # Actual dispatch/setup/SQL timeout and rollback behavior remains tested separately.
    fixed = time.monotonic()
    clock = SimpleNamespace(
        monotonic=lambda: fixed, time=time.time, sleep=time.sleep, thread_time=time.thread_time
    )
    monkeypatch.setattr(runtime, "time", clock)
    monkeypatch.setattr(storage, "time", clock)


@pytest.mark.parametrize("failure", ["before", "after", "both"])
def test_age_cleanup_and_history_time_survive_failed_capacity(
    engine, monkeypatch, inline_workers, failure
):
    now = datetime.now(UTC)
    engine._storage_history_attempted_at = now - timedelta(seconds=61)
    old = now - timedelta(hours=48)
    engine.database.append_events(
        [
            MarketEvent(event_id=key, source="test", kind=kind, mint="m", received_at=at)
            for key, kind, at in (
                ("old", EventKind.TRADE, old),
                ("new", EventKind.TRADE, now),
                ("protected", EventKind.CREATE, old),
            )
        ]
    )
    original_checked = engine._storage_capacity_checked_at
    original_values = dict(engine._storage_snapshot)
    budget_calls = []
    original_budget = engine.database.enforce_storage_budget

    def budget(*args, **kwargs):
        budget_calls.append(True)
        return original_budget(*args, **kwargs)

    async def capacity(_cancelled, _phases, prefix, _deadline):
        if failure == "both" or (prefix == "capacity_before") == (failure == "before"):
            raise MaintenanceReadDeferred
        return engine.database.storage_capacity_stats()

    monkeypatch.setattr(engine, "_storage_capacity_read", capacity)
    monkeypatch.setattr(engine.database, "enforce_storage_budget", budget)
    asyncio.run(engine._storage_maintenance_pass(now, Event()))
    ids = {row[0] for row in engine.database._conn.execute("SELECT event_id FROM market_events")}
    assert ids == {"new", "protected"}
    assert bool(budget_calls) is (failure == "after")
    assert engine._storage_maintenance_last_removed["raw_trades"] == 1
    assert engine._storage_history_checked_at is not None
    assert engine._oldest_retained_trade_at == now.isoformat()
    assert not engine._storage_maintenance_active
    assert engine._storage_idle.is_set()
    assert not engine.database._conn.in_transaction
    if failure != "before":
        assert engine._storage_budget_state == "capacity_unknown"
        assert engine._storage_maintenance_requested
    if failure == "both":
        assert engine._storage_capacity_checked_at == original_checked
        for key in ("live_bytes", "database_bytes", "reclaimable_bytes"):
            assert engine._storage_snapshot.get(key) == original_values.get(key)


@pytest.mark.parametrize("expired_deferral", [False, True])
def test_unknown_capacity_is_not_urgent_even_if_cached_usage_is_high(
    engine, monkeypatch, inline_workers, expired_deferral
):
    now = datetime.now(UTC)
    engine._storage_snapshot["live_bytes"] = engine.storage_max_bytes * 2
    engine._storage_maintenance_deferred_since = now - timedelta(
        seconds=301 if expired_deferral else 1
    )
    calls = []

    async def capacity(*_args):
        raise MaintenanceReadDeferred

    monkeypatch.setattr(engine, "_storage_capacity_read", capacity)
    monkeypatch.setattr(engine, "_storage_market_path_busy", lambda: True)
    monkeypatch.setattr(engine.database, "prune_history", lambda *a, **k: calls.append(k) or {})
    monkeypatch.setattr(
        engine.database, "enforce_storage_budget", lambda *a, **k: pytest.fail("unknown budget")
    )
    asyncio.run(engine._storage_maintenance_pass(now, Event()))
    assert len(calls) == int(expired_deferral)
    if calls:
        assert calls[0]["max_rows_per_category"] == 50
        assert calls[0]["max_duration_seconds"] == 0.05
    assert engine._storage_maintenance_requested


@pytest.mark.parametrize("change", ["revision", "cancel", "upgrade", "error"])
def test_failed_capacity_cannot_bypass_stop_or_error(engine, monkeypatch, inline_workers, change):
    cancelled = Event()

    async def capacity(*_args):
        if change == "revision":
            engine._storage_policy_revision += 1
        elif change == "cancel":
            cancelled.set()
        elif change == "upgrade":
            engine._maintenance_requested = True
        else:
            raise ValueError("unexpected reader error")
        raise MaintenanceReadDeferred

    monkeypatch.setattr(engine, "_storage_capacity_read", capacity)
    monkeypatch.setattr(
        engine.database, "prune_history", lambda *a, **k: pytest.fail("inadmissible cleanup")
    )
    if change == "error":
        with pytest.raises(ValueError, match="unexpected reader error"):
            asyncio.run(engine._storage_maintenance_pass(datetime.now(UTC), cancelled))
    else:
        asyncio.run(engine._storage_maintenance_pass(datetime.now(UTC), cancelled))
    assert not engine._storage_maintenance_active
    assert engine._storage_idle.is_set()


def test_policy_change_after_history_keeps_committed_counts_and_stops_budget(
    engine, monkeypatch, inline_workers
):
    monkeypatch.setattr(engine.database, "maintenance_read", lambda read, **_: read())

    def history(*_args, **kwargs):
        assert not kwargs["stop_requested"]()
        engine._storage_policy_revision += 1
        assert kwargs["stop_requested"]()
        return {"raw_trades": 2}

    monkeypatch.setattr(engine.database, "prune_history", history)
    monkeypatch.setattr(
        engine.database, "enforce_storage_budget", lambda *a, **k: pytest.fail("old policy")
    )
    asyncio.run(engine._storage_maintenance_pass(datetime.now(UTC), Event()))
    assert engine._storage_maintenance_last_removed["raw_trades"] == 2
    assert engine._storage_removed_total["raw_trades"] == 2
    assert engine._storage_maintenance_requested
    assert engine._storage_idle.is_set()
