from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from signal_arcade.intelligence.features import TokenState
from signal_arcade.models import LearningObservationStatus
from signal_arcade.orchestrator import Orchestrator

# Exercise concurrent market updates through the same boundary used by worker threads.
# ruff: noqa: SLF001


@pytest.mark.parametrize("cancel", [False, True])
def test_pruning_waits_for_pending_learning_commit(settings, cancel):
    app = Orchestrator(settings)
    app.demo_mode = True
    now = datetime.now(UTC)
    mint = "PendingLearningCommit"
    app.features.tokens[mint] = TokenState(
        mint=mint, last_event_at=now - timedelta(minutes=settings.candidate_window_minutes + 1)
    )

    async def exercise():
        async with app._event_lock:
            tick = asyncio.create_task(app._enrichment_tick(now))
            await asyncio.sleep(0)
            try:
                # An in-flight market update has not yet committed its pending observation.
                assert not tick.done()
                assert mint in app.features.tokens
                if cancel:
                    tick.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await tick
                else:
                    app.learning.observations[mint] = SimpleNamespace(
                        status=LearningObservationStatus.PENDING
                    )
            finally:
                if not tick.done() and cancel:
                    tick.cancel()
        if not cancel:
            await asyncio.wait_for(tick, 1)
        assert mint in app.features.tokens
        assert not app._event_lock.locked()

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(app.http.close())
        app.database.close()


@pytest.mark.parametrize("source_switch", [False, True])
def test_exact_account_selection_waits_for_market_update_and_releases_before_io(
    settings, monkeypatch, source_switch
):
    app = Orchestrator(settings)
    app.demo_mode = False
    now = datetime.now(UTC)
    mint = "NewCandidate".ljust(40, "1")
    requested = []

    async def accounts(addresses, **_kwargs):
        # A slow provider must not keep market events or the position watchdog waiting.
        async with app._event_lock:
            requested.extend(addresses)
        return None

    monkeypatch.setattr(app.http, "solana_multiple_accounts", accounts)

    async def exercise():
        async with app._event_lock:
            task = asyncio.create_task(app._verify_candidate_accounts(now, set()))
            await asyncio.sleep(0)
            assert not task.done()
            app.features.tokens[mint] = TokenState(
                mint=mint, last_event_at=now, last_slot=10, sources={"solana:pump"}
            )
            if source_switch:
                app.demo_mode = True
        await asyncio.wait_for(task, 1)
        assert requested == ([] if source_switch else [mint])

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(app.http.close())
        app.database.close()
