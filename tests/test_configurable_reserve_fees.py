"""Fee rules from pump-rust-client 0.1.13, including venue-specific Mayhem supply."""

import copy
import struct

import pytest
from signal_arcade.intelligence.features import NATIVE_SOL_MINT, WRAPPED_SOL_MINT
from signal_arcade.intelligence.reserve_refresh import (
    ReserveRefreshRejected,
    pda,
    reserve_addresses,
    validated_learning_state,
)
from signal_arcade.paper.curve_math import quote_sell
from signal_arcade.providers.solana import PUMP_AMM_PROGRAM, PUMP_PROGRAM
from solders.pubkey import Pubkey
from test_v1104_refresh import anchor_account, route_fixture, vault


def configured_route(
    venue="pump_curve",
    *,
    gate=True,
    rate=75,
    can_edit=False,
    max_rate=100,
    canonical=True,
    mayhem=False,
    has_creator=True,
    seed=43,
):
    state, response, decoder, now = route_fixture(venue, seed=seed)
    namespace = "pump" if venue == "pump_curve" else "pump_amm"
    program = PUMP_PROGRAM if venue == "pump_curve" else PUMP_AMM_PROGRAM
    accounts = response["accounts"]
    global_address = reserve_addresses(state)[2]
    accounts[global_address]["raw"] += struct.pack("<BQ", gate, max_rate)
    address = state.curve_address if venue == "pump_curve" else state.pool_address
    account = accounts.pop(address)
    name = "BondingCurve" if venue == "pump_curve" else "Pool"
    values = decoder.decode_account(account["raw"], expected_program=program)[2]
    values["is_mayhem_mode"] = mayhem
    if not has_creator:
        values["creator" if venue == "pump_curve" else "coin_creator"] = NATIVE_SOL_MINT
    if venue == "pump_swap" and canonical:
        values["creator"] = pda(
            PUMP_PROGRAM, b"pool-authority", bytes(Pubkey.from_string(state.mint))
        )
        address = pda(
            program,
            b"pool",
            b"\0\0",
            bytes(Pubkey.from_string(values["creator"])),
            bytes(Pubkey.from_string(state.mint)),
            bytes(Pubkey.from_string(WRAPPED_SOL_MINT)),
        )
        state.pool_address = address
        accounts[state.pool_base_token_account] = vault(state.mint, address, 10**15)
        accounts[state.pool_quote_token_account] = vault(WRAPPED_SOL_MINT, address, 30 * 10**9)
    account["raw"] = anchor_account(namespace, name, values) + struct.pack("<QB", rate, can_edit)
    accounts[address] = account
    return state, response, decoder, now


@pytest.mark.parametrize("venue", ["pump_curve", "pump_swap"])
@pytest.mark.parametrize("gate,rate,expected", [(True, 75, 75), (False, 75, 7), (True, 0, 7)])
@pytest.mark.parametrize("can_edit", [False, True])
def test_creator_override_uses_global_gate_and_nonzero_stored_rate(
    venue, gate, rate, expected, can_edit
):
    state, response, decoder, now = configured_route(
        venue, gate=gate, rate=rate, can_edit=can_edit, max_rate=50
    )
    before = copy.deepcopy(state)
    result = validated_learning_state(state, response, decoder, requested_at=now, observed_at=now)
    assert result.reserve_fee_components == (0 if venue == "pump_curve" else 3, 5, expected)
    # max_configurable_creator_fee_bps restricts setting a fee; it is not a trade-time
    # clamp. can_edit_creator_fee controls editing, not whether an existing rate applies.
    assert state == before
    assert result.reserve_audit["fee_recipe"] == "pump-rust-client-0.1.13"


@pytest.mark.parametrize("venue", ["pump_curve", "pump_swap"])
def test_missing_creator_never_charges_the_configured_creator_fee(venue):
    state, response, decoder, now = configured_route(venue, has_creator=False)
    result = validated_learning_state(state, response, decoder, requested_at=now, observed_at=now)
    assert result.reserve_fee_components == (0 if venue == "pump_curve" else 3, 5, 0)


@pytest.mark.parametrize("canonical", [False, True])
def test_noncanonical_pool_keeps_flat_fees_and_still_applies_creator_override(canonical):
    state, response, decoder, now = configured_route("pump_swap", canonical=canonical)
    accounts = response["accounts"]
    fees = reserve_addresses(state)[1]
    values = decoder.decode_account(accounts[fees]["raw"], expected_program=PUMP_AMM_PROGRAM)[2]
    values["flat_fees"] = {"lp_fee_bps": 21, "protocol_fee_bps": 11, "creator_fee_bps": 9}
    # Non-SOL schedules must not accidentally change supported SOL pool fees.
    accounts[fees]["raw"] = anchor_account("pump_amm", "FeeConfig", values) + struct.pack(
        "<QQQ", 101, 201, 301
    )
    result = validated_learning_state(state, response, decoder, requested_at=now, observed_at=now)
    assert result.reserve_fee_components == ((3, 5, 75) if canonical else (21, 11, 75))


@pytest.mark.parametrize(
    "venue,mayhem,fixed",
    [
        ("pump_curve", False, True),
        ("pump_curve", True, False),
        ("pump_swap", False, False),
        ("pump_swap", True, True),
    ],
)
def test_burned_supply_selects_the_correct_tier_for_each_venue(venue, mayhem, fixed):
    state, response, decoder, now = configured_route(venue, mayhem=mayhem, rate=0)
    accounts = response["accounts"]
    mint = bytearray(accounts[state.mint]["raw"])
    struct.pack_into("<Q", mint, 36, 4 * 10**14)
    accounts[state.mint]["raw"] = bytes(mint)
    program = PUMP_PROGRAM if venue == "pump_curve" else PUMP_AMM_PROGRAM
    namespace = "pump" if venue == "pump_curve" else "pump_amm"
    threshold = 20 * 10**9
    if venue == "pump_swap":
        accounts[state.pool_base_token_account] = vault(state.mint, state.pool_address, 10**14)
        threshold *= 10
    fees = reserve_addresses(state)[1]
    values = decoder.decode_account(accounts[fees]["raw"], expected_program=program)[2]
    values["fee_tiers"][1]["market_cap_lamports_threshold"] = threshold
    accounts[fees]["raw"] = anchor_account(namespace, "FeeConfig", values)
    result = validated_learning_state(state, response, decoder, requested_at=now, observed_at=now)
    assert result.reserve_audit["fee_supply"] == (10**15 if fixed else 4 * 10**14)
    assert result.reserve_audit["fee_supply_source"] == (
        "fixed_billion" if fixed else "verified_mint"
    )
    assert result.reserve_fee_components == (
        0 if venue == "pump_curve" else (4 if fixed else 3),
        6 if fixed else 5,
        8 if fixed else 7,
    )


@pytest.mark.parametrize("venue", ["pump_curve", "pump_swap"])
@pytest.mark.parametrize("rate", [9996, 10_000, 2**64 - 1])
def test_unsafe_effective_fee_is_rejected_without_changing_live_state(venue, rate):
    state, response, decoder, now = configured_route(venue, rate=rate)
    before = copy.deepcopy(state)
    with pytest.raises(ReserveRefreshRejected, match="invalid_fee_rates"):
        validated_learning_state(state, response, decoder, requested_at=now, observed_at=now)
    assert state == before


@pytest.mark.parametrize("venue", ["pump_curve", "pump_swap"])
@pytest.mark.parametrize("total", [9999, 10_000])
def test_effective_fee_limit_is_exclusive_and_does_not_mutate_the_input(venue, total):
    # A curve charges protocol 5bps; this pool also charges LP 3bps.
    rate = total - (5 if venue == "pump_curve" else 8)
    state, response, decoder, now = configured_route(venue, rate=rate)
    before = copy.deepcopy(state)
    if total == 10_000:
        with pytest.raises(ReserveRefreshRejected, match="invalid_fee_rates"):
            validated_learning_state(state, response, decoder, requested_at=now, observed_at=now)
    else:
        refreshed = validated_learning_state(
            state, response, decoder, requested_at=now, observed_at=now
        )
        assert refreshed.fee_bps == 9999
    assert state == before


@pytest.mark.parametrize("venue", ["pump_curve", "pump_swap"])
@pytest.mark.parametrize("gate,has_creator", [(False, True), (True, False)])
def test_inapplicable_stored_rate_cannot_change_effective_fees(venue, gate, has_creator):
    state, response, decoder, now = configured_route(
        venue, gate=gate, has_creator=has_creator, rate=2**64 - 1
    )
    before = copy.deepcopy(state)
    refreshed = validated_learning_state(
        state, response, decoder, requested_at=now, observed_at=now
    )
    assert refreshed.reserve_fee_components == (
        0 if venue == "pump_curve" else 3,
        5,
        7 if has_creator else 0,
    )
    assert state == before


@pytest.mark.parametrize("venue", ["pump_curve", "pump_swap"])
@pytest.mark.parametrize("mayhem", [False, True])
def test_fixed_supply_never_masks_an_invalid_mint_supply(venue, mayhem):
    state, response, decoder, now = configured_route(venue, mayhem=mayhem)
    mint = bytearray(response["accounts"][state.mint]["raw"])
    struct.pack_into("<Q", mint, 36, 0)
    response["accounts"][state.mint]["raw"] = bytes(mint)
    # The existing verified-mint boundary rejects this before fee selection.
    with pytest.raises(ReserveRefreshRejected, match="mint_not_verified_safe"):
        validated_learning_state(state, response, decoder, requested_at=now, observed_at=now)


@pytest.mark.parametrize(
    "venue,expected_fee,expected_net",
    [
        ("pump_curve", 239762, 29725267),
        ("pump_swap", 248754, 29716275),
    ],
)
def test_configured_fee_sell_keeps_component_rounding_and_network_cost(
    venue, expected_fee, expected_net
):
    # Reference equation: floor(30e9 * 1e12 / (1e15 + 1e12)) = 29,970,029 gross.
    # Independently ceil protocol 5bps, creator 75bps, and AMM LP 3bps. Then subtract
    # the original 5,000-lamport network cost. See official math/fees.rs and amm.rs.
    state, response, decoder, now = configured_route(venue)
    result = validated_learning_state(state, response, decoder, requested_at=now, observed_at=now)
    quote = quote_sell(
        virtual_token_reserves=result.virtual_token_reserves,
        virtual_sol_reserves=result.virtual_quote_reserves,
        real_quote_reserves=result.real_quote_reserves,
        token_units=10**12,
        fee_bps=result.fee_bps,
        fee_components=result.reserve_fee_components,
        lp_fee_bps=result.reserve_lp_fee_bps,
        network_fee_lamports=5000,
    )
    assert quote.curve_sol_lamports == 29970029
    assert quote.protocol_fee_lamports == expected_fee
    assert quote.wallet_sol_lamports == expected_net
