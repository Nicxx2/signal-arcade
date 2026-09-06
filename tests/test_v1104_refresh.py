from __future__ import annotations

import asyncio
import copy
import json
import struct
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from signal_arcade.intelligence.features import NATIVE_SOL_MINT, WRAPPED_SOL_MINT, TokenState
from signal_arcade.intelligence.learning import LearningEngine
from signal_arcade.intelligence.reserve_refresh import (
    FEE_PROGRAM,
    ReserveRefreshRejected,
    pda,
    reserve_addresses,
    validated_learning_state,
)
from signal_arcade.models import (
    LearningEvidenceLane,
    LearningEvidenceStatus,
    LearningObservationStatus,
    Position,
    RiskMode,
)
from signal_arcade.orchestrator import Orchestrator
from signal_arcade.paper.curve_math import quote_sell
from signal_arcade.providers.anchor import AnchorEventDecoder
from signal_arcade.providers.http import SPL_TOKEN_PROGRAM, TOKEN_2022_PROGRAM
from signal_arcade.providers.solana import PUMP_AMM_PROGRAM, PUMP_PROGRAM
from solders.pubkey import Pubkey

IDL_DIR = Path(__file__).resolve().parents[1] / "backend/signal_arcade/resources/idl"


def anchor_account(venue: str, name: str, values: dict) -> bytes:
    idl = json.loads((IDL_DIR / f"{venue}.json").read_text())
    definitions = {item["name"]: item["type"] for item in idl["types"]}

    def encode(spec, value=None):
        if isinstance(spec, str):
            if spec == "pubkey":
                return bytes(Pubkey.from_string(value or NATIVE_SOL_MINT))
            if spec == "bool":
                return bytes([bool(value)])
            return int(value or 0).to_bytes(int(spec[1:]) // 8, "little", signed=spec[0] == "i")
        if "defined" in spec:
            definition = definitions[spec["defined"]["name"]]
            return b"".join(
                encode(field["type"], (value or {}).get(field["name"]))
                for field in definition["fields"]
            )
        if "vec" in spec:
            return struct.pack("<I", len(value or [])) + b"".join(
                encode(spec["vec"], item) for item in (value or [])
            )
        if "array" in spec:
            return b"".join(
                encode(spec["array"][0], item) for item in (value or [None] * spec["array"][1])
            )
        raise AssertionError(spec)

    discriminator = bytes(
        next(item for item in idl["accounts"] if item["name"] == name)["discriminator"]
    )
    return discriminator + encode({"defined": {"name": name}}, values)


def safe_mint(owner=SPL_TOKEN_PROGRAM):
    raw = bytearray(82)
    struct.pack_into("<Q", raw, 36, 1_000_000_000_000_000)
    raw[44:46] = bytes([6, 1])
    return {"owner": owner, "raw": bytes(raw)}


def vault(mint: str, authority: str, amount: int, *, frozen=False):
    raw = bytearray(165)
    raw[:32] = bytes(Pubkey.from_string(mint))
    raw[32:64] = bytes(Pubkey.from_string(authority))
    struct.pack_into("<Q", raw, 64, amount)
    raw[108] = 2 if frozen else 1
    return {"owner": SPL_TOKEN_PROGRAM, "raw": bytes(raw)}


def route_fixture(venue="pump_curve", seed=43):
    now = datetime.now(UTC)
    mint = str(Pubkey.from_bytes(bytes([seed]) * 32))
    creator = str(Pubkey.from_bytes(bytes([44]) * 32))
    state = TokenState(
        mint=mint,
        last_slot=100,
        last_event_id="old-trade",
        last_event_at=now - timedelta(minutes=5),
        venue=venue,
    )
    state.curve_address = pda(PUMP_PROGRAM, b"bonding-curve", bytes(Pubkey.from_string(mint)))
    program = PUMP_PROGRAM if venue == "pump_curve" else PUMP_AMM_PROGRAM
    namespace = "pump" if venue == "pump_curve" else "pump_amm"
    fees = {"lp_fee_bps": 3, "protocol_fee_bps": 5, "creator_fee_bps": 7}
    fee_values = {
        "flat_fees": fees,
        "fee_tiers": [
            {"market_cap_lamports_threshold": 0, "fees": fees},
            {
                "market_cap_lamports_threshold": 1_000_000_000_000,
                "fees": {"lp_fee_bps": 4, "protocol_fee_bps": 6, "creator_fee_bps": 8},
            },
        ],
    }
    accounts = {mint: safe_mint()}
    fee_address = pda(FEE_PROGRAM, b"fee_config", bytes(Pubkey.from_string(program)))
    accounts[fee_address] = {
        "owner": FEE_PROGRAM,
        "raw": anchor_account(namespace, "FeeConfig", fee_values),
    }
    global_address = pda(program, b"global" if venue == "pump_curve" else b"global_config")
    accounts[global_address] = {
        "owner": program,
        "raw": anchor_account(
            namespace,
            "Global" if venue == "pump_curve" else "GlobalConfig",
            {},
        ),
    }
    if venue == "pump_curve":
        values = {
            "virtual_token_reserves": 1_000_000_000_000_000,
            "virtual_quote_reserves": 30_000_000_000,
            "real_token_reserves": 500_000_000_000_000,
            "real_quote_reserves": 20_000_000_000,
            "token_total_supply": 1_000_000_000_000_000,
            "creator": creator,
            "quote_mint": NATIVE_SOL_MINT,
        }
        accounts[state.curve_address] = {
            "owner": program,
            "raw": anchor_account(namespace, "BondingCurve", values),
        }
    else:
        state.pool_address = pda(
            program,
            b"pool",
            b"\0\0",
            bytes(Pubkey.from_string(creator)),
            bytes(Pubkey.from_string(mint)),
            bytes(Pubkey.from_string(WRAPPED_SOL_MINT)),
        )
        state.pool_base_token_account = pda(program, b"test-base", bytes(Pubkey.from_string(mint)))
        state.pool_quote_token_account = pda(
            program, b"test-quote", bytes(Pubkey.from_string(mint))
        )
        values = {
            "creator": creator,
            "coin_creator": creator,
            "base_mint": mint,
            "quote_mint": WRAPPED_SOL_MINT,
            "pool_base_token_account": state.pool_base_token_account,
            "pool_quote_token_account": state.pool_quote_token_account,
        }
        accounts[state.pool_address] = {
            "owner": program,
            "raw": anchor_account(namespace, "Pool", values),
        }
        accounts[state.pool_base_token_account] = vault(mint, state.pool_address, 10**15)
        accounts[state.pool_quote_token_account] = vault(
            WRAPPED_SOL_MINT, state.pool_address, 30 * 10**9
        )
    decoder = AnchorEventDecoder([IDL_DIR / "pump.json", IDL_DIR / "pump_amm.json"])
    return state, {"slot": 101, "accounts": accounts}, decoder, now


@pytest.mark.parametrize("venue", ["pump_curve", "pump_swap"])
def test_validated_snapshot_preserves_live_state_and_has_account_provenance(venue):
    state, result, decoder, now = route_fixture(venue)
    before = copy.deepcopy(state)
    refreshed = validated_learning_state(state, result, decoder, requested_at=now, observed_at=now)
    assert state == before
    assert refreshed is not state
    assert refreshed.last_event_at == before.last_event_at
    assert refreshed.reserve_source == "solana-rpc-learning"
    assert refreshed.fee_bps == (12 if venue == "pump_curve" else 15)
    assert refreshed.reserve_audit["slot"] == 101
    assert len(refreshed.reserve_audit["accounts"]) == len(reserve_addresses(state))
    assert all(len(item["sha256"]) == 64 for item in refreshed.reserve_audit["accounts"])


def test_verified_empty_pool_requires_repeated_proof_and_revival_clears_it(settings, monkeypatch):
    engine = Orchestrator(settings)
    state, healthy, _decoder, now = route_fixture("pump_swap")
    engine.features.tokens[state.mint] = state
    engine.broker.positions[state.mint] = Position(
        position_id="held",
        mint=state.mint,
        symbol="TEST",
        token_units=10**12,
        entry_cost_lamports=10**6,
        book_value_lamports=10**6,
        opened_at=now - timedelta(hours=2),
        entry_fill_id="fill",
        last_marked_at=now - timedelta(minutes=5),
        mark_is_stale=True,
    )
    monkeypatch.setattr(engine, "_rollover_market_data_healthy", lambda _: True)
    empty = copy.deepcopy(healthy)
    empty["accounts"][state.pool_quote_token_account] = vault(
        WRAPPED_SOL_MINT, state.pool_address, 0
    )
    with pytest.raises(ReserveRefreshRejected, match="no_executable_reserves"):
        validated_learning_state(
            state, empty, engine.solana.decoder, requested_at=now, observed_at=now
        )
    targets = engine._position_watchdog_targets()[0]
    for index in range(2):
        empty["slot"] = 101 + index
        at = now + timedelta(seconds=8 * index)
        _, refreshed, _ = engine._apply_position_watchdog_result(targets, empty, at)
        assert refreshed == {state.mint}
        dispositions, _ = engine._terminal_position_dispositions(
            engine.broker.snapshot(RiskMode.BALANCED, persist_peak=False), at
        )
        assert dispositions[state.mint]["terminal_disposition"] == (
            "unknown" if index == 0 else "write_off"
        )
    # A malformed response breaks the chain; another valid empty response must start again.
    invalid = copy.deepcopy(empty)
    invalid["slot"] = 103
    invalid["accounts"][state.pool_address]["owner"] = SPL_TOKEN_PROGRAM
    engine._apply_position_watchdog_result(targets, invalid, now + timedelta(seconds=16))
    assert engine._position_route_probes[state.mint]["consecutive"] == 0
    empty["slot"] = 104
    engine._apply_position_watchdog_result(targets, empty, now + timedelta(seconds=24))
    assert engine._position_route_probes[state.mint]["consecutive"] == 1
    healthy["slot"] = 105
    engine._apply_position_watchdog_result(targets, healthy, now + timedelta(seconds=32))
    assert engine._position_route_probes[state.mint]["outcome"] == "available"
    assert engine.broker.positions[state.mint].mark_is_executable
    assert state.last_event_at == now - timedelta(minutes=5)
    asyncio.run(engine.http.close())
    engine.database.close()


@pytest.mark.parametrize(
    "failure",
    [
        "owner",
        "mint",
        "truncated",
        "old_slot",
        "future",
        "late",
        "pda",
        "fee_owner",
        "fee_extension",
    ],
)
def test_invalid_snapshot_cannot_produce_fresh_reserves(failure):
    state, result, decoder, now = route_fixture()
    observed = now
    if failure == "owner":
        result["accounts"][state.curve_address]["owner"] = SPL_TOKEN_PROGRAM
    elif failure == "mint":
        result["accounts"][state.mint]["raw"] = bytes(82)
    elif failure == "truncated":
        result["accounts"][state.curve_address]["raw"] = b"short"
    elif failure == "old_slot":
        result["slot"] = 99
    elif failure == "future":
        state.last_reserve_at = now + timedelta(seconds=1)
    elif failure == "late":
        observed = now + timedelta(seconds=9)
    elif failure == "pda":
        state.curve_address = state.mint
    elif failure == "fee_owner":
        result["accounts"][reserve_addresses(state)[1]]["owner"] = PUMP_PROGRAM
    else:
        result["accounts"][reserve_addresses(state)[1]]["raw"] += b"unreviewed"
    before = copy.deepcopy(state)
    with pytest.raises(ReserveRefreshRejected):
        validated_learning_state(state, result, decoder, requested_at=now, observed_at=observed)
    assert state == before


@pytest.mark.parametrize("failure", ["frozen", "authority", "mint", "extension", "mapping"])
def test_pool_vaults_fail_closed(failure):
    state, result, decoder, now = route_fixture("pump_swap")
    account = result["accounts"][state.pool_base_token_account]
    raw = bytearray(account["raw"])
    if failure == "frozen":
        raw[108] = 2
    elif failure == "authority":
        raw[32:64] = bytes(32)
    elif failure == "mint":
        raw[:32] = bytes(32)
    elif failure == "extension":
        account["owner"] = TOKEN_2022_PROGRAM
        result["accounts"][state.mint] = safe_mint(TOKEN_2022_PROGRAM)
        raw.extend(bytes([2]) + struct.pack("<HH", 8, 0))
    else:
        state.pool_base_token_account = state.pool_quote_token_account
    account["raw"] = bytes(raw)
    with pytest.raises(ReserveRefreshRejected):
        validated_learning_state(state, result, decoder, requested_at=now, observed_at=now)


def test_component_fees_round_individually_and_lp_liquidity_is_not_fabricated():
    quote = quote_sell(
        virtual_token_reserves=1000,
        virtual_sol_reserves=2000,
        token_units=1000,
        fee_bps=15,
        fee_components=(3, 5, 7),
        network_fee_lamports=0,
        real_quote_reserves=999,
        lp_fee_bps=3,
    )
    assert quote.curve_sol_lamports == 1000
    assert quote.protocol_fee_lamports == 3  # ceil(0.3) + ceil(0.5) + ceil(0.7)
    assert quote.wallet_sol_lamports == 997
    with pytest.raises(ValueError, match="real quote"):
        quote_sell(
            virtual_token_reserves=1000,
            virtual_sol_reserves=2000,
            token_units=1000,
            fee_bps=15,
            fee_components=(3, 5, 7),
            network_fee_lamports=0,
            real_quote_reserves=998,
            lp_fee_bps=3,
        )


def scheduler_fixture():
    now = datetime.now(UTC)
    states = {
        f"{lane}-{i}": TokenState(
            mint=f"{lane}-{i}",
            last_reserve_at=now,
            virtual_token_reserves=10**15,
            virtual_quote_reserves=10**10,
        )
        for lane in ("policy", "discovery")
        for i in range(24)
    }
    engine = NS(
        settings=NS(stale_market_seconds=20),
        observations={
            mint: NS(
                mint=mint,
                created_at=now - timedelta(seconds=65),
                status=LearningObservationStatus.PENDING,
                checkpoints={},
            )
            for mint in states
            if mint.startswith("discovery")
        },
        evidence_episodes={
            mint: NS(
                mint=mint,
                entry_at=now - timedelta(seconds=65),
                status=LearningEvidenceStatus.PENDING,
                lane=LearningEvidenceLane.POLICY,
                checkpoints={},
            )
            for mint in states
            if mint.startswith("policy")
        },
        _checkpoint_served={"cache": {}, "rpc": {}},
        _checkpoint_turn={"cache": 0, "rpc": 0},
    )
    return engine, states, now


def test_cached_policy_is_not_starved_by_stale_discovery():
    engine, states, now = scheduler_fixture()
    for mint, state in states.items():
        if mint.startswith("discovery"):
            state.last_reserve_at = now - timedelta(minutes=5)
    chosen = LearningEngine.due_checkpoint_mints(engine, states, now, limit=20, fresh=True)
    assert len(chosen) == 20
    assert all(mint.startswith("policy") for mint in chosen)


def test_rpc_scheduler_reserves_discovery_share_and_rotates_failures():
    engine, states, now = scheduler_fixture()
    for state in states.values():
        state.last_reserve_at = now - timedelta(minutes=5)
    chosen = [
        LearningEngine.due_checkpoint_mints(engine, states, now, limit=1, fresh=False)[0]
        for _ in range(16)
    ]
    assert sum(mint.startswith("discovery") for mint in chosen) == 4
    assert len(set(chosen)) == 16
    assert not LearningEngine.due_checkpoint_mints(
        engine,
        states,
        now + timedelta(seconds=90),
        limit=20,
        fresh=False,
    )


def test_result_cannot_cross_a_route_change(settings):
    engine = Orchestrator(settings)
    state, result, _decoder, now = route_fixture()
    engine.features.tokens[state.mint] = state
    snapshot = copy.copy(state)
    state.venue = "pump_swap"
    engine._apply_learning_reserve_result({state.mint: snapshot}, {state.mint: state}, result, now)
    assert engine._learning_refresh_status["accepted_routes"] == 0
    assert engine._learning_refresh_status["rejected"]["route_changed_during_request"] == 1
    asyncio.run(engine.http.close())
    engine.database.close()


def test_background_batch_is_bounded_disabled_by_default_and_isolates_future_slot(
    settings, monkeypatch
):
    engine = Orchestrator(settings)
    engine.demo_mode = False
    monkeypatch.setattr(engine, "_rollover_market_data_healthy", lambda _: True)
    response = {"slot": 101, "accounts": {}}
    for seed in range(50, 70):
        state, fixture, _decoder, _now = route_fixture("pump_swap", seed=seed)
        engine.features.tokens[state.mint] = state
        response["accounts"].update(fixture["accounts"])
    originals = copy.deepcopy(engine.features.tokens)
    mints = list(originals)
    engine.features.tokens[mints[0]].last_slot = 999_999_999
    calls, accepted = [], []
    monkeypatch.setattr(engine.learning, "due_checkpoint_mints", lambda *a, **kw: mints)
    monkeypatch.setattr(
        engine.learning, "observe_market", lambda state, *a, **kw: accepted.append(state) or 1
    )

    async def fetch(addresses, **kwargs):
        calls.append((addresses, kwargs))
        return response

    monkeypatch.setattr(engine.http, "solana_multiple_accounts", fetch)
    asyncio.run(engine._learning_reserve_tick())
    assert not calls
    settings.learning_reserve_refresh_enabled = True
    asyncio.run(engine._learning_reserve_tick())
    assert len(calls) == 1
    assert len(calls[0][0]) == 82
    assert calls[0][1] == {"min_context_slot": 100, "critical": False}
    assert len(accepted) == 19
    assert all(state.reserve_audit["slot"] == 101 for state in accepted)
    for mint in mints[1:]:
        assert engine.features.tokens[mint] == originals[mint]
    engine._event_batches_in_flight = 1
    engine.last_processing_lag_seconds = 2
    asyncio.run(engine._learning_reserve_tick())
    assert len(calls) == 1
    asyncio.run(engine.http.close())
    engine.database.close()
