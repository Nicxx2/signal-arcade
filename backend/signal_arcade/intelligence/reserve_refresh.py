"""Pure reserve validation shared by learning collection and the position watchdog."""

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
RESERVE_PROOF_VERSION = "learning-account-snapshot-v2"
# Official holder-rewards contract; the fee amounts and trade interfaces are unchanged.
RESERVE_ACCOUNT_RECIPE = "f216b6724c6ede79d7cef9ce210b741f7e17e93b"

# Appended account fields from pump-rust-client 0.1.13 (published 2026-09-09).
# Its archive SHA-256 and independent account definitions are retained in
# tests/fixtures/pump_rust_account_contract_0_1_13.json. Keep the stream IDLs pinned:
# replacing them would also change historical CreateEvent/CreatePoolEvent decoding.
_ACCOUNT_EXTENSIONS = {
    "FeeConfig": "<QQQ",
    "Global": "<BQ",
    "GlobalConfig": "<BQ",
    "BondingCurve": "<QB",
    "Pool": "<QB",
}


class ReserveRefreshRejected(ValueError):
    def __init__(
        self,
        reason: str,
        *,
        account_type: str | None = None,
        layout: dict[str, int | str] | None = None,
    ) -> None:
        super().__init__(reason)
        # Diagnostic context only: keep the existing reason and acceptance rules intact.
        self.account_type = account_type
        self.layout = dict(layout) if layout is not None else None


def _layout_details(raw: bytes, reviewed_bytes: int | None = None) -> dict[str, int | str]:
    # Do not retain account bodies or hash arbitrarily large RPC data on the market boundary.
    # The explicit sample length distinguishes a full-account digest from a bounded prefix.
    sample = raw[:4096]
    details: dict[str, int | str] = {
        "account_bytes": len(raw),
        "sample_bytes": len(sample),
        "sample_sha256": hashlib.sha256(sample).hexdigest(),
    }
    if reviewed_bytes is not None:
        details["reviewed_bytes"] = reviewed_bytes
        details["unreviewed_bytes"] = max(0, len(raw) - reviewed_bytes)
    return details


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
        raise ReserveRefreshRejected(
            "unsupported_account_layout", account_type=name, layout=_layout_details(account["raw"])
        )
    values = result[2]
    remaining = int(values.get("_remaining_bytes", 0))
    tail = account["raw"][-remaining:] if remaining else b""
    layout = _ACCOUNT_EXTENSIONS.get(name)
    reviewed_bytes = len(account["raw"]) - remaining
    if layout is not None:
        size = struct.calcsize(layout)
        if tail:
            reviewed_bytes += size
        # Exact legacy prefixes have no appended fields. Do not zero-pad a partially
        # received extension, even when its bytes happen to be zero.
        if tail and len(tail) < size:
            raise ReserveRefreshRejected(
                "unsupported_account_layout",
                account_type=name,
                layout=_layout_details(account["raw"], reviewed_bytes),
            )
        extension = struct.unpack(layout, tail[:size] if tail else bytes(size))
        if name == "FeeConfig":
            values["exotic_flat_fees"] = dict(
                zip(("lp_fee_bps", "protocol_fee_bps", "creator_fee_bps"), extension, strict=True)
            )
        elif name in {"Global", "GlobalConfig"}:
            if extension[0] not in (0, 1):
                raise ReserveRefreshRejected(
                    "unsupported_account_layout",
                    account_type=name,
                    layout=_layout_details(account["raw"], reviewed_bytes),
                )
            values["creator_fee_configurable"] = bool(extension[0])
            values["max_configurable_creator_fee_bps"] = extension[1]
        else:
            if extension[1] not in (0, 1):
                raise ReserveRefreshRejected(
                    "unsupported_account_layout",
                    account_type=name,
                    layout=_layout_details(account["raw"], reviewed_bytes),
                )
            values["creator_fee_bps"] = extension[0]
            values["can_edit_creator_fee"] = bool(extension[1])
        tail = tail[size:]
    if name == "Global":
        values["holder_reward_claim_authority"] = NATIVE_SOL_MINT
        values["is_holder_reward_enabled"] = False
        if len(tail) >= 33:
            reviewed_bytes += 33
            if tail[32] not in (0, 1):
                raise ReserveRefreshRejected(
                    "unsupported_account_layout",
                    account_type=name,
                    layout=_layout_details(account["raw"], reviewed_bytes),
                )
            values["holder_reward_claim_authority"] = str(Pubkey.from_bytes(tail[:32]))
            values["is_holder_reward_enabled"] = bool(tail[32])
            tail = tail[33:]
        elif any(tail):
            # Preserve legacy zero allocation padding, but never complete a partially
            # received authority with invented bytes or a default enabled flag.
            raise ReserveRefreshRejected(
                "unsupported_account_layout",
                account_type=name,
                layout=_layout_details(account["raw"], reviewed_bytes + 33),
            )
    elif name in {"BondingCurve", "Pool"}:
        values["is_holder_reward"] = False
        if tail:
            reviewed_bytes += 1
            if tail[0] not in (0, 1):
                raise ReserveRefreshRejected(
                    "unsupported_account_layout",
                    account_type=name,
                    layout=_layout_details(account["raw"], reviewed_bytes),
                )
            values["is_holder_reward"] = bool(tail[0])
            tail = tail[1:]
    if any(tail):
        raise ReserveRefreshRejected(
            "unreviewed_account_extension",
            account_type=name,
            layout=_layout_details(account["raw"], reviewed_bytes),
        )
    values["_remaining_bytes"] = len(tail)
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
    mint_supply = int(safety["supply"])
    if not 0 < mint_supply <= 2**64 - 1:
        raise ReserveRefreshRejected("invalid_fee_supply")
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
    coin_creator_fee_bps: int
    canonical = True
    mayhem = False
    holder_reward = False
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
        holder_reward = bool(curve["is_holder_reward"])
        state.virtual_token_reserves = int(curve["virtual_token_reserves"])
        state.virtual_quote_reserves = int(curve["virtual_quote_reserves"])
        state.real_token_reserves = int(curve["real_token_reserves"])
        state.real_quote_reserves = int(curve["real_quote_reserves"])
        creator = str(curve["creator"])
        coin_creator_fee_bps = int(curve["creator_fee_bps"])
        # pump-rust-client 0.1.13 math/bonding_curve.rs fee_for_quote(): curve
        # Mayhem sells use current mint supply; ordinary curves use fixed supply.
        fixed_supply = not mayhem
        fee_supply = 1_000_000_000_000_000 if fixed_supply else mint_supply
        state.reserve_lp_fee_bps = 0
    else:
        pool = _decoded(
            decoder,
            _account(accounts, original.pool_address, program),
            program,
            "Pool",
        )
        mayhem = bool(pool.get("is_mayhem_mode"))
        holder_reward = bool(pool["is_holder_reward"])
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
        coin_creator_fee_bps = int(pool["creator_fee_bps"])
        canonical = pool["creator"] == pda(
            PUMP_PROGRAM,
            b"pool-authority",
            bytes(Pubkey.from_string(original.mint)),
        )
        # This differs from bonding curves. The current SDK's sdk/mod.rs
        # fee_tier_supply(), mirroring Pool::market_cap, fixes Mayhem AMM supply.
        fixed_supply = mayhem
        fee_supply = 1_000_000_000_000_000 if fixed_supply else mint_supply
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
    creator_fee_gate = bool(global_values["creator_fee_configurable"])
    if creator_fee_gate and coin_creator_fee_bps != 0:
        # The global maximum and can_edit_creator_fee constrain configuration,
        # not a trade against an existing stored rate. Zero means use the schedule.
        fees["creator_fee_bps"] = coin_creator_fee_bps
    state.reserve_lp_fee_bps = fees["lp_fee_bps"] if original.venue == "pump_swap" else 0
    state.reserve_fee_components = (
        state.reserve_lp_fee_bps,
        fees["protocol_fee_bps"],
        fees["creator_fee_bps"] if creator != NATIVE_SOL_MINT else 0,
    )
    state.fee_bps = sum(state.reserve_fee_components)
    if any(value < 0 for value in state.reserve_fee_components) or state.fee_bps >= 10_000:
        raise ReserveRefreshRejected("invalid_fee_rates")
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
        "fee_supply_source": "fixed_billion" if fixed_supply else "verified_mint",
        "is_mayhem_mode": mayhem,
        "is_holder_reward": holder_reward,
        "account_recipe": RESERVE_ACCOUNT_RECIPE,
        "creator_fee_configurable": creator_fee_gate,
        "stored_creator_fee_bps": coin_creator_fee_bps,
        "fee_recipe": "pump-rust-client-0.1.13",
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
