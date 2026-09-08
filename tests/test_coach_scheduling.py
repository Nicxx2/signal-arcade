import asyncio
import sqlite3
import threading
from datetime import UTC, datetime

import pytest
from signal_arcade.api import CoachContributionRequest, CoachResearchRequest, create_app
from signal_arcade.database import Database
from test_coach import _hypothesis
from test_coach_pressure import coach_for


@pytest.mark.parametrize("change", [None, "disabled", "pressure", "context"])
@pytest.mark.parametrize("active", [False, True])
def test_monitor_lookup_yields_and_rechecks_admission(tmp_path, monkeypatch, change, active):
    database = Database(tmp_path / "monitor.sqlite3")
    if active:
        database.save_coach_hypothesis(_hypothesis(datetime.now(UTC)))
    coach = coach_for(database)
    # Keep this test at the lookup boundary, independent of forward-outcome evaluation.
    monkeypatch.setattr(coach, "_refresh_hypotheses", lambda *args, **kwargs: None)
    original = database.coach_context_hypotheses
    entered, release = threading.Event(), threading.Event()

    async def exercise():
        loop_thread = threading.get_ident()

        def blocked(*args, **kwargs):
            assert threading.get_ident() != loop_thread, "Coach read blocked the event loop"
            entered.set()
            assert release.wait(3)
            return original(*args, **kwargs)

        monkeypatch.setattr(database, "coach_context_hypotheses", blocked)
        task = asyncio.create_task(coach.tick())
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            assert not task.done()
            if change == "disabled":
                coach.enabled = lambda: False
            elif change == "pressure":
                coach.can_run = lambda: (False, "protecting_market_throughput")
            elif change == "context":
                coach.provenance = lambda: {"dependency_versions": {"exit": "replacement"}}
        finally:
            release.set()
            await task
        expected = {
            "disabled": "ai_shadow_off",
            "pressure": "protecting_market_throughput",
            "context": "context_changed",
        }
        if change:
            assert coach.paused_reason == expected[change]
            assert database.list_coach_reviews() == []
        elif active:
            assert coach.paused_reason == "forward_test_in_progress"
            assert database.list_coach_reviews() == []
        else:
            assert len(database.list_coach_reviews()) == 1
        assert coach.http.calls == 0

    try:
        asyncio.run(exercise())
    finally:
        database.close()


@pytest.mark.parametrize("control", ["research", "contribution"])
def test_coach_control_status_yields_and_owns_cancelled_read(settings, monkeypatch, control):
    app = create_app(settings)
    engine = app.state.orchestrator
    path = f"/api/v1/ai-lab/coach-{control}"
    endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == path)
    body = (CoachResearchRequest if control == "research" else CoachContributionRequest)(
        enabled=False
    )
    # HTTP auth, permission validation and mutation serialization have separate API tests.
    setter = f"set_coach_{control}_enabled"
    monkeypatch.setattr(engine, setter, lambda *_: None)
    original = engine.coach.status
    expected = original()
    entered, release = threading.Event(), threading.Event()
    state_lock = threading.Lock()
    counts = {"entered": 0, "exited": 0}

    async def exercise():
        loop_thread = threading.get_ident()

        def blocked():
            assert threading.get_ident() != loop_thread, "Status read blocked the event loop"
            with state_lock:
                counts["entered"] += 1
                if counts["entered"] == 2:
                    entered.set()
            try:
                assert release.wait(3)
                return original()
            finally:
                with state_lock:
                    counts["exited"] += 1

        monkeypatch.setattr(engine.coach, "status", blocked)
        first = asyncio.create_task(endpoint(body))
        second = asyncio.create_task(endpoint(body))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            first.cancel()
            await asyncio.sleep(0)
            first.cancel()
            await asyncio.sleep(0.02)
            assert not first.done(), "Request abandoned a database worker during cancellation"
            assert not second.done()
        finally:
            release.set()
            results = await asyncio.gather(first, second, return_exceptions=True)
        assert isinstance(results[0], asyncio.CancelledError)
        assert results[1] == expected
        assert counts == {"entered": 2, "exited": 2}

    try:
        asyncio.run(exercise())
    finally:
        engine.database.close()


@pytest.mark.parametrize("control", ["research", "contribution"])
def test_coach_control_read_error_is_not_a_successful_empty_status(settings, monkeypatch, control):
    app = create_app(settings)
    engine = app.state.orchestrator
    endpoint = next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == f"/api/v1/ai-lab/coach-{control}"
    )
    body = (CoachResearchRequest if control == "research" else CoachContributionRequest)(
        enabled=False
    )
    monkeypatch.setattr(engine, f"set_coach_{control}_enabled", lambda *_: None)
    original = engine.coach.status

    def fail():
        raise sqlite3.OperationalError("injected read failure")

    async def exercise():
        monkeypatch.setattr(engine.coach, "status", fail)
        with pytest.raises(sqlite3.OperationalError, match="injected read failure"):
            await endpoint(body)
        monkeypatch.setattr(engine.coach, "status", original)
        assert (await endpoint(body))["influence"] == "none"

    try:
        asyncio.run(exercise())
    finally:
        engine.database.close()
