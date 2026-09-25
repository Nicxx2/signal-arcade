"""Optional timing distinguishes admission/setup/SQL without changing read semantics."""

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from signal_arcade.database import Database, MaintenanceReadDeferred


@pytest.mark.parametrize(
    "outcome", ["success", "expired", "cancelled", "busy", "interrupt", "error"]
)
def test_maintenance_attribution_and_restoration(tmp_path, outcome):
    database = Database(tmp_path / "phases.sqlite3")
    timing = {}

    def read():
        if outcome in {"busy", "interrupt", "error"}:
            error = sqlite3.OperationalError("injected SQL outcome")
            error.sqlite_errorcode = {
                "busy": sqlite3.SQLITE_BUSY,
                "interrupt": sqlite3.SQLITE_INTERRUPT,
                "error": sqlite3.SQLITE_ERROR,
            }[outcome]
            raise error
        return database._reader_conn.execute("SELECT 42").fetchone()[0]

    try:
        arguments = {
            "deadline": time.monotonic() + (-1 if outcome == "expired" else 10),
            "stop_requested": lambda: outcome == "cancelled",
            "timing": timing,
        }
        if outcome == "success":
            assert database.maintenance_read(read, **arguments) == 42
        else:
            expected = sqlite3.OperationalError if outcome == "error" else MaintenanceReadDeferred
            with pytest.raises(expected):
                database.maintenance_read(read, **arguments)
        if outcome in {"expired", "cancelled"}:
            assert timing == {"admission_deferred": 1.0}
        else:
            assert {"lock_wait", "setup", "query", "restore"} <= timing.keys()
            assert timing.get("sql_busy", 0) == (outcome == "busy")
            assert timing.get("sql_interrupted", 0) == (outcome == "interrupt")
        assert all(value >= 0 for value in timing.values())
        assert database._reader_conn.execute("PRAGMA busy_timeout").fetchone()[0] == 250
        assert database._reader_conn.execute("SELECT 1").fetchone()[0] == 1
    finally:
        database.close()


def test_actual_reader_lock_contention_is_distinct_from_expired_admission(tmp_path):
    database = Database(tmp_path / "lock.sqlite3")
    timing = {}
    try:
        with ThreadPoolExecutor(max_workers=1) as pool, database._reader_lock:
            task = pool.submit(
                database.maintenance_read,
                lambda: pytest.fail("contended read was admitted"),
                deadline=time.monotonic() + 10,
                timing=timing,
            )
            with pytest.raises(MaintenanceReadDeferred):
                task.result(timeout=2)
        assert set(timing) == {"lock_wait", "lock_deferred"}
        assert timing["lock_deferred"] == 1
    finally:
        database.close()
