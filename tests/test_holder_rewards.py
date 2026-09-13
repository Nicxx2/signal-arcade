"""Holder-reward accounts against the independent, pinned official September contract."""

import base64
import copy
import hashlib
import json
import struct
from pathlib import Path

import pytest
from signal_arcade.intelligence.reserve_refresh import (
    ReserveRefreshRejected,
    _decoded,
    reserve_addresses,
    validated_learning_state,
)
from signal_arcade.providers.solana import PUMP_AMM_PROGRAM, PUMP_PROGRAM
from solders.pubkey import Pubkey
from test_configurable_reserve_fees import configured_route
from test_v1104_refresh import IDL_DIR, anchor_account, route_fixture

FIXTURES = Path(__file__).parent / "fixtures"
CONTRACT = json.loads((FIXTURES / "pump_holder_rewards_contract_20260912.json").read_text())
CAPTURE = json.loads((FIXTURES / "pump_global_unreviewed_20260912.json").read_text())
AUTHORITY = bytes(range(1, 33))


def normalize(fields):
    return [(field["name"], field["type"]) for field in fields]


def test_captured_global_is_explained_by_the_new_official_contract():
    raw = base64.b64decode(CAPTURE["data_base64"], validate=True)
    assert hashlib.sha256(raw).hexdigest() == CAPTURE["sha256"]
    assert len(raw) == 1087
    _, _, decoder, _ = route_fixture()
    decoded = _decoded(decoder, {"raw": raw}, PUMP_PROGRAM, "Global")
    assert decoded["holder_reward_claim_authority"] == str(Pubkey.from_bytes(raw[1054:1086]))
    assert decoded["is_holder_reward_enabled"] is True
    assert decoded["max_configurable_creator_fee_bps"] == 300
    assert decoded["_remaining_bytes"] == 0


@pytest.mark.parametrize(
    "namespace,name,old_layout,old_fields,new_fields,new_bytes",
    [
        (
            "pump",
            "Global",
            "<BQ",
            (1, 300),
            [("holder_reward_claim_authority", "pubkey"), ("is_holder_reward_enabled", "bool")],
            AUTHORITY + b"\x01",
        ),
        ("pump", "BondingCurve", "<QB", (75, 1), [("is_holder_reward", "bool")], b"\x01"),
        ("pump_amm", "Pool", "<QB", (75, 1), [("is_holder_reward", "bool")], b"\x01"),
    ],
)
def test_account_extensions_follow_official_field_order_and_preserve_prefix(
    namespace, name, old_layout, old_fields, new_fields, new_bytes
):
    old = json.loads((IDL_DIR / f"{namespace}.json").read_text())
    previous = json.loads((FIXTURES / "pump_rust_account_contract_0_1_13.json").read_text())

    def definition(doc):
        return next(t["type"]["fields"] for t in doc["types"] if t["name"] == name)

    before = normalize(definition(previous["programs"][namespace]))
    after = normalize(definition(CONTRACT["programs"][namespace]))
    assert after == before + new_fields
    assert before[: len(definition(old))] == normalize(definition(old))
    program = PUMP_PROGRAM if namespace == "pump" else PUMP_AMM_PROGRAM
    _, _, decoder, _ = route_fixture()
    raw = anchor_account(namespace, name, {}) + struct.pack(old_layout, *old_fields)
    retained = copy.deepcopy(decoder.accounts)
    legacy = _decoded(decoder, {"raw": raw}, program, name)
    current = _decoded(decoder, {"raw": raw + new_bytes}, program, name)
    flag = new_fields[-1][0]
    assert legacy[flag] is False
    assert current[flag] is True
    assert current["_remaining_bytes"] == 0
    assert decoder.accounts == retained  # Historical event/account prefixes remain pinned.
    assert {k: v for k, v in current.items() if k not in dict(new_fields)} == {
        k: v for k, v in legacy.items() if k not in dict(new_fields)
    }
    with pytest.raises(ReserveRefreshRejected, match="unsupported_account_layout"):
        _decoded(decoder, {"raw": raw + new_bytes[:-1] + b"\x02"}, program, name)
    with pytest.raises(ReserveRefreshRejected, match="unreviewed_account_extension"):
        _decoded(decoder, {"raw": raw + new_bytes + b"\x01"}, program, name)


@pytest.mark.parametrize("length", range(1, 33))
def test_nonzero_partial_global_extension_is_not_zero_padded(length):
    _, _, decoder, _ = route_fixture()
    raw = anchor_account("pump", "Global", {}) + struct.pack("<BQ", 1, 300)
    with pytest.raises(ReserveRefreshRejected, match="unsupported_account_layout"):
        _decoded(decoder, {"raw": raw + AUTHORITY[:length]}, PUMP_PROGRAM, "Global")
    # Earlier accounts can carry zero allocation padding, which is not a partial claim.
    legacy = _decoded(decoder, {"raw": raw + bytes(length)}, PUMP_PROGRAM, "Global")
    assert legacy["is_holder_reward_enabled"] is False


@pytest.mark.parametrize("venue", ["pump_curve", "pump_swap"])
@pytest.mark.parametrize("holder", [False, True])
@pytest.mark.parametrize("creation_enabled", [False, True])
@pytest.mark.parametrize("fee_gate", [False, True])
def test_holder_reward_changes_fee_destination_not_fee_or_existing_trade_permission(
    venue, holder, creation_enabled, fee_gate
):
    state, response, decoder, now = configured_route(venue, gate=fee_gate)
    before = copy.deepcopy(state)
    baseline = validated_learning_state(state, response, decoder, requested_at=now, observed_at=now)
    route = state.curve_address if venue == "pump_curve" else state.pool_address
    response["accounts"][route]["raw"] += bytes([holder])
    if venue == "pump_curve":
        response["accounts"][reserve_addresses(state)[2]]["raw"] += AUTHORITY + bytes(
            [creation_enabled]
        )
    for empty_probe in (False, True):
        refreshed = validated_learning_state(
            state, response, decoder, requested_at=now, observed_at=now, allow_empty=empty_probe
        )
        assert refreshed.reserve_fee_components == baseline.reserve_fee_components
        assert refreshed.fee_bps == baseline.fee_bps
        assert refreshed.reserve_audit["is_holder_reward"] is holder
        assert refreshed.reserve_audit["account_recipe"] == CONTRACT["revision"]
        assert state == before


@pytest.mark.parametrize(
    "namespace,name",
    [
        ("pump", "CreateEvent"),
        ("pump", "TradeEvent"),
        ("pump_amm", "CreatePoolEvent"),
        ("pump_amm", "BuyEvent"),
        ("pump_amm", "SellEvent"),
    ],
)
def test_official_events_keep_the_old_prefix_and_existing_creator_fee_fields(namespace, name):
    old = json.loads((IDL_DIR / f"{namespace}.json").read_text())
    old_fields = next(t["type"]["fields"] for t in old["types"] if t["name"] == name)
    new_fields = next(
        t["type"]["fields"] for t in CONTRACT["programs"][namespace]["types"] if t["name"] == name
    )
    assert normalize(new_fields[: len(old_fields)]) == normalize(old_fields)
    if name in {"TradeEvent", "BuyEvent", "SellEvent"}:
        assert [f["name"] for f in new_fields[-2:]] == ["holder_rewards_bps", "holder_rewards"]
        fee = "creator_fee" if name == "TradeEvent" else "coin_creator_fee"
        assert fee in {f["name"] for f in old_fields}
