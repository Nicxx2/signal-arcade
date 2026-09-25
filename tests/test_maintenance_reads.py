"""Maintenance read deadlines must protect market work without inventing fresh data."""

# ruff: noqa: F811 -- shared fixture

import asyncio
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import UTC, datetime, timedelta
from threading import Event
from types import SimpleNamespace

import pytest
import signal_arcade.database as database_module
from signal_arcade.database import Database, MaintenanceReadDeferred
from signal_arcade.models import EventKind, MarketEvent
from test_probe_retention import engine  # noqa: F401


@pytest.mark.parametrize("stopped", [False, True])
def test_budget_capacity_read_yields_to_reader_contention(tmp_path, stopped):
    database = Database(tmp_path / "reader.sqlite3")
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with database._reader_lock:
                future = pool.submit(
                    database.enforce_storage_budget,
                    1,
                    max_duration_seconds=0.02,
                    stop_requested=lambda: stopped,
                )
                try:
                    result = future.result(timeout=0.5)
                except TimeoutError:
                    result = None
            future.result(timeout=2)
        assert result is not None, "capacity read ignored the cleanup deadline"
        assert result["raw_trades"] == result["non_entry_decisions"] == 0
        assert result["work_remaining"] == 1
        assert "live_bytes" not in result, "a deferred read must not fabricate capacity"
    finally:
        database.close()


def test_large_optional_count_can_be_interrupted_inside_its_scan(tmp_path, monkeypatch):
    database = Database(tmp_path / "counts.sqlite3")
    with database._conn:
        database._conn.executemany(
            "INSERT INTO decisions VALUES (?, 'mint', 'pass', '2026-09-21', '{}')",
            [(str(i),) for i in range(2000)],
        )
    clock = [0.0]
    count_started = [False]
    callbacks = []
    connect = sqlite3.connect

    class MeasuredConnection(sqlite3.Connection):
        def set_progress_handler(self, handler, steps):
            def progress():
                if count_started[0]:
                    callbacks.append(True)
                    clock[0] = 1.0
                return handler()

            super().set_progress_handler(progress, steps)

    def reader(*args, **kwargs):
        connection = connect(*args, **kwargs, factory=MeasuredConnection)
        connection.set_trace_callback(
            lambda sql: count_started.__setitem__(0, sql.startswith("SELECT COUNT("))
        )
        return connection

    try:
        monkeypatch.setattr(database_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
        monkeypatch.setattr(database_module.sqlite3, "connect", reader)
        counts = database.bounded_storage_counts()
        assert callbacks, "the count completed without offering cooperative cancellation"
        assert "decisions" not in counts, "an interrupted count must not be published"
        clock[0] = 0.0
        count_started[0] = False
        counts = database.bounded_storage_counts()
        assert counts.get("fills") == 0, "a large first table must not starve small counters"
        assert "decisions" not in counts, "rotation must not publish an interrupted count"
    finally:
        monkeypatch.undo()
        database.close()


def test_optional_counts_do_not_precede_market_pressure_deferral(engine, monkeypatch):
    now = datetime.now(UTC)
    engine._storage_counts_checked_at = now - timedelta(minutes=2)
    monkeypatch.setattr(engine, "_storage_market_path_busy", lambda: True)
    monkeypatch.setattr(
        engine.database,
        "bounded_storage_counts",
        lambda **_: pytest.fail("optional count started before yielding to market pressure"),
    )
    asyncio.run(engine._storage_maintenance_pass(now, Event()))
    assert engine._storage_maintenance_requested
    assert not engine._storage_maintenance_active
    assert engine._storage_idle.is_set()


def test_reader_wait_does_not_restart_deadline(tmp_path, monkeypatch):
    database = Database(tmp_path / "deadline.sqlite3")
    original = database._reader_lock
    clock = [0.0]

    class DelayedLock:
        def acquire(self, *, timeout):
            assert timeout == 0.025
            clock[0] = 0.051
            return original.acquire()

        def release(self):
            original.release()

    try:
        monkeypatch.setattr(database_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
        monkeypatch.setattr(database, "_reader_lock", DelayedLock())
        with pytest.raises(MaintenanceReadDeferred):
            database.maintenance_read(lambda: pytest.fail("SQL started too late"), deadline=0.05)
    finally:
        monkeypatch.undo()
        database.close()


@pytest.mark.parametrize("reason", ["deadline", "cancel", "normal"])
def test_short_read_rechecks_admission_after_connection_setup(tmp_path, monkeypatch, reason):
    database = Database(tmp_path / "setup-deadline.sqlite3")
    connection = database._reader_conn
    clock, stopped, calls = [0.0], [False], []

    class SlowSetup:
        def execute(self, sql):
            result = connection.execute(sql)
            if sql == "PRAGMA busy_timeout=0":
                if reason == "deadline":
                    clock[0] = 0.05
                elif reason == "cancel":
                    stopped[0] = True
            return result

        def set_progress_handler(self, *args):
            return connection.set_progress_handler(*args)

    def read():
        calls.append(True)
        return connection.execute("SELECT 1").fetchone()[0]

    try:
        monkeypatch.setattr(database_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
        monkeypatch.setattr(database, "_reader_conn", SlowSetup())
        if reason == "normal":
            assert database.maintenance_read(read, deadline=0.05) == 1
            assert calls == [True]
        else:
            with pytest.raises(MaintenanceReadDeferred):
                database.maintenance_read(read, deadline=0.05, stop_requested=lambda: stopped[0])
            assert not calls, "short SQL started after setup consumed its admission"
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 250
        assert connection.execute("SELECT 1").fetchone()[0] == 1
    finally:
        monkeypatch.undo()
        database.close()


@pytest.mark.parametrize("reason", ["stop", "sql_error"])
def test_interrupted_reader_restores_connection_and_writer(tmp_path, reason):
    database = Database(tmp_path / "interrupt.sqlite3")
    calls = [0]

    def stopped():
        calls[0] += 1
        return reason == "stop" and calls[0] > 2

    def read():
        query = (
            "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<100000) "
            "SELECT SUM(x) FROM n"
            if reason == "stop"
            else "SELECT * FROM missing_table"
        )
        return database._reader_conn.execute(query).fetchone()

    try:
        expected = MaintenanceReadDeferred if reason == "stop" else sqlite3.OperationalError
        with pytest.raises(expected):
            database.maintenance_read(read, deadline=time.monotonic() + 2, stop_requested=stopped)
        assert database._reader_conn.execute("PRAGMA busy_timeout").fetchone()[0] == 250
        assert database._reader_conn.execute("SELECT 1").fetchone()[0] == 1
        database.set_setting("safe-after-interruption", True)
        assert database.get_setting("safe-after-interruption") is True
    finally:
        database.close()


def test_reader_restores_timeout_and_releases_lock_if_handler_cleanup_fails(tmp_path, monkeypatch):
    database = Database(tmp_path / "restore.sqlite3")
    connection = database._reader_conn

    class CleanupFailure:
        def execute(self, sql):
            return connection.execute(sql)

        def set_progress_handler(self, handler, steps):
            connection.set_progress_handler(handler, steps)
            if handler is None:
                raise sqlite3.OperationalError("injected cleanup failure")

    try:
        monkeypatch.setattr(database, "_reader_conn", CleanupFailure())
        with pytest.raises(sqlite3.OperationalError, match="injected cleanup failure"):
            database.maintenance_read(lambda: 1, deadline=time.monotonic() + 2)
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 250
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(database.health_check).result(timeout=2)
    finally:
        monkeypatch.undo()
        database.close()


def test_budget_reports_committed_deletion_when_final_capacity_is_deferred(tmp_path, monkeypatch):
    database = Database(tmp_path / "committed.sqlite3")
    database.append_event(
        MarketEvent(
            event_id="retire",
            source="test",
            kind=EventKind.TRADE,
            mint="mint",
            received_at=datetime.now(UTC),
        )
    )
    original = database._retention_transaction
    clock = [0.0]

    def completed(*args, **kwargs):
        count = original(*args, **kwargs)
        clock[0] = 1.0
        return count

    try:
        monkeypatch.setattr(
            database_module,
            "time",
            SimpleNamespace(
                monotonic=lambda: clock[0],
                sleep=lambda _: None,
            ),
        )
        monkeypatch.setattr(database, "_retention_transaction", completed)
        result = database.enforce_storage_budget(
            1,
            preserve_recent_events=0,
            max_rows_per_chunk=1,
            max_duration_seconds=0.05,
        )
        assert result["raw_trades"] == result["capacity_deferred"] == result["work_remaining"] == 1
        assert not database.recent_events()
    finally:
        monkeypatch.undo()
        database.close()


def test_unknown_capacity_preserves_old_measurement_and_recovers(engine, monkeypatch):
    before = dict(engine._storage_snapshot)
    stamp = engine._storage_capacity_checked_at

    def deferred(*_args, **_kwargs):
        raise MaintenanceReadDeferred("busy")

    monkeypatch.setattr(engine.database, "maintenance_read", deferred)
    asyncio.run(engine._storage_maintenance_pass(datetime.now(UTC), Event()))
    assert engine._storage_budget_state == "capacity_unknown"
    assert engine._storage_snapshot == before
    assert engine._storage_capacity_checked_at == stamp
    assert engine._storage_maintenance_requested and engine._storage_idle.is_set()
    assert engine._storage_maintenance_deferred_reason == "storage_reader_busy"
    # Unknown capacity cannot grant urgency, but independently eligible history gets
    # its ordinary bounded turn and advances the fair category rotation.
    assert engine._storage_history_category_offset == 1
    # Own admission for this reporting/recovery assertion. The real reader deadline,
    # lock restoration and interruption behavior are exercised separately above.
    monkeypatch.setattr(engine.database, "maintenance_read", lambda function, **_: function())
    asyncio.run(engine._storage_maintenance_pass(datetime.now(UTC), Event()))
    assert engine._storage_budget_state == "within_budget"
    assert engine._storage_maintenance_deferred_reason is None
    assert engine._storage_history_category_offset == 2


def test_optional_statistics_follow_cleanup_and_keep_failed_oldest_age(engine, monkeypatch):
    now = datetime.now(UTC)
    old = now - timedelta(minutes=2)
    engine._storage_counts_checked_at = engine._storage_history_attempted_at = old
    engine._storage_history_checked_at = old
    engine._oldest_retained_trade_at = old.isoformat()
    stamps = dict(engine._storage_count_timestamps)
    calls = []

    def read(function, **kwargs):
        if function == engine.database.oldest_retained_trade:
            raise MaintenanceReadDeferred("busy")
        # This test owns admission to exercise ordering and the stale-age branch.
        # Real reader/dispatch deadlines are covered by the contention tests above.
        return function()

    monkeypatch.setattr(engine.database, "maintenance_read", read)
    monkeypatch.setattr(
        engine.database, "prune_history", lambda *_a, **_k: calls.append("history") or {}
    )
    monkeypatch.setattr(
        engine.database, "enforce_storage_budget", lambda *_a, **_k: calls.append("budget") or {}
    )
    monkeypatch.setattr(
        engine.database,
        "bounded_storage_counts",
        lambda **_k: calls.append("counts") or {"fills": 0},
    )
    asyncio.run(engine._storage_maintenance_pass(now, Event()))
    assert calls == ["history", "budget", "counts"]
    assert engine._storage_count_timestamps["fills"] != stamps["fills"]
    assert engine._storage_count_timestamps["market_events"] == stamps["market_events"]
    assert engine._storage_history_checked_at == old
    assert engine._oldest_retained_trade_at == old.isoformat()
    phases = engine._storage_maintenance_last_phases
    assert {"counts_seconds", "oldest_trade_seconds"} <= set(phases)
