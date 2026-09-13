"""Independent on-chain fixtures and the reviewed, versioned account contract."""

import base64
import copy
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from signal_arcade.intelligence.features import TokenState
from signal_arcade.intelligence.reserve_refresh import (
    ReserveRefreshRejected,
    _decoded,
    validated_learning_state,
)
from signal_arcade.providers.anchor import AnchorEventDecoder
from signal_arcade.providers.solana import PUMP_AMM_PROGRAM, PUMP_PROGRAM
from test_v1104_refresh import IDL_DIR, route_fixture

CAPTURE = json.loads(
    (Path(__file__).parent / "fixtures/pump_shared_accounts_20260910.json").read_text()
)


@pytest.mark.parametrize("item", CAPTURE["accounts"], ids=lambda row: row["venue"] + row["name"])
def test_public_shared_accounts_match_reviewed_layout(item):
    state, response, decoder, now = route_fixture(item["venue"])
    before = copy.deepcopy(state)
    raw = base64.b64decode(item["data_base64"], validate=True)
    assert len(raw) == item["length"]
    assert hashlib.sha256(raw).hexdigest() == item["sha256"]
    program = PUMP_PROGRAM if item["venue"] == "pump_curve" else PUMP_AMM_PROGRAM
    decoded = decoder.decode_account(raw, expected_program=program, expected_name=item["name"])
    assert decoded is not None  # The stream decoder retains its older account prefix.
    remaining = decoded[2]["_remaining_bytes"]
    assert remaining > 0 and any(raw[-remaining:])
    account = {"raw": raw, "owner": item["owner"], "executable": item["executable"]}
    values = _decoded(decoder, account, program, item["name"])
    if item["name"] == "FeeConfig":
        expected = (0, 95, 30) if item["venue"] == "pump_curve" else (20, 5, 5)
        assert tuple(values["exotic_flat_fees"].values()) == expected
    else:
        assert values["creator_fee_configurable"] is True
        assert values["max_configurable_creator_fee_bps"] == 100
    # Replace just this shared account, leaving the other synthetic accounts valid.
    # Each shared account must work independently, including with legacy route accounts.
    assert item["address"] in response["accounts"]
    response["accounts"][item["address"]] = account
    for allow_empty in (False, True):
        refreshed = validated_learning_state(
            state,
            response,
            decoder,
            requested_at=now,
            observed_at=now,
            allow_empty=allow_empty,
        )
        assert refreshed.last_reserve_slot == response["slot"]
        assert state == before

    # A reviewed extension never grants permission to ignore a subsequent unknown field.
    future = {**account, "raw": raw + b"\x01"}
    reason = (
        "unsupported_account_layout" if item["name"] == "Global" else "unreviewed_account_extension"
    )
    with pytest.raises(ReserveRefreshRejected, match=f"^{reason}$"):
        _decoded(decoder, future, program, item["name"])


def test_complete_public_pool_snapshot_passes_all_reserve_checks():
    capture = json.loads(
        (Path(__file__).parent / "fixtures/pump_reserve_snapshot_20260910.json").read_text()
    )
    now = datetime.fromisoformat(capture["observed_at"])
    state = TokenState(
        **capture["route"],
        last_slot=capture["slot"] - 1,
        last_event_at=now - timedelta(minutes=5),
    )
    accounts = {}
    for address, item in capture["accounts"].items():
        raw = base64.b64decode(item["data_base64"], validate=True)
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        accounts[address] = {"owner": item["owner"], "executable": item["executable"], "raw": raw}
    response = {"slot": capture["slot"], "accounts": accounts}
    decoder = AnchorEventDecoder([IDL_DIR / "pump.json", IDL_DIR / "pump_amm.json"])
    before = copy.deepcopy(state)
    refreshed = validated_learning_state(
        state, response, decoder, requested_at=now, observed_at=now
    )
    assert state == before
    assert refreshed.route_verified
    assert refreshed.real_quote_reserves > 0
    assert refreshed.reserve_fee_components is not None
    assert 0 < refreshed.fee_bps < 10_000
    assert refreshed.reserve_audit["slot"] == capture["slot"]
    assert refreshed.reserve_audit["fee_recipe"] == "pump-rust-client-0.1.13"
    assert {a["sha256"] for a in refreshed.reserve_audit["accounts"]} == {
        a["sha256"] for a in capture["accounts"].values()
    }
