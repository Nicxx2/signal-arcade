"""Isolated export failures must never change the recorder or paper/learning database."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
import zlib

import pytest
from fastapi import HTTPException
from signal_arcade import api
from signal_arcade import diagnostics_store as storage
from test_diagnostics import interval


@pytest.fixture
def export_app(settings):
    app = api.create_app(settings)
    endpoint = next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == "/api/v1/diagnostics/export"
    )
    store = storage.DiagnosticsStore(app.state.orchestrator.diagnostics.directory)
    try:
        yield app.state.orchestrator, store, endpoint
    finally:
        store.close()
        app.state.orchestrator.database.close()


async def exported(endpoint):
    response = await endpoint()
    return [json.loads(line) async for line in response.body_iterator]


def sqlite_error(code):
    error = sqlite3.OperationalError("private path or details must not reach the export")
    error.sqlite_errorcode = code
    return error


def test_real_wal_lock_retry_recovers_without_blocking_event_loop(export_app, monkeypatch):
    engine, store, endpoint = export_app
    assert store.append(interval())
    store.close()
    lock = sqlite3.connect(store.path, timeout=0.02)
    lock.execute("PRAGMA locking_mode=EXCLUSIVE")
    lock.execute("BEGIN EXCLUSIVE")
    lock.execute("UPDATE metadata SET value=value")
    failed = threading.Event()
    original = api.read_page
    attempts = []

    def read(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except storage.DiagnosticsReadError as exc:
            attempts.append(exc.reason)
            failed.set()
            raise

    monkeypatch.setattr(api, "read_page", read)

    async def scenario():
        task = asyncio.create_task(exported(endpoint))
        ticks = 0
        async with asyncio.timeout(3):
            while not failed.is_set():
                await asyncio.sleep(0.001)
                ticks += 1
        lock.rollback()
        lock.close()
        rows = await task
        assert ticks > 1
        assert rows[-1] == {"type": "export_complete", "rows": 3, "read_retries": 1}
        assert attempts == ["diagnostics_sqlite_busy"]

    try:
        asyncio.run(scenario())
    finally:
        lock.close()
    # A failed reader neither changes the paper database nor disables the recorder.
    resumed = storage.DiagnosticsStore(engine.diagnostics.directory)
    try:
        assert resumed.append(interval(1))
        assert len(storage.read_page(engine.diagnostics.directory, tier=0)) == 2
    finally:
        resumed.close()


@pytest.mark.parametrize(
    "failure,reason,retries",
    [
        (sqlite_error(sqlite3.SQLITE_BUSY), "diagnostics_sqlite_busy", 2),
        (sqlite_error(sqlite3.SQLITE_BUSY_RECOVERY), "diagnostics_sqlite_busy", 2),
        (sqlite_error(sqlite3.SQLITE_LOCKED), "diagnostics_sqlite_locked", 2),
        (sqlite_error(sqlite3.SQLITE_INTERRUPT), "diagnostics_sqlite_error", 0),
        (sqlite_error(sqlite3.SQLITE_CORRUPT), "diagnostics_sqlite_error", 0),
        (sqlite_error(sqlite3.SQLITE_CANTOPEN), "diagnostics_file_error", 0),
        (sqlite_error(sqlite3.SQLITE_IOERR_READ), "diagnostics_file_error", 0),
        (PermissionError("private path"), "diagnostics_file_error", 0),
    ],
)
def test_permanent_failure_is_bounded_specific_and_isolated(
    export_app, monkeypatch, failure, reason, retries
):
    engine, store, endpoint = export_app
    assert store.append(interval())
    core_changes = engine.database._conn.total_changes
    recording_changes = store.connection.total_changes
    calls = 0

    def unavailable(*args, **kwargs):
        nonlocal calls
        calls += 1
        assert kwargs["uri"] is True
        assert kwargs["timeout"] == 0.02
        assert args[0].endswith("/history.sqlite3?mode=ro")
        raise failure

    with monkeypatch.context() as patch:
        patch.setattr(storage.sqlite3, "connect", unavailable)
        started = time.monotonic()
        rows = asyncio.run(exported(endpoint))
    assert time.monotonic() - started < 2
    assert rows[-1] == {
        "type": "export_incomplete",
        "rows": 0,
        "reason": reason,
        "stage": "minute",
        "read_retries": retries,
    }
    assert len(rows) == 2
    assert "private" not in json.dumps(rows)
    assert calls == retries + 1
    assert engine.database._conn.total_changes == core_changes
    assert store.connection.total_changes == recording_changes
    assert store.append(interval(1))
    assert asyncio.run(exported(endpoint))[-1]["type"] == "export_complete"


def test_real_query_deadline_is_distinct_and_bounded(export_app, monkeypatch):
    _, store, endpoint = export_app
    for seq in range(110):
        assert store.append(interval(seq))
    monkeypatch.setattr(storage, "_READ_QUERY_SECONDS", 0)
    with pytest.raises(storage.DiagnosticsReadError, match="diagnostics_query_deadline") as caught:
        storage.read_page(store.directory, tier=0)
    # A zero budget may now stop before fetching, rather than waiting for the SQLite
    # callback. Both paths must remain a retryable deadline, never an empty success.
    assert caught.value.retryable
    rows = asyncio.run(exported(endpoint))
    assert rows[-1]["reason"] == "diagnostics_query_deadline"
    assert rows[-1]["read_retries"] == 2
    assert rows[-1]["rows"] == 0


def test_transient_query_deadline_retries_same_page(export_app, monkeypatch):
    _, store, endpoint = export_app
    for seq in range(110):
        assert store.append(interval(seq))
    original = api.read_page
    calls = 0

    def first_query_times_out(*args, **kwargs):
        nonlocal calls
        calls += 1
        with monkeypatch.context() as patch:
            if calls == 1:
                patch.setattr(storage, "_READ_QUERY_SECONDS", 0)
            return original(*args, **kwargs)

    monkeypatch.setattr(api, "read_page", first_query_times_out)
    rows = asyncio.run(exported(endpoint))
    assert rows[-1]["type"] == "export_complete"
    assert rows[-1]["read_retries"] == 1
    assert [row["seq"] for row in rows if row["type"] == "minute"] == list(range(110))


@pytest.mark.parametrize("kind", ["minute", "hour", "event"])
def test_later_page_retry_preserves_cursor_and_cutoff(export_app, monkeypatch, kind):
    _, store, endpoint = export_app
    # Equal timestamps with distinct boots exercise the complete keyset, including event items.
    for number in range(205):
        assert store.append(interval(0, boot=f"{number:032x}"))
    attribute = "read_events" if kind == "event" else "read_page"
    original = getattr(api, attribute)
    attempts = []
    failed = False
    wanted_tier = 0 if kind == "minute" else 1

    def read(*args, **kwargs):
        nonlocal failed
        attempts.append(dict(kwargs))
        matching = kind == "event" or kwargs["tier"] == wanted_tier
        # Hour has one aggregate; exercise retry at its first page too.
        if matching and (kwargs["after"] is not None or kind == "hour") and not failed:
            failed = True
            raise storage.DiagnosticsReadError("diagnostics_sqlite_locked", retryable=True)
        return original(*args, **kwargs)

    monkeypatch.setattr(api, attribute, read)
    rows = asyncio.run(exported(endpoint))
    assert failed
    assert rows[-1]["type"] == "export_complete"
    assert rows[-1]["read_retries"] == 1
    assert rows[-1]["rows"] == 411
    minutes = [row for row in rows if row["type"] == "minute"]
    assert len({(row["boot"], row["seq"]) for row in minutes}) == 205
    assert len({attempt["before"] for attempt in attempts}) == 1
    assert any(a == b for a, b in zip(attempts, attempts[1:], strict=False))


def test_repeated_contention_has_an_export_wide_retry_budget(export_app, monkeypatch):
    _, store, endpoint = export_app
    for seq in range(710):
        assert store.append(interval(seq))
    original = api.read_page
    seen = set()

    def once_per_page(*args, **kwargs):
        key = (kwargs["tier"], kwargs["after"])
        if key not in seen:
            seen.add(key)
            raise storage.DiagnosticsReadError("diagnostics_sqlite_busy", retryable=True)
        return original(*args, **kwargs)

    monkeypatch.setattr(api, "read_page", once_per_page)
    rows = asyncio.run(exported(endpoint))
    assert rows[-1]["type"] == "export_incomplete"
    assert rows[-1]["read_retries"] == 6
    assert rows[-1]["rows"] == 600
    assert len({row["seq"] for row in rows if row["type"] == "minute"}) == 600


@pytest.mark.parametrize(
    "payload",
    [
        b"corrupt",
        zlib.compress(b"null"),
        zlib.compress(b'{"skills":[null]}'),
        zlib.compress(b'{"gauges":{"bad":NaN}}'),
        zlib.compress(b'{"gauges":' + b"[" * 10_000 + b"0" + b"]" * 10_000 + b"}"),
    ],
)
def test_bad_record_is_reported_without_retry_or_false_completion(export_app, payload):
    _, store, endpoint = export_app
    assert store.append(interval())
    with store.connection:
        store.connection.execute("UPDATE intervals SET payload=? WHERE tier=0", (payload,))
    rows = asyncio.run(exported(endpoint))
    assert rows[-1]["reason"] == "diagnostics_decode_error"
    assert rows[-1]["read_retries"] == 0
    assert rows[-1]["rows"] == 0


def test_unsupported_schema_is_reported_without_retry_or_repair(export_app):
    _, store, endpoint = export_app
    store.connection.execute("PRAGMA user_version=999")
    rows = asyncio.run(exported(endpoint))
    assert rows[-1]["reason"] == "diagnostics_schema_unsupported"
    assert rows[-1]["read_retries"] == 0
    assert store.connection.execute("PRAGMA user_version").fetchone()[0] == 999


@pytest.mark.parametrize("missing", [False, True])
def test_empty_or_missing_store_remains_an_explicit_empty_export(export_app, missing):
    _, store, endpoint = export_app
    if missing:
        store.close()
        store.path.unlink()
    rows = asyncio.run(exported(endpoint))
    assert rows[-1] == {"type": "export_complete", "rows": 0, "read_retries": 0}


def test_streaming_releases_read_snapshot_and_keeps_original_cutoff(export_app):
    _, store, endpoint = export_app
    for seq in range(105):
        assert store.append(interval(seq, at=1_788_000_000))

    async def scenario():
        response = await endpoint()
        metadata = json.loads(await anext(response.body_iterator))
        first = json.loads(await anext(response.body_iterator))
        assert first["type"] == "minute"
        # A client stalled partway through a page must not pin a WAL read snapshot.
        assert store.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0
        assert store.append(interval(0, boot="b" * 32, at=metadata["exported_at"] + 60))
        rest = [json.loads(line) async for line in response.body_iterator]
        minutes = [first, *(row for row in rest if row["type"] == "minute")]
        assert [row["seq"] for row in minutes] == list(range(105))
        assert rest[-1]["type"] == "export_complete"
        assert rest[-1]["rows"] == 213

    asyncio.run(scenario())


def test_thousands_export_during_wal_checkpoint_contention(export_app):
    _, store, endpoint = export_app
    assert store.append(interval(0, at=1_788_000_000))
    pinned = sqlite3.connect(f"{store.path.as_uri()}?mode=ro", uri=True, timeout=0.02)
    try:
        pinned.execute("BEGIN")
        pinned.execute("SELECT at FROM intervals LIMIT 1").fetchone()
        for seq in range(1, 3000):
            assert store.append(interval(seq, at=1_788_000_000))
        # The old read snapshot prevents truncation; WAL reads still see committed new rows.
        assert store.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 1
        changes = store.connection.total_changes
        rows = asyncio.run(exported(endpoint))
        assert rows[-1] == {"type": "export_complete", "rows": 6051, "read_retries": 0}
        assert len([row for row in rows if row["type"] == "event"]) == 3000
        assert [row["seq"] for row in rows if row["type"] == "minute"] == list(range(3000))
        assert store.connection.total_changes == changes
        assert store.append(interval(3000, at=1_788_000_000))
    finally:
        pinned.close()
    assert store.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0


def test_cancelled_export_keeps_its_slot_until_detached_read_finishes(export_app, monkeypatch):
    _, _, endpoint = export_app
    finish = threading.Event()

    async def scenario():
        started = asyncio.Event()
        loop = asyncio.get_running_loop()

        def delayed_read(*args, **kwargs):
            loop.call_soon_threadsafe(started.set)
            assert finish.wait(3)
            return []

        monkeypatch.setattr(api, "read_page", delayed_read)
        first, second = await endpoint(), await endpoint()
        await anext(first.body_iterator)
        await anext(second.body_iterator)
        task = asyncio.create_task(anext(first.body_iterator))
        try:
            async with asyncio.timeout(3):
                await started.wait()
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(HTTPException) as caught:
                await endpoint()
            assert caught.value.status_code == 429
            assert not task.done()
        finally:
            finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        third = await endpoint()
        await third.background()
        await second.body_iterator.aclose()

    asyncio.run(scenario())


def test_cancellation_during_backoff_releases_slot_without_retry(export_app, monkeypatch):
    _, _, endpoint = export_app
    calls = 0
    monkeypatch.setattr(api, "_DIAGNOSTICS_RETRY_DELAYS", (10, 10))

    async def scenario():
        started = asyncio.Event()
        loop = asyncio.get_running_loop()

        def unavailable(*args, **kwargs):
            nonlocal calls
            calls += 1
            loop.call_soon_threadsafe(started.set)
            raise storage.DiagnosticsReadError("diagnostics_sqlite_busy", retryable=True)

        monkeypatch.setattr(api, "read_page", unavailable)
        first = await endpoint()
        task = asyncio.create_task(anext(first.body_iterator))
        await task  # Metadata is always first.
        task = asyncio.create_task(anext(first.body_iterator))
        async with asyncio.timeout(3):
            await started.wait()
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert calls == 1
        second, third = await endpoint(), await endpoint()
        await second.background()
        await third.background()

    asyncio.run(scenario())
