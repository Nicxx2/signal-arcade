"""Adaptive page work stays within the original query and retry limits."""

import asyncio

import pytest
from signal_arcade import api
from signal_arcade import diagnostics_store as storage
from test_diagnostics_export import export_app, exported  # noqa: F401


@pytest.mark.parametrize("tier", ["minute", "event"])
def test_deadline_reduces_and_keeps_page_size_without_losing_rows(export_app, monkeypatch, tier):  # noqa: F811
    engine, store, endpoint = export_app
    payload = storage.encode({"kind": "synthetic"})
    with store.connection:
        if tier == "event":
            store.connection.executemany(
                "INSERT INTO events VALUES(?,?,?,?,?)",
                [("boot", seq, 0, float(seq // 7), payload) for seq in range(251)],
            )
        else:
            store.connection.executemany(
                "INSERT INTO intervals VALUES(?,?,?,?,?,?)",
                [(0, "boot", seq, float(seq // 7), float(seq // 7), payload) for seq in range(251)],
            )
    original = api.read_events if tier == "event" else api.read_page
    calls = []

    def under_pressure(*args, **kwargs):
        calls.append((kwargs["limit"], kwargs.get("after")))
        if kwargs["limit"] > 25:
            raise storage.DiagnosticsReadError("diagnostics_query_deadline", retryable=True)
        return original(*args, **kwargs)

    monkeypatch.setattr(api, "read_events" if tier == "event" else "read_page", under_pressure)
    before = (engine.database._conn.total_changes, store.connection.total_changes)
    rows = asyncio.run(exported(endpoint))
    assert rows[-1] == {"type": "export_complete", "rows": 251, "read_retries": 2}
    assert calls[:3] == [(100, None), (50, None), (25, None)]
    assert all(size == 25 for size, _ in calls[2:])
    assert sum(row["type"] == tier for row in rows) == 251
    assert (engine.database._conn.total_changes, store.connection.total_changes) == before


def test_small_event_pages_preserve_equal_timestamp_cursor_order(export_app):  # noqa: F811
    _, store, _ = export_app
    payload = storage.encode({"kind": "synthetic"})
    with store.connection:
        store.connection.executemany(
            "INSERT INTO events VALUES(?,?,?,?,?)",
            [
                (boot, seq, item, 1.0, payload)
                for boot in ("a", "b")
                for seq in range(19)
                for item in range(3)
            ],
        )
    after = None
    keys = []
    while page := storage.read_events(store.directory, after=after, before=2, limit=7):
        keys.extend(tuple(row["cursor"]) for row in page)
        after = tuple(page[-1]["cursor"])
    assert len(keys) == 114 and keys == sorted(set(keys))
