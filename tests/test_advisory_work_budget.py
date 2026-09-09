"""Advisory reads must let the event loop service market work during reader contention."""

import asyncio
import sqlite3
from threading import Event, Thread, get_ident

import pytest
from fastapi import HTTPException
from signal_arcade.api import create_app
from signal_arcade.database import AdvisoryReadDeferred
from signal_arcade.models import RiskMode
from test_results_boundaries import engine  # noqa: F401


def test_missing_cohort_is_captured_without_worker_configuration_reads(engine, monkeypatch):  # noqa: F811
    owner = get_ident()
    calls = []

    def configuration():
        assert get_ident() == owner, "reader thread recalculated mutable authority"
        calls.append(1)
        return None

    monkeypatch.setattr(engine.learning, "configuration_fingerprint", configuration)
    result = asyncio.run(engine.champion_journey_view(limit=8, cursor=None))
    assert result == {"events": [], "total": 0, "next_cursor": None}
    assert len(calls) == 2  # Capture and recheck both occur under the event boundary.


async def responsive_read(database, operation):
    acquired, pulse = Event(), Event()
    timeouts = []

    def occupy_reader():
        with database._reader_lock:
            acquired.set()
            timeouts.append(not pulse.wait(1))

    thread = Thread(target=occupy_reader)
    thread.start()
    await asyncio.to_thread(acquired.wait, 2)
    # Only the event loop can release this reader promptly. A direct blocking read
    # prevents the callback until the thread's bounded failure timeout expires.
    timer = asyncio.get_running_loop().call_later(0.02, pulse.set)
    try:
        result = await operation()
    finally:
        pulse.set()
        timer.cancel()
        await asyncio.to_thread(thread.join, 2)
    assert not any(timeouts), "advisory read blocked the event-loop pulse"
    return result


@pytest.mark.parametrize("view", ["journey", "decision"])
def test_history_endpoints_keep_event_loop_responsive(settings, view):
    app = create_app(settings)
    app_engine = app.state.orchestrator
    path = (
        "/api/v1/learning/champion-journey"
        if view == "journey"
        else "/api/v1/decisions/{decision_id}"
    )
    endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == path)

    async def read():
        if view == "journey":
            return await endpoint(limit=8, cursor=None)
        with pytest.raises(HTTPException) as error:
            await endpoint(decision_id="missing")
        assert error.value.status_code == 404

    async def exercise():
        try:
            result = await responsive_read(app_engine.database, read)
            if view == "journey":
                assert result == {"events": [], "total": 0, "next_cursor": None}
        finally:
            await app_engine.http.close()

    try:
        asyncio.run(exercise())
    finally:
        app_engine.database.close()


@pytest.mark.parametrize("view", ["leaderboard", "seasons"])
def test_results_revision_keeps_event_loop_responsive(engine, view):  # noqa: F811
    asyncio.run(responsive_read(engine.database, getattr(engine, view + "_view")))


@pytest.mark.parametrize("cancel", [False, True])
def test_history_read_rechecks_cohort_and_owns_cancelled_worker(engine, monkeypatch, cancel):  # noqa: F811
    entered, release = Event(), Event()
    original = engine.learning.champion_journey_page
    calls = []

    def delayed(**kwargs):
        calls.append(kwargs["cohort"])
        entered.set()
        assert release.wait(3)
        return original(**kwargs)

    monkeypatch.setattr(engine.learning, "champion_journey_page", delayed)

    async def exercise():
        task = asyncio.create_task(engine.champion_journey_view(limit=8, cursor=None))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            # The database worker does not retain the market lock while reading.
            async with asyncio.timeout(0.2):
                async with engine._event_lock:
                    engine.learning.current_risk_mode = RiskMode.AGGRESSIVE
            if cancel:
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
                assert not task.done()
                assert engine._ui_detail_read_lock.locked()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError if cancel else ValueError):
            await task
        assert not engine._ui_detail_read_lock.locked()
        assert len(calls) == 1
        assert (await engine.champion_journey_view(limit=8, cursor=None))["events"] == []

    asyncio.run(exercise())


def test_advisory_sql_deadline_and_errors_leave_reader_and_writer_usable(engine):  # noqa: F811
    database = engine.database
    database.set_setting("advisory-test", "kept")
    with pytest.raises(AdvisoryReadDeferred):
        database.advisory_read(
            lambda: database._reader_conn.execute(
                "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<10000000) "
                "SELECT SUM(x) FROM n"
            ).fetchone()
        )
    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        database.advisory_read(
            lambda: database._reader_conn.execute("SELECT * FROM missing_advisory_fixture")
        )
    database.set_setting("advisory-test", "still writable")
    assert database.advisory_read(lambda: database.get_setting("advisory-test")) == "still writable"


def test_advisory_lock_timeout_is_retryable_without_occupying_market_lock(engine):  # noqa: F811
    entered, release = Event(), Event()

    def held():
        with engine.database._reader_lock:
            entered.set()
            release.wait(2)

    thread = Thread(target=held)
    thread.start()

    async def exercise():
        assert await asyncio.to_thread(entered.wait, 1)
        try:
            with pytest.raises(AdvisoryReadDeferred):
                await engine.decision_view("missing")
            assert not engine._event_lock.locked()
        finally:
            release.set()
            await asyncio.to_thread(thread.join, 2)
        assert await engine.decision_view("missing") is None

    asyncio.run(exercise())
