from __future__ import annotations

import asyncio
import copy
from datetime import timedelta

import pytest
from signal_arcade.intelligence.features import (
    NATIVE_SOL_MINT,
    WRAPPED_SOL_MINT,
    FeatureEngine,
)
from signal_arcade.intelligence.reserve_refresh import (
    ReserveRefreshRejected,
    reserve_addresses,
    validated_learning_state,
)
from signal_arcade.models import EventKind, MarketEvent, Position, PositionMarketStatus
from signal_arcade.orchestrator import Orchestrator
from signal_arcade.providers.http import SPL_TOKEN_PROGRAM
from signal_arcade.providers.solana import PUMP_AMM_PROGRAM
from test_v1104_refresh import anchor_account, route_fixture, vault


@pytest.mark.parametrize("already_verified", [False, True])
def test_verified_pool_quote_recovers_cached_native_quote_atomically(already_verified):
    state, result, decoder, now = route_fixture("pump_swap")
    state.quote_mint = NATIVE_SOL_MINT
    state.route_verified = already_verified
    before = copy.deepcopy(state)
    refreshed = validated_learning_state(state, result, decoder, requested_at=now, observed_at=now)

    assert state == before  # Learning-only validation never changes the live object.
    assert refreshed.quote_mint == WRAPPED_SOL_MINT
    assert refreshed.reserve_audit["route_identity"][-1] == WRAPPED_SOL_MINT
    assert refreshed.route_verified
    features = FeatureEngine()
    features.tokens[state.mint] = state
    assert features.apply_validated_watchdog_snapshot(refreshed)
    assert features.tokens[state.mint] is state
    assert state.quote_mint == WRAPPED_SOL_MINT
    assert state.route_verified
    assert state.last_event_at == before.last_event_at
    assert "unsupported_quote_mint_v1" not in features.position_snapshot(state.mint, now).hard_flags


@pytest.mark.parametrize(
    "failure",
    [
        "owner",
        "quote",
        "base_mint",
        "vault_mint",
        "vault_authority",
        "mapping",
        "pda",
        "disabled",
        "old_slot",
        "late",
    ],
)
def test_quote_recovery_requires_the_complete_valid_account_set(failure):
    state, result, decoder, now = route_fixture("pump_swap")
    state.quote_mint = NATIVE_SOL_MINT
    state.route_verified = True  # Reproduce the legacy inconsistent state.
    account = result["accounts"][state.pool_address]
    pool = decoder.decode_account(account["raw"], expected_program=PUMP_AMM_PROGRAM)[2]
    observed = now
    if failure == "owner":
        account["owner"] = SPL_TOKEN_PROGRAM
    elif failure == "quote":
        pool["quote_mint"] = NATIVE_SOL_MINT
    elif failure == "base_mint":
        pool["base_mint"] = WRAPPED_SOL_MINT
    elif failure == "vault_mint":
        result["accounts"][state.pool_quote_token_account] = vault(
            state.mint, state.pool_address, 30 * 10**9
        )
    elif failure == "vault_authority":
        result["accounts"][state.pool_quote_token_account] = vault(
            WRAPPED_SOL_MINT, state.mint, 30 * 10**9
        )
    elif failure == "mapping":
        pool["pool_quote_token_account"] = state.pool_base_token_account
    elif failure == "pda":
        pool["index"] = 1
    elif failure == "disabled":
        global_account = result["accounts"][reserve_addresses(state)[2]]
        global_values = decoder.decode_account(
            global_account["raw"], expected_program=PUMP_AMM_PROGRAM
        )[2]
        global_values["disable_flags"] = 16
        global_account["raw"] = anchor_account("pump_amm", "GlobalConfig", global_values)
    elif failure == "old_slot":
        result["slot"] = 99
    else:
        observed += timedelta(seconds=9)
    account["raw"] = anchor_account("pump_amm", "Pool", pool)
    before = copy.deepcopy(state)
    with pytest.raises(ReserveRefreshRejected):
        validated_learning_state(state, result, decoder, requested_at=now, observed_at=observed)
    assert state == before


@pytest.mark.parametrize("change", ["pool", "base_vault", "quote_vault", "slot", "duplicate"])
def test_quote_recovery_cannot_cross_newer_route_or_slot(change):
    state, result, decoder, now = route_fixture("pump_swap")
    state.quote_mint = NATIVE_SOL_MINT
    refreshed = validated_learning_state(state, result, decoder, requested_at=now, observed_at=now)
    features = FeatureEngine()
    features.tokens[state.mint] = state
    if change == "pool":
        state.pool_address = state.mint
    elif change == "base_vault":
        state.pool_base_token_account = state.mint
    elif change == "quote_vault":
        state.pool_quote_token_account = state.mint
    elif change == "slot":
        state.last_slot = result["slot"] + 1
    else:
        state.last_reserve_slot = result["slot"]
    before = copy.deepcopy(state)
    assert not features.apply_validated_watchdog_snapshot(refreshed)
    assert state == before


def test_recovered_quote_stays_pinned_only_for_the_verified_pool():
    state, result, decoder, now = route_fixture("pump_swap")
    state.quote_mint = NATIVE_SOL_MINT
    features = FeatureEngine()
    features.tokens[state.mint] = state
    refreshed = validated_learning_state(state, result, decoder, requested_at=now, observed_at=now)
    assert features.apply_validated_watchdog_snapshot(refreshed)
    for index, pool in enumerate([state.pool_address, state.mint]):
        features.apply(
            MarketEvent(
                event_id=f"quote-log-{index}",
                source=f"solana:{PUMP_AMM_PROGRAM}",
                kind=EventKind.TRADE,
                mint=state.mint,
                slot=102 + index,
                received_at=now + timedelta(seconds=index + 1),
                payload={
                    "event_name": "BuyEvent",
                    "pool": pool,
                    "quote_mint": NATIVE_SOL_MINT,
                },
            )
        )
        assert state.route_verified is (index == 0)
        assert state.quote_mint == (WRAPPED_SOL_MINT if index == 0 else NATIVE_SOL_MINT)


@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("restart", [False, True])
def test_watchdog_repairs_persisted_position_without_inventing_liquidity(settings, empty, restart):
    engine = Orchestrator(settings)
    state, result, _decoder, now = route_fixture("pump_swap")
    state.quote_mint = NATIVE_SOL_MINT
    state.route_verified = True
    engine.features.tokens[state.mint] = state
    position = Position(
        position_id="quote-recovery",
        mint=state.mint,
        symbol="RECOVERY",
        token_units=10**12,
        entry_cost_lamports=10**6,
        book_value_lamports=10**6,
        opened_at=now - timedelta(hours=2),
        entry_fill_id="entry",
        venue=state.venue,
        curve_address=state.curve_address,
        pool_address=state.pool_address,
        pool_base_token_account=state.pool_base_token_account,
        pool_quote_token_account=state.pool_quote_token_account,
        quote_mint=NATIVE_SOL_MINT,
        market_status=PositionMarketStatus.EXIT_BLOCKED,
        mark_is_executable=False,
        mark_blockers=["unsupported_quote_mint_v1"],
    )
    engine.database.save_position(position)
    engine.broker.positions[state.mint] = position
    if restart:
        asyncio.run(engine.http.close())
        engine.database.close()
        engine = Orchestrator(settings)
        state = engine.features.tokens[state.mint]
        position = engine.broker.positions[state.mint]
        assert state.quote_mint == NATIVE_SOL_MINT
    if empty:
        result["accounts"][state.pool_quote_token_account] = vault(
            WRAPPED_SOL_MINT, state.pool_address, 0
        )
    try:
        targets = engine._position_watchdog_targets()[0]
        receipts, refreshed, _slot = engine._apply_position_watchdog_result(targets, result, now)
        assert receipts == []  # A stopped engine refreshes marks without submitting an exit.
        assert refreshed == {state.mint}
        assert position.quote_mint == WRAPPED_SOL_MINT
        assert position.mark_is_executable is (not empty)
        assert "unsupported_quote_mint_v1" not in position.mark_blockers
        assert engine._position_route_probes[state.mint]["outcome"] == (
            "unavailable" if empty else "available"
        )
        stored = next(p for p in engine.database.list_positions() if p.mint == state.mint)
        assert stored.quote_mint == WRAPPED_SOL_MINT
        assert stored.mark_is_executable is (not empty)
        # Normal exit management must resume once fresh evidence recovers the route.
        # Keep the actual fill deferred so this fixture does not invent a historical buy.
        engine.running = True
        engine.settings.exit_latency_ms = 1000
        result["slot"] += 1
        engine._apply_position_watchdog_result(targets, result, now + timedelta(seconds=1))
        assert len(engine.broker.pending) == (0 if empty else 1)
        if not empty:
            order = next(iter(engine.broker.pending.values()))
            assert order.mint == state.mint and order.side.value == "sell"
            assert order.created_at == now + timedelta(seconds=1)
    finally:
        asyncio.run(engine.http.close())
        engine.database.close()
