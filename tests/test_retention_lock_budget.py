"""SQLite contention must yield without changing subsequent trading transactions."""

import sqlite3
import time
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
import signal_arcade.database as database_module
from signal_arcade.database import Database


def test_external_writer_does_not_outwait_cleanup_budget(tmp_path):
    database = Database(tmp_path / "writer.sqlite3")
    other = sqlite3.connect(database.path)
    try:
        database.set_setting("protected", 1)
        database._conn.execute("PRAGMA busy_timeout=1200")
        other.execute("BEGIN IMMEDIATE")
        timing = {}
        started = time.monotonic()
        result = database.prune_history(
            datetime.now(UTC), max_duration_seconds=0.025, timing=timing
        )
        assert time.monotonic() - started < 0.6, "waited for SQLite busy timeout"
        assert result["work_remaining"] == 1
        assert timing["query_busy"] == 1
        assert timing["completed_queries"] == 0
        assert not database._conn.in_transaction
        assert database._conn.execute("PRAGMA busy_timeout").fetchone()[0] == 1200
        other.rollback()
        database.set_setting("next-trade", 2)
        assert database.get_setting("protected") == 1
        assert database.get_setting("next-trade") == 2
    finally:
        other.close()
        database.close()


@pytest.mark.parametrize("case", ["success", "sql_error", "interrupt", "expired", "stop"])
def test_maintenance_restores_writer_on_every_exit(tmp_path, case):
    database = Database(tmp_path / "restore.sqlite3")
    database._conn.execute("CREATE TABLE disposable(id INTEGER)")
    with database._conn:
        database._conn.executemany("INSERT INTO disposable VALUES (?)", [(i,) for i in range(200)])
    calls = 0

    def stop():
        nonlocal calls
        calls += 1
        return case == "stop" or (case == "interrupt" and calls > 3)

    try:
        query = "DELETE FROM disposable" if case != "sql_error" else "DELETE FROM absent_table"
        deadline = time.monotonic() + (-1 if case == "expired" else 2)
        if case == "interrupt":
            query = (
                "DELETE FROM disposable WHERE id IN "
                "(SELECT a.id FROM disposable a CROSS JOIN disposable b)"
            )
        if case == "sql_error":
            with pytest.raises(sqlite3.OperationalError, match="no such table"):
                database._retention_transaction(query, (), deadline, stop)
        else:
            removed = database._retention_transaction(query, (), deadline, stop)
            assert removed == (200 if case == "success" else None)
        assert database._conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert database._conn.execute("SELECT count(*) FROM disposable").fetchone()[0] == (
            0 if case == "success" else 200
        )
        database.set_setting("ordinary-write", True)
        assert database.get_setting("ordinary-write") is True
        assert not database._conn.in_transaction
    finally:
        database.close()


@pytest.mark.parametrize("method", ["history", "retired", "budget"])
def test_expired_dispatch_budget_starts_no_sql(tmp_path, method):
    database = Database(tmp_path / "dispatch.sqlite3")
    queries = []
    database._conn.set_trace_callback(queries.append)
    database._reader_conn.set_trace_callback(queries.append)
    try:
        kwargs = {"deadline": time.monotonic() - 1}
        if method == "history":
            result = database.prune_history(datetime.now(UTC), **kwargs)
        elif method == "retired":
            result = database.prune_retired_decisions(**kwargs)
        else:
            result = database.enforce_storage_budget(1, **kwargs)
        assert result["work_remaining"] == 1
        assert queries == [], "dispatch delay must not grant a fresh cleanup budget"
    finally:
        database.close()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("parameter", ["deadline", "max_duration_seconds"])
def test_nonfinite_cleanup_bounds_are_rejected_before_sql(tmp_path, parameter, value):
    database = Database(tmp_path / "finite.sqlite3")
    try:
        for method, args in (
            (database.prune_history, (datetime.now(UTC),)),
            (database.prune_retired_decisions, ()),
            (database.enforce_storage_budget, (1,)),
        ):
            with pytest.raises(ValueError):
                method(*args, **{parameter: value})
    finally:
        database.close()


@pytest.mark.parametrize(
    "code", [sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_FULL, sqlite3.SQLITE_IOERR]
)
def test_failed_commit_is_never_reported_as_deleted(tmp_path, monkeypatch, code):
    database = Database(tmp_path / "commit.sqlite3")
    connection = database._conn
    connection.execute("CREATE TABLE disposable(id INTEGER)")
    with connection:
        connection.execute("INSERT INTO disposable VALUES(1)")

    class FailedCommit:
        def __getattr__(self, name):
            return getattr(connection, name)

        def __enter__(self):
            return connection.__enter__()

        def __exit__(self, *_args):
            connection.rollback()
            error = sqlite3.OperationalError("isolated commit failure")
            error.sqlite_errorcode = code
            raise error

    try:
        monkeypatch.setattr(database, "_conn", FailedCommit())
        if code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            assert (
                database._retention_transaction(
                    "DELETE FROM disposable", (), time.monotonic() + 1, None
                )
                is None
            )
        else:
            with pytest.raises(sqlite3.OperationalError, match="isolated commit failure"):
                database._retention_transaction(
                    "DELETE FROM disposable", (), time.monotonic() + 1, None
                )
        assert connection.execute("SELECT COUNT(*) FROM disposable").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert not connection.in_transaction
        monkeypatch.setattr(database, "_conn", connection)
        database.set_setting("next-write", True)
        assert database.get_setting("next-write") is True
    finally:
        monkeypatch.undo()
        database.close()


@pytest.mark.parametrize("cancel", [False, True])
def test_setup_delay_or_cancellation_cannot_admit_a_short_delete(tmp_path, monkeypatch, cancel):
    database = Database(tmp_path / "setup.sqlite3")
    connection = database._conn
    connection.execute("CREATE TABLE disposable(id INTEGER)")
    with connection:
        connection.execute("INSERT INTO disposable VALUES(1)")
    clock = [0.0]
    stopped = [False]
    queries = []
    connection.set_trace_callback(queries.append)

    class SlowSetup:
        def __getattr__(self, name):
            return getattr(connection, name)

        def execute(self, query, *args):
            result = connection.execute(query, *args)
            if query == "PRAGMA busy_timeout=0":
                clock[0] = 0.01 if cancel else 0.051
                stopped[0] = cancel
            return result

    timing = {"lock_wait_seconds": 0.0, "query_seconds": 0.0}
    try:
        monkeypatch.setattr(database, "_conn", SlowSetup())
        monkeypatch.setattr(database_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
        assert (
            database._retention_transaction(
                "DELETE FROM disposable",
                (),
                0.05,
                lambda: stopped[0],
                timing=timing,
            )
            is None
        )
        assert not any(query.startswith("DELETE") for query in queries)
        assert timing["query_seconds"] == 0
        assert timing["setup_seconds"] == clock[0]
        assert timing["restore_seconds"] == 0
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert connection.execute("SELECT COUNT(*) FROM disposable").fetchone()[0] == 1
    finally:
        monkeypatch.undo()
        database.close()
