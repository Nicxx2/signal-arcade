from __future__ import annotations

import copy
import json
import struct
from pathlib import Path

import pytest
from signal_arcade.intelligence.features import NATIVE_SOL_MINT
from signal_arcade.intelligence.learning import _failed_quote_checkpoint
from signal_arcade.intelligence.reserve_refresh import (
    ReserveRefreshRejected,
    reserve_addresses,
    validated_learning_state,
)
from signal_arcade.models import LearningCheckpoint
from signal_arcade.paper.curve_math import quote_sell
from signal_arcade.providers.http import TOKEN_2022_PROGRAM
from signal_arcade.providers.solana import PUMP_PROGRAM
from test_v1104_refresh import anchor_account, route_fixture, safe_mint

REFERENCE = json.loads((Path(__file__).parent / "fixtures/pump_sdk_mayhem_sell.json").read_text())


def mayhem_fixture(case):
    state, result, decoder, now = route_fixture()
    accounts = result["accounts"]
    values = decoder.decode_account(
        accounts[state.curve_address]["raw"], expected_program=PUMP_PROGRAM
    )[2]
    values.update(
        is_mayhem_mode=case["mayhem"],
        virtual_quote_reserves=int(case["quote"]),
        real_quote_reserves=int(case["quote"]),
    )
    if not case["creator"]:
        values["creator"] = NATIVE_SOL_MINT
    accounts[state.curve_address]["raw"] = anchor_account("pump", "BondingCurve", values)
    mint = safe_mint(TOKEN_2022_PROGRAM)
    raw = bytearray(mint["raw"])
    struct.pack_into("<Q", raw, 36, int(case["supply"]))
    mint["raw"] = bytes(raw)
    accounts[state.mint] = mint
    fee_address = reserve_addresses(state)[1]
    accounts[fee_address]["raw"] = anchor_account(
        "pump",
        "FeeConfig",
        {
            "fee_tiers": [
                {
                    "market_cap_lamports_threshold": int(t["threshold"]),
                    "fees": {
                        "lp_fee_bps": 0,
                        "protocol_fee_bps": int(t["protocol"]),
                        "creator_fee_bps": int(t["creator"]),
                    },
                }
                for t in REFERENCE["tiers"]
            ],
        },
    )
    return state, result, decoder, now


@pytest.mark.parametrize("case", REFERENCE["rows"])
def test_mayhem_and_standard_sell_match_official_sdk(case):
    state, result, decoder, now = mayhem_fixture(case)
    before = copy.deepcopy(state)
    refreshed = validated_learning_state(state, result, decoder, requested_at=now, observed_at=now)
    assert state == before
    expected = int(case["sdk_after_protocol_fee"]) - 5000
    args = dict(
        virtual_token_reserves=refreshed.virtual_token_reserves,
        virtual_sol_reserves=refreshed.virtual_quote_reserves,
        real_quote_reserves=refreshed.real_quote_reserves,
        token_units=int(case["amount"]),
        fee_bps=refreshed.fee_bps,
        fee_components=refreshed.reserve_fee_components,
        network_fee_lamports=5000,
    )
    if expected <= 0:
        with pytest.raises(ValueError, match="fees exceed|no SOL output"):
            quote_sell(**args)
    else:
        assert quote_sell(**args).wallet_sol_lamports == expected
    assert refreshed.reserve_audit["fee_supply"] == (
        int(case["supply"]) if case["mayhem"] else 10**15
    )
    assert refreshed.reserve_audit["is_mayhem_mode"] is case["mayhem"]


@pytest.mark.parametrize(
    "failure",
    ["mint_owner", "mint_executable", "zero_supply", "migrated", "quote", "late", "extension"],
)
def test_mayhem_still_requires_a_verified_current_route(failure):
    case = {**REFERENCE["rows"][-1], "mayhem": True}
    state, result, decoder, now = mayhem_fixture(case)
    from datetime import timedelta

    at = now
    if failure == "mint_owner":
        result["accounts"][state.mint]["owner"] = NATIVE_SOL_MINT
    elif failure == "mint_executable":
        result["accounts"][state.mint]["executable"] = True
    elif failure == "zero_supply":
        raw = bytearray(result["accounts"][state.mint]["raw"])
        struct.pack_into("<Q", raw, 36, 0)
        result["accounts"][state.mint]["raw"] = bytes(raw)
    elif failure in {"migrated", "quote"}:
        account = result["accounts"][state.curve_address]
        values = decoder.decode_account(account["raw"], expected_program=PUMP_PROGRAM)[2]
        values["complete" if failure == "migrated" else "quote_mint"] = (
            True if failure == "migrated" else state.mint
        )
        account["raw"] = anchor_account("pump", "BondingCurve", values)
    elif failure == "late":
        at += timedelta(seconds=9)
    else:
        result["accounts"][state.curve_address]["raw"] += b"unreviewed"
    with pytest.raises(ReserveRefreshRejected):
        validated_learning_state(state, result, decoder, requested_at=now, observed_at=at)


def test_unknown_quote_retains_failure_proof_without_changing_outcome():
    state, result, decoder, now = route_fixture()
    state = validated_learning_state(state, result, decoder, requested_at=now, observed_at=now)
    proof = copy.deepcopy(state.reserve_audit)
    checkpoint = _failed_quote_checkpoint(state, now, 300, ValueError("fees exceed sell proceeds"))
    assert checkpoint.net_return is checkpoint.exit_value_lamports is None
    assert checkpoint.missing_reason == "executable_exit_quote_unavailable"
    assert checkpoint.route_snapshot["accounts"] == proof["accounts"]
    assert checkpoint.route_snapshot["quote_failure_reason"] == "fees exceed sell proceeds"
    assert state.reserve_audit == proof
    assert LearningCheckpoint.model_validate_json(checkpoint.model_dump_json()) == checkpoint
