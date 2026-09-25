"""Delayed optional responses cannot block the loop or cross a token/route boundary."""

# ruff: noqa: F811 -- shared fixture

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event

import pytest
from signal_arcade.intelligence.features import FeatureEngine, TokenState
from signal_arcade.providers.solana import PUMP_AMM_PROGRAM
from test_probe_retention import engine  # noqa: F401


def route(engine):
    state = TokenState(mint="M" * 44, venue="pump_swap", pool_address="P" * 44)
    engine.features.tokens[state.mint] = state
    return state


@pytest.mark.parametrize(
    "change",
    [
        "none",
        "engine",
        "token",
        "pool",
        "provider",
        "source",
        "newer",
        "trade",
        "removed",
        "venue",
        "stop",
        "maintenance",
    ],
)
@pytest.mark.parametrize("available", [False, True])
def test_route_result_keeps_original_request_identity(engine, monkeypatch, change, available):
    state = route(engine)
    now = datetime.now(UTC)
    requested, release = asyncio.Event(), asyncio.Event()
    original_pool = state.pool_address
    decoded = {
        "base_mint": state.mint,
        "quote_mint": "Q" * 44,
        "pool_base_token_account": "B" * 44,
        "pool_quote_token_account": "T" * 44,
    }

    async def fetch(address, **kwargs):
        assert address == original_pool and kwargs == {"critical": True}
        assert not engine._event_lock.locked()
        requested.set()
        await release.wait()
        return {"owner": PUMP_AMM_PROGRAM, "raw": b"fixture"} if available else None

    monkeypatch.setattr(engine.http, "solana_account_info", fetch)
    monkeypatch.setattr(engine.solana, "decode_pump_swap_pool", lambda _: decoded)

    async def run():
        task = asyncio.create_task(engine._verify_pumpswap_route(state, now))
        await requested.wait()
        current = state
        if change == "engine":
            engine.features = FeatureEngine()
        if change in {"engine", "token"}:
            current = TokenState(mint=state.mint, venue="pump_swap", pool_address=original_pool)
            engine.features.tokens[state.mint] = current
        if change == "pool":
            state.pool_address = "N" * 44
        if change == "provider":
            engine.http.solana_generation += 1
        if change == "source":
            engine.demo_mode = not engine.demo_mode
        if change == "newer":
            state.route_verified = True
            state.pool_base_token_account = "V" * 44
        if change == "trade":
            state.last_slot += 100
            state.last_event_at = now
        if change == "removed":
            del engine.features.tokens[state.mint]
        if change == "venue":
            state.venue = "pump_curve"
        if change == "stop":
            engine.stop_event.set()
        if change == "maintenance":
            engine._maintenance_requested = True
        # An obsolete response must not clear or increase a replacement's backoff.
        engine._route_retry_at[state.mint] = now
        engine._route_retry_delay_seconds[state.mint] = 120
        release.set()
        result = await task
        if change not in {"none", "trade", "newer"}:
            assert result is False and not current.route_verified
            assert engine._route_retry_at[state.mint] == now
            assert engine._route_retry_delay_seconds[state.mint] == 120
        elif change == "newer":
            assert result is True and state.pool_base_token_account == "V" * 44
            assert engine._route_retry_delay_seconds[state.mint] == 120
        else:
            assert result is available and state.route_verified is available
            if available:
                assert state.pool_base_token_account == "B" * 44
                assert state.mint not in engine._route_retry_at
            else:
                assert engine._route_retry_delay_seconds[state.mint] == 240
        assert not engine._event_lock.locked()

    asyncio.run(run())


@pytest.mark.parametrize("change", ["token", "source", "stop", "maintenance"])
def test_metadata_waiter_rechecks_context_before_mutation(engine, monkeypatch, change):
    state = route(engine)
    now = datetime.now(UTC)
    requested = asyncio.Event()

    async def fetch(_mint):
        requested.set()
        return {"base_token_name": "Old response"}

    monkeypatch.setattr(engine.http, "dexscreener_token", fetch)

    async def run():
        async with engine._event_lock:
            task = asyncio.create_task(engine._enrich_candidate_metadata(state, now))
            await requested.wait()
            assert not task.done()
            if change == "token":
                engine.features.tokens[state.mint] = TokenState(mint=state.mint)
            elif change == "source":
                engine.demo_mode = not engine.demo_mode
            elif change == "stop":
                engine.stop_event.set()
            else:
                engine._maintenance_requested = True
        await task
        assert state.name == "Unknown token"
        assert not engine.features.tokens[state.mint].enrichment
        assert state.mint not in engine.enriched_at

    asyncio.run(run())


def test_metadata_lock_contention_does_not_block_async_progress(engine, monkeypatch):
    state = route(engine)
    locked, release = Event(), Event()
    released_by_loop = []

    async def fetch(_mint):
        return {"base_token_name": "Example"}

    def holder():
        with engine.features._lock:
            locked.set()
            released_by_loop.append(release.wait(2))

    monkeypatch.setattr(engine.http, "dexscreener_token", fetch)

    async def run():
        task = asyncio.create_task(engine._enrich_candidate_metadata(state, datetime.now(UTC)))
        # Run after the callback has reached its contended feature operation.
        await asyncio.sleep(0.01)
        release.set()
        await task

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(holder)
        assert locked.wait(2)
        try:
            asyncio.run(run())
        finally:
            release.set()
            future.result(timeout=3)
    assert released_by_loop == [True], "metadata blocked the event loop on the feature lock"
    assert state.name == "Example"


@pytest.mark.parametrize("cancel", [False, True])
def test_metadata_worker_keeps_boundary_until_apply_finishes(engine, monkeypatch, cancel):
    state = route(engine)
    entered, release = Event(), Event()
    original = engine.features.add_enrichment

    async def fetch(_mint):
        assert not engine._event_lock.locked()
        return {"base_token_name": "Example"}

    def apply(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        original(*args, **kwargs)

    monkeypatch.setattr(engine.http, "dexscreener_token", fetch)
    monkeypatch.setattr(engine.features, "add_enrichment", apply)

    async def run():
        task = asyncio.create_task(engine._enrich_candidate_metadata(state, datetime.now(UTC)))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            assert engine._event_lock.locked()
            if cancel:
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
            assert not task.done()
        finally:
            release.set()
        if cancel:
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task
        assert not engine._event_lock.locked()
        assert state.name == "Example"

    asyncio.run(run())
