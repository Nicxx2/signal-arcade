"""Capacity reads retain deadline, cancellation and fresh-page accounting semantics."""

import time

import pytest
from signal_arcade.database import Database, MaintenanceReadDeferred


def expected(database):
    with database._reader_lock:
        size, count, free = (
            int(database._reader_conn.execute("PRAGMA " + field).fetchone()[0])
            for field in ("page_size", "page_count", "freelist_count")
        )
    return {
        "database_bytes": size * count,
        "live_bytes": size * (count - free),
        "reclaimable_bytes": size * free,
    }


def test_capacity_is_one_fresh_statement_across_commits_and_reuse(tmp_path):
    database = Database(tmp_path / "capacity.sqlite3")
    try:
        with database._conn:
            database._conn.execute("CREATE TABLE disposable(payload TEXT)")
        for populated in (True, False, True):
            with database._conn:
                if populated:
                    database._conn.executemany(
                        "INSERT INTO disposable VALUES(?)", [("a" * 8192,)] * 50
                    )
                else:
                    database._conn.execute("DELETE FROM disposable")
            reference = expected(database)
            queries = []
            database._reader_conn.set_trace_callback(queries.append)
            try:
                assert database._page_usage() == reference
            finally:
                database._reader_conn.set_trace_callback(None)
            # SQLite's virtual PRAGMA implementation may trace internal statements too.
            external = [query for query in queries if not query.startswith("--")]
            assert len(external) == 1 and external[0].startswith("SELECT page_size,")
    finally:
        database.close()


@pytest.mark.parametrize("reason", ["expired", "cancelled"])
def test_capacity_cannot_bypass_maintenance_admission(tmp_path, reason):
    database = Database(tmp_path / "admission.sqlite3")
    queries = []
    database._reader_conn.set_trace_callback(queries.append)
    try:
        with pytest.raises(MaintenanceReadDeferred):
            database.maintenance_read(
                database._page_usage,
                deadline=time.monotonic() + (-1 if reason == "expired" else 2),
                stop_requested=lambda: reason == "cancelled",
            )
        assert not any("pragma_page_count" in query.lower() for query in queries)
        assert database._page_usage() == expected(database)
    finally:
        database.close()
