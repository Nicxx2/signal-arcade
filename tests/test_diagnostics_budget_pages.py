"""Read deadlines bound a complete keyset prefix instead of losing useful progress."""

import asyncio
import sqlite3
from types import SimpleNamespace

import pytest
from signal_arcade import diagnostics_store as storage
from test_diagnostics_export import export_app, exported, sqlite_error  # noqa: F401


@pytest.mark.parametrize("failure", ["elapsed", "interrupt", "io", "unexpected_interrupt"])
@pytest.mark.parametrize("tier", ["minute", "event"])
def test_budget_prefix_is_complete_and_only_deadline_can_end_it(
    export_app,  # noqa: F811
    monkeypatch,
    failure,
    tier,
):
    engine, store, endpoint = export_app
    payloads = [storage.encode({"kind": "synthetic", "id": seq}) for seq in range(41)]
    with store.connection:
        if tier == "event":
            store.connection.executemany(
                "INSERT INTO events VALUES(?,?,?,?,?)",
                [("boot", seq, 0, float(seq // 7), payloads[seq]) for seq in range(41)],
            )
        else:
            store.connection.executemany(
                "INSERT INTO intervals VALUES(?,?,?,?,?,?)",
                [
                    (0, "boot", seq, float(seq // 7), float(seq // 7), payloads[seq])
                    for seq in range(41)
                ],
            )
    actual_connect = storage.sqlite3.connect
    actual_time = storage.time
    clock = [0.0]
    connections = []

    class BudgetCursor:
        def __init__(self, cursor, connection):
            self.cursor = cursor
            self.connection = connection
            self.count = 0

        def fetchone(self):
            if self.count == 3 and failure != "elapsed":
                if failure == "interrupt":
                    clock[0] += 1
                    assert self.connection.progress() == 1
                code = sqlite3.SQLITE_IOERR if failure == "io" else sqlite3.SQLITE_INTERRUPT
                raise sqlite_error(code)
            row = self.cursor.fetchone()
            if row is not None:
                self.count += 1
                if self.count == 3 and failure == "elapsed":
                    clock[0] += 1
            return row

    class BudgetConnection:
        def __init__(self, connection):
            self.connection = connection
            self.closed = False
            self.progress = None

        def set_progress_handler(self, callback, steps):
            self.progress = callback
            self.connection.set_progress_handler(callback, steps)

        def execute(self, query, parameters=()):
            cursor = self.connection.execute(query, parameters)
            return BudgetCursor(cursor, self) if query.startswith("SELECT at,") else cursor

        def close(self):
            self.connection.close()
            self.closed = True

    def connect(*args, **kwargs):
        connection = BudgetConnection(actual_connect(*args, **kwargs))
        connections.append(connection)
        return connection

    before = (engine.database._conn.total_changes, store.connection.total_changes)
    with monkeypatch.context() as patch:
        patch.setattr(storage.sqlite3, "connect", connect)
        patch.setattr(
            storage, "time", SimpleNamespace(monotonic=lambda: clock[0], time=actual_time.time)
        )
        rows = asyncio.run(exported(endpoint))
    if failure in ("elapsed", "interrupt"):
        assert rows[-1] == {"type": "export_complete", "rows": 41, "read_retries": 0}
        assert [row["id"] for row in rows if row["type"] == tier] == list(range(41))
    else:
        assert rows[-1]["type"] == "export_incomplete"
        assert rows[-1]["reason"] == (
            "diagnostics_file_error" if failure == "io" else "diagnostics_sqlite_error"
        )
        assert rows[-1]["rows"] == rows[-1]["read_retries"] == 0
    assert connections and all(connection.closed for connection in connections)
    assert (engine.database._conn.total_changes, store.connection.total_changes) == before


def test_sqlite_progress_deadline_without_prefix_still_fails(export_app, monkeypatch):  # noqa: F811
    _, store, _ = export_app
    monkeypatch.setattr(storage, "_READ_QUERY_SECONDS", 0)
    with pytest.raises(storage.DiagnosticsReadError, match="diagnostics_query_deadline") as caught:
        storage._read_records(
            store.directory,
            "WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<1000000) "
            "SELECT sum(x) FROM n",
            (),
            require_existing=True,
        )
    assert caught.value.retryable
    assert caught.value.__cause__.sqlite_errorcode == sqlite3.SQLITE_INTERRUPT
