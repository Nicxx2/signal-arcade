"""Pure validation of learning-only account snapshots; no live market state is changed."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import replace
from datetime import datetime
from typing import Any

from solders.pubkey import Pubkey

from ..providers.anchor import AnchorEventDecoder
from ..providers.http import SPL_TOKEN_PROGRAM, TOKEN_2022_PROGRAM, HttpProviders
from ..providers.solana import PUMP_AMM_PROGRAM, PUMP_PROGRAM, SolanaLogProvider
from .features import NATIVE_SOL_MINT, WRAPPED_SOL_MINT, TokenState

FEE_PROGRAM = "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"
RESERVE_PROOF_VERSION = "learning-account-snapshot-v1"


class ReserveRefreshRejected(ValueError):
    pass


def pda(program: str, *seeds: bytes) -> str:
    return str(Pubkey.find_program_address(list(seeds), Pubkey.from_string(program))[0])


def route_identity(state: TokenState) -> tuple[str, ...]:
    return (
        state.mint,
        state.venue,
        state.curve_address,
        state.pool_address,
        state.pool_base_token_account,
        state.pool_quote_token_account,
        state.quote_mint,
    )


def reserve_addresses(state: TokenState) -> list[str]:
    program = PUMP_PROGRAM if state.venue == "pump_curve" else PUMP_AMM_PROGRAM
    if state.venue not in {"pump_curve", "pump_swap"}:
        raise ReserveRefreshRejected("unsupported_venue")
    addresses = [
        state.mint,
        pda(FEE_PROGRAM, b"fee_config", bytes(Pubkey.from_string(program))),
        pda(program, b"global" if state.venue == "pump_curve" else b"global_config"),
    ]
    if state.venue == "pump_curve":
        curve = pda(PUMP_PROGRAM, b"bonding-curve", bytes(Pubkey.from_string(state.mint)))
        if curve != state.curve_address:
            raise ReserveRefreshRejected("curve_pda_mismatch")
        addresses.append(curve)
    else:
        addresses.extend(
            [
                state.pool_address,
                state.pool_base_token_account,
                state.pool_quote_token_account,
            ]
        )
    for address in addresses:
        Pubkey.from_string(address)
    return addresses


def _account(accounts: dict[str, Any], address: str, owner: str) -> dict[str, Any]:
    account = accounts.get(address)
    if not isinstance(account, dict) or account.get("owner") != owner:
        raise ReserveRefreshRejected("missing_account_or_wrong_owner")
    if not isinstance(account.get("raw"), bytes) or account.get("executable", False):
        raise ReserveRefreshRejected("invalid_account_data")
    return account


def _decoded(
    decoder: AnchorEventDecoder,
    account: dict[str, Any],
    program: str,
    name: str,
) -> dict[str, Any]:
    result = decoder.decode_account(account["raw"], expected_program=program, expected_name=name)
    if result is None:
        raise ReserveRefreshRejected("unsupported_account_layout")
    values = result[2]
    remaining = int(values.get("_remaining_bytes", 0))
    if remaining and any(account["raw"][-remaining:]):
        raise ReserveRefreshRejected("unreviewed_account_extension")
    return values


def _vault(account: dict[str, Any], mint: str, authority: str) -> int:
    raw = account["raw"]
    if account["owner"] == SPL_TOKEN_PROGRAM:
        if len(raw) != 165:
            raise ReserveRefreshRejected("unsupported_vault_layout")
    elif account["owner"] == TOKEN_2022_PROGRAM:
        # The only supported account extension is ImmutableOwner (type 7, length 0).
        if len(raw) > 165:
            if raw[165] != 2:
                raise ReserveRefreshRejected("unsupported_vault_layout")
            offset = 166
            seen: set[int] = set()
            while offset < len(raw) and any(raw[offset:]):
                if offset + 4 > len(raw):
                    raise ReserveRefreshRejected("malformed_vault_extension")
                kind, length = struct.unpack_from("<HH", raw, offset)
                if kind != 7 or length != 0 or kind in seen:
                    raise ReserveRefreshRejected("unreviewed_vault_extension")
                seen.add(kind)
                offset += 4
    else:
        raise ReserveRefreshRejected("unsupported_token_program")
    values = SolanaLogProvider.decode_token_account(raw)
    if (
        values is None
        or values["state"] != 1
        or values["mint"] != mint
        or values["authority"] != authority
    ):
        raise ReserveRefreshRejected("vault_mapping_or_state_invalid")
    return int(values["amount"])


def _fees(config: dict[str, Any], market_cap: int, canonical: bool) -> dict[str, int]:
    selected = config.get("flat_fees")
    if canonical:
        tiers = config.get("fee_tiers")
        if not isinstance(tiers, list) or not 1 <= len(tiers) <= 128:
            raise ReserveRefreshRejected("invalid_fee_tiers")
        thresholds = [int(tier["market_cap_lamports_threshold"]) for tier in tiers]
        if thresholds != sorted(set(thresholds)) or thresholds[0] < 0:
            raise ReserveRefreshRejected("unordered_fee_tiers")
        selected = tiers[0]["fees"]
        for tier, threshold in zip(tiers, thresholds, strict=True):
            if threshold <= market_cap:
                selected = tier["fees"]
    if not isinstance(selected, dict):
        raise ReserveRefreshRejected("missing_fees")
    result = {
        key: int(selected[key])
        for key in (
            "lp_fee_bps",
            "protocol_fee_bps",
            "creator_fee_bps",
        )
    }
    if any(value < 0 for value in result.values()) or sum(result.values()) >= 10_000:
        raise ReserveRefreshRejected("invalid_fee_rates")
    return result


def validated_learning_state(
    original: TokenState,
    result: dict[str, Any],
    decoder: AnchorEventDecoder,
    *,
    requested_at: datetime,
    observed_at: datetime,
    allow_empty: bool = False,
) -> TokenState:
    """Return a separate reserve view after validating the entire same-slot account set."""
    slot = int(result.get("slot") or 0)
    if (
        slot <= 0
        or slot < max(original.last_slot, original.last_reserve_slot)
        or not 0 <= (observed_at - requested_at).total_seconds() <= 8
        or any(
            at is not None and at > observed_at
            for at in (
                original.last_event_at,
                original.last_reserve_at,
            )
        )
    ):
        raise ReserveRefreshRejected("stale_slot_or_timestamp")
    accounts = result.get("accounts")
    if not isinstance(accounts, dict):
        raise ReserveRefreshRejected("missing_accounts")
    addresses = reserve_addresses(original)
    mint_account = accounts.get(original.mint)
    safety = HttpProviders.mint_safety_from_account(mint_account)
    if not safety or not safety.get("safe") or not safety.get("verified"):
        raise ReserveRefreshRejected("mint_not_verified_safe")
    _account(accounts, original.mint, safety["owner"])
    program = PUMP_PROGRAM if original.venue == "pump_curve" else PUMP_AMM_PROGRAM
    fee_account = _account(accounts, addresses[1], FEE_PROGRAM)
    fee_config = _decoded(decoder, fee_account, program, "FeeConfig")
    global_values = _decoded(
        decoder,
        _account(accounts, addresses[2], program),
        program,
        "Global" if original.venue == "pump_curve" else "GlobalConfig",
    )
    state = replace(original)
    creator: str
    canonical = True
    mayhem = False
    if original.venue == "pump_curve":
        curve = _decoded(
            decoder,
            _account(accounts, original.curve_address, program),
            program,
            "BondingCurve",
        )
        if curve["complete"]:
            raise ReserveRefreshRejected("curve_migrated")
        if curve.get("quote_mint") not in {NATIVE_SOL_MINT, WRAPPED_SOL_MINT}:
            raise ReserveRefreshRejected("unsupported_quote_mint")
        mayhem = bool(curve.get("is_mayhem_mode"))
        state.virtual_token_reserves = int(curve["virtual_token_reserves"])
        state.virtual_quote_reserves = int(curve["virtual_quote_reserves"])
        state.real_token_reserves = int(curve["real_token_reserves"])
        state.real_quote_reserves = int(curve["real_quote_reserves"])
        creator = str(curve["creator"])
        # pump-sdk 1.36.0 getFee(): Mayhem uses the current mint-account supply,
        # not the curve's original token_total_supply (burns can change it).
        # The verified mint is in the same RPC account batch as these reserves.
        fee_supply = int(safety["supply"]) if mayhem else 1_000_000_000_000_000
        state.reserve_lp_fee_bps = 0
    else:
        pool = _decoded(
            decoder,
            _account(accounts, original.pool_address, program),
            program,
            "Pool",
        )
        mayhem = bool(pool.get("is_mayhem_mode"))
        if pool["base_mint"] != original.mint or pool["quote_mint"] != WRAPPED_SOL_MINT:
            raise ReserveRefreshRejected("pool_mint_mismatch")
        expected_pool = pda(
            program,
            b"pool",
            int(pool["index"]).to_bytes(2, "little"),
            bytes(Pubkey.from_string(pool["creator"])),
            bytes(Pubkey.from_string(original.mint)),
            bytes(Pubkey.from_string(WRAPPED_SOL_MINT)),
        )
        if expected_pool != original.pool_address:
            raise ReserveRefreshRejected("pool_pda_mismatch")
        if (
            pool["pool_base_token_account"] != original.pool_base_token_account
            or pool["pool_quote_token_account"] != original.pool_quote_token_account
        ):
            raise ReserveRefreshRejected("pool_vault_mapping_changed")
        if int(global_values["disable_flags"]) & 16:
            raise ReserveRefreshRejected("pool_sells_disabled")
        base = _vault(
            _account(accounts, original.pool_base_token_account, safety["owner"]),
            original.mint,
            original.pool_address,
        )
        quote = _vault(
            _account(accounts, original.pool_quote_token_account, SPL_TOKEN_PROGRAM),
            WRAPPED_SOL_MINT,
            original.pool_address,
        )
        virtual_quote = int(pool.get("virtual_quote_reserves", 0))
        if virtual_quote < 0:
            raise ReserveRefreshRejected("unsupported_negative_virtual_reserves")
        state.virtual_token_reserves = state.real_token_reserves = base
        state.virtual_quote_reserves = quote + virtual_quote
        state.real_quote_reserves = quote
        # Migration/restart logs may retain the curve's native-SOL marker. The exact
        # Pool and quote vault above prove this identity; never mark an old quote verified.
        state.quote_mint = str(pool["quote_mint"])
        state.route_verified = True
        creator = str(pool["coin_creator"])
        canonical = pool["creator"] == pda(
            PUMP_PROGRAM,
            b"pool-authority",
            bytes(Pubkey.from_string(original.mint)),
        )
        fee_supply = int(safety["supply"])
    if not 0 < fee_supply <= 2**64 - 1:
        raise ReserveRefreshRejected("invalid_fee_supply")
    if state.real_quote_reserves < 0 or state.real_token_reserves < 0:
        raise ReserveRefreshRejected("invalid_real_reserves")
    empty = state.virtual_token_reserves == 0 or state.virtual_quote_reserves == 0
    if empty and not allow_empty:
        raise ReserveRefreshRejected("no_executable_reserves")
    market_cap = (
        state.virtual_quote_reserves * fee_supply // state.virtual_token_reserves
        if not empty
        else None
    )
    fees = _fees(fee_config, market_cap or 0, canonical)
    state.reserve_lp_fee_bps = fees["lp_fee_bps"] if original.venue == "pump_swap" else 0
    state.reserve_fee_components = (
        state.reserve_lp_fee_bps,
        fees["protocol_fee_bps"],
        fees["creator_fee_bps"] if creator != NATIVE_SOL_MINT else 0,
    )
    state.fee_bps = sum(state.reserve_fee_components)
    if empty:
        # No pricing claim is made for an empty route. Only the watchdog may use this
        # fully validated state as evidence of current non-executability.
        state.reserve_fee_components = None
        state.reserve_lp_fee_bps = 0
        state.fee_bps = 0
    state.last_reserve_at = observed_at
    state.last_reserve_slot = slot
    state.reserve_source = "solana-rpc-learning"
    state.last_reserve_event_id = f"learning-rpc:{slot}:{state.mint}"
    state.reserve_audit = {
        "proof_version": RESERVE_PROOF_VERSION,
        "requested_at": requested_at.isoformat(),
        "observed_at": observed_at.isoformat(),
        "slot": slot,
        "commitment": "confirmed",
        "route_identity": list(route_identity(state)),
        "virtual_token_reserves": state.virtual_token_reserves,
        "virtual_quote_reserves": state.virtual_quote_reserves,
        "real_quote_reserves": state.real_quote_reserves,
        "fee_components_bps": (
            list(state.reserve_fee_components) if state.reserve_fee_components is not None else None
        ),
        "economic_state": "empty_route" if empty else "reserves_present",
        "fee_market_cap": market_cap,
        "fee_supply": fee_supply,
        "fee_supply_source": (
            "verified_mint" if mayhem or original.venue == "pump_swap" else "fixed_billion"
        ),
        "is_mayhem_mode": mayhem,
        "fee_recipe": "pump-sdk-1.36.0/pump-swap-sdk-1.19.0",
        "accounts": [
            {
                "address": address,
                "owner": accounts[address]["owner"],
                "sha256": hashlib.sha256(accounts[address]["raw"]).hexdigest(),
            }
            for address in addresses
        ],
    }
    return state
