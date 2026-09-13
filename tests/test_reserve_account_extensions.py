"""The reserve adapter must follow the independent contract without changing events."""

import copy
import json
import struct
from pathlib import Path

import pytest
from signal_arcade.intelligence.reserve_refresh import ReserveRefreshRejected, _decoded
from signal_arcade.providers.solana import PUMP_AMM_PROGRAM, PUMP_PROGRAM
from test_v1104_refresh import IDL_DIR, anchor_account, route_fixture

CONTRACT = json.loads(
    (Path(__file__).parent / "fixtures/pump_rust_account_contract_0_1_13.json").read_text()
)
CASES = [
    ("pump", "Global", "<BQ", (1, 100)),
    ("pump_amm", "GlobalConfig", "<BQ", (1, 100)),
    ("pump", "BondingCurve", "<QB", (75, 1)),
    ("pump_amm", "Pool", "<QB", (75, 1)),
    ("pump", "FeeConfig", "<QQQ", (0, 95, 30)),
    ("pump_amm", "FeeConfig", "<QQQ", (20, 5, 5)),
]


@pytest.mark.parametrize("namespace,name,layout,fields", CASES)
def test_adapter_matches_official_appended_fields(namespace, name, layout, fields):
    old = json.loads((IDL_DIR / f"{namespace}.json").read_text())
    old_types = {t["name"]: t["type"] for t in old["types"]}
    new_types = {t["name"]: t["type"] for t in CONTRACT["programs"][namespace]["types"]}
    old_fields = old_types[name]["fields"]
    new_fields = new_types[name]["fields"]
    assert new_fields[: len(old_fields)] == old_fields
    appended = new_fields[len(old_fields) :]
    expected = {
        "FeeConfig": ["exotic_flat_fees"],
        "Global": ["creator_fee_configurable", "max_configurable_creator_fee_bps"],
        "GlobalConfig": ["creator_fee_configurable", "max_configurable_creator_fee_bps"],
        "BondingCurve": ["creator_fee_bps", "can_edit_creator_fee"],
        "Pool": ["creator_fee_bps", "can_edit_creator_fee"],
    }[name]
    assert [field["name"] for field in appended] == expected
    assert [field["type"] for field in appended] == (
        [{"defined": {"name": "Fees"}}]
        if name == "FeeConfig"
        else (["bool", "u64"] if name in {"Global", "GlobalConfig"} else ["u64", "bool"])
    )
    _, _, decoder, _ = route_fixture()
    program = PUMP_PROGRAM if namespace == "pump" else PUMP_AMM_PROGRAM
    prefix = anchor_account(namespace, name, {})
    for padding in (b"", bytes(31)):
        raw = prefix + struct.pack(layout, *fields) + padding
        before = copy.deepcopy(decoder.accounts)
        values = _decoded(decoder, {"raw": raw}, program, name)
        if name == "FeeConfig":
            assert tuple(values["exotic_flat_fees"].values()) == fields
        else:
            assert tuple(values[field] for field in expected) == fields
        holder_flag_bytes = int(name in {"BondingCurve", "Pool"} and bool(padding))
        assert values["_remaining_bytes"] == len(padding) - holder_flag_bytes
        assert decoder.accounts == before
        assert decoder.decode_account(raw, expected_program=program)[2]["_remaining_bytes"] == (
            struct.calcsize(layout) + len(padding)
        )


@pytest.mark.parametrize("namespace,name,layout,fields", CASES)
def test_legacy_defaults_partial_and_future_extensions(namespace, name, layout, fields):
    _, _, decoder, _ = route_fixture()
    program = PUMP_PROGRAM if namespace == "pump" else PUMP_AMM_PROGRAM
    prefix = anchor_account(namespace, name, {})
    value = _decoded(decoder, {"raw": prefix}, program, name)
    if name == "FeeConfig":
        assert not any(value["exotic_flat_fees"].values())
    else:
        assert value.get("creator_fee_bps", value.get("max_configurable_creator_fee_bps")) == 0
    for length in range(1, struct.calcsize(layout)):
        for tail in (bytes(length), struct.pack(layout, *fields)[:length]):
            with pytest.raises(ReserveRefreshRejected, match="unsupported_account_layout"):
                _decoded(decoder, {"raw": prefix + tail}, program, name)
    future = prefix + struct.pack(layout, *fields) + bytes(40) + b"\x01"
    with pytest.raises(ReserveRefreshRejected, match="unreviewed_account_extension"):
        _decoded(decoder, {"raw": future}, program, name)
    if name != "FeeConfig":
        bad = list(fields)
        bad[0 if name in {"Global", "GlobalConfig"} else 1] = 2
        with pytest.raises(ReserveRefreshRejected, match="unsupported_account_layout"):
            _decoded(decoder, {"raw": prefix + struct.pack(layout, *bad)}, program, name)
