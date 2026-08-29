from __future__ import annotations

import base64
import json
import struct
from pathlib import Path

from signal_arcade.providers.anchor import AnchorEventDecoder, b58encode


def test_decodes_new_anchor_idl_event_shape(tmp_path: Path) -> None:
    discriminator = [1, 2, 3, 4, 5, 6, 7, 8]
    idl = {
        "address": "Program111111111111111111111111111111111",
        "events": [{"name": "TradeEvent", "discriminator": discriminator}],
        "types": [
            {
                "name": "TradeEvent",
                "type": {
                    "kind": "struct",
                    "fields": [
                        {"name": "mint", "type": "pubkey"},
                        {"name": "amount", "type": "u64"},
                        {"name": "is_buy", "type": "bool"},
                    ],
                },
            }
        ],
    }
    path = tmp_path / "idl.json"
    path.write_text(json.dumps(idl), encoding="utf-8")
    mint_bytes = bytes(range(32))
    payload = bytes(discriminator) + mint_bytes + struct.pack("<Q", 42) + b"\x01"
    line = "Program data: " + base64.b64encode(payload).decode()
    decoded = AnchorEventDecoder([path]).decode_log_line(line)
    assert decoded is not None
    _, name, values = decoded
    assert name == "TradeEvent"
    assert values == {
        "mint": b58encode(mint_bytes),
        "amount": 42,
        "is_buy": True,
        "_remaining_bytes": 0,
    }


def test_unknown_or_malformed_events_are_ignored(tmp_path: Path) -> None:
    decoder = AnchorEventDecoder([])
    assert decoder.decode_log_line("Program log: hello") is None
    assert decoder.decode_log_line("Program data: not-base64") is None


def test_decodes_pinned_anchor_account_shape_and_rejects_wrong_name(tmp_path: Path) -> None:
    discriminator = [9, 8, 7, 6, 5, 4, 3, 2]
    program = "Program111111111111111111111111111111111"
    idl = {
        "address": program,
        "accounts": [{"name": "Pool", "discriminator": discriminator}],
        "types": [
            {
                "name": "Pool",
                "type": {
                    "kind": "struct",
                    "fields": [
                        {"name": "base_mint", "type": "pubkey"},
                        {"name": "quote_mint", "type": "pubkey"},
                    ],
                },
            }
        ],
    }
    path = tmp_path / "pool.json"
    path.write_text(json.dumps(idl), encoding="utf-8")
    base = bytes(range(32))
    quote = bytes(reversed(range(32)))
    raw = bytes(discriminator) + base + quote
    decoder = AnchorEventDecoder([path])

    assert decoder.decode_account(
        raw,
        expected_program=program,
        expected_name="Pool",
    ) == (
        program,
        "Pool",
        {
            "base_mint": b58encode(base),
            "quote_mint": b58encode(quote),
            "_remaining_bytes": 0,
        },
    )
    assert decoder.decode_account(raw, expected_program=program, expected_name="Vault") is None


def test_event_discriminator_collisions_are_scoped_to_the_emitting_program(
    tmp_path: Path,
) -> None:
    discriminator = [8, 7, 6, 5, 4, 3, 2, 1]
    program_a = "ProgramA11111111111111111111111111111111"
    program_b = "ProgramB11111111111111111111111111111111"
    definitions = (
        (program_a, "a.json", [{"name": "amount", "type": "u64"}]),
        (program_b, "b.json", [{"name": "enabled", "type": "bool"}]),
    )
    paths: list[Path] = []
    for program, filename, fields in definitions:
        path = tmp_path / filename
        path.write_text(
            json.dumps(
                {
                    "address": program,
                    "events": [{"name": "SharedEvent", "discriminator": discriminator}],
                    "types": [
                        {
                            "name": "SharedEvent",
                            "type": {"kind": "struct", "fields": fields},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        paths.append(path)

    decoder = AnchorEventDecoder(paths)
    amount_line = (
        "Program data: " + base64.b64encode(bytes(discriminator) + struct.pack("<Q", 42)).decode()
    )
    bool_line = "Program data: " + base64.b64encode(bytes(discriminator) + b"\x01").decode()

    assert decoder.decode_log_line(amount_line) is None
    assert decoder.decode_log_line(amount_line, program_a) == (
        program_a,
        "SharedEvent",
        {"amount": 42, "_remaining_bytes": 0},
    )
    assert decoder.decode_log_line(bool_line, program_b) == (
        program_b,
        "SharedEvent",
        {"enabled": True, "_remaining_bytes": 0},
    )
