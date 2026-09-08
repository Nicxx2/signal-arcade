from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from signal_arcade import api
from signal_arcade import diagnostics_store as storage
from test_diagnostics import interval
from test_diagnostics_export import export_app, exported  # noqa: F401


@pytest.mark.parametrize("pressure", ["capacity", "free_disk"])
def test_paused_recording_does_not_prevent_export(export_app, monkeypatch, pressure):  # noqa: F811
    engine, store, endpoint = export_app
    for seq in range(105):
        assert store.append(interval(seq, at=1_788_000_000))
    store.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    if pressure == "capacity":
        # Sparse padding exercises the exact configured byte guard without allocating
        # half a gigabyte in every CI run. The separate capacity validation allocates it.
        with (store.directory / "capacity-fixture").open("wb") as padding:
            padding.truncate(storage.BUDGET - storage.owned_bytes(store.directory))
        assert storage.owned_bytes(store.directory) == storage.BUDGET
    else:
        monkeypatch.setattr(storage.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    core_changes = engine.database._conn.total_changes
    assert not store.append(interval(105, at=1_788_000_000))
    assert store.status()["state"] == "paused_storage"
    writes = store.connection.total_changes
    rows = asyncio.run(exported(endpoint))
    assert rows[-1] == {"type": "export_complete", "rows": 213, "read_retries": 0}
    assert store.connection.total_changes == writes
    assert engine.database._conn.total_changes == core_changes
    assert store.status()["state"] == "paused_storage"


def test_retention_can_remove_future_pages_without_repeating_previous_rows(
    export_app,  # noqa: F811
    monkeypatch,
):
    _, store, endpoint = export_app
    for seq in range(205):
        assert store.append(interval(seq, at=1_788_000_000))

    async def scenario():
        response = await endpoint()
        await anext(response.body_iterator)
        first = json.loads(await anext(response.body_iterator))
        monkeypatch.setattr(storage, "MINUTE_ROWS", 80)
        # Real writer cleanup first deletes 100 rows, then 27. The first page was
        # already fetched; subsequent reads should resume at the full keyset cursor.
        assert store.append(interval(205, at=1_788_000_000))
        assert store.append(interval(206, at=1_788_000_000))
        rest = [json.loads(line) async for line in response.body_iterator]
        minutes = [first, *(row for row in rest if row["type"] == "minute")]
        assert [row["seq"] for row in minutes] == [*range(100), *range(127, 207)]
        assert rest[-1]["type"] == "export_complete"
        assert rest[-1]["rows"] == len(rest)
        assert store.status()["ranges"]["minute"]["rows"] == 80

    asyncio.run(scenario())


def test_store_disappearing_mid_export_cannot_report_completion(export_app):  # noqa: F811
    _, store, endpoint = export_app
    for seq in range(105):
        assert store.append(interval(seq, at=1_788_000_000))

    async def scenario():
        response = await endpoint()
        await anext(response.body_iterator)
        await anext(response.body_iterator)
        # Only an isolated fixture is renamed; exports must not recreate or repair it.
        store.path.rename(store.directory / "unavailable-fixture.sqlite3")
        rest = [json.loads(line) async for line in response.body_iterator]
        assert rest[-1]["type"] == "export_incomplete"
        assert rest[-1]["reason"] == "diagnostics_file_error"
        assert rest[-1]["rows"] == 100
        assert not store.path.exists()

    asyncio.run(scenario())


def test_existing_store_lost_before_first_page_is_not_an_empty_export(export_app):  # noqa: F811
    _, store, endpoint = export_app
    assert store.append(interval())

    async def scenario():
        response = await endpoint()
        await anext(response.body_iterator)
        store.path.rename(store.directory / "unavailable-fixture.sqlite3")
        rest = [json.loads(line) async for line in response.body_iterator]
        assert rest[-1]["type"] == "export_incomplete"
        assert rest[-1]["reason"] == "diagnostics_file_error"
        assert rest[-1]["rows"] == 0

    asyncio.run(scenario())


def test_missing_recorded_history_is_not_reported_as_empty(export_app, monkeypatch):  # noqa: F811
    engine, store, endpoint = export_app
    assert store.append(interval())
    status = store.status()
    monkeypatch.setattr(engine.diagnostics, "status", lambda: status)
    store.path.rename(store.directory / "unavailable-fixture.sqlite3")
    rows = asyncio.run(exported(endpoint))
    assert rows[0]["type"] == "metadata"
    assert rows[-1]["type"] == "export_incomplete"
    assert rows[-1]["reason"] == "diagnostics_file_error"
    assert rows[-1]["rows"] == 0


def test_store_lost_after_empty_minute_tier_still_reports_file_error(
    export_app,  # noqa: F811
    monkeypatch,
):
    _, store, endpoint = export_app
    assert store.append(interval())
    with store.connection:
        store.connection.execute("DELETE FROM intervals WHERE tier=0")
    original = api.read_page

    def read(*args, **kwargs):
        rows = original(*args, **kwargs)
        if kwargs["tier"] == 0:
            assert not rows
            store.path.rename(store.directory / "unavailable-fixture.sqlite3")
        return rows

    monkeypatch.setattr(api, "read_page", read)
    rows = asyncio.run(exported(endpoint))
    assert rows[0]["type"] == "metadata"
    assert rows[-1]["type"] == "export_incomplete"
    assert rows[-1]["stage"] == "hour"
    assert rows[-1]["reason"] == "diagnostics_file_error"
    assert rows[-1]["rows"] == 0
