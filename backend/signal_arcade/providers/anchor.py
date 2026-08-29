from __future__ import annotations

import base64
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(data: bytes) -> str:
    zeros = len(data) - len(data.lstrip(b"\0"))
    number = int.from_bytes(data, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = BASE58_ALPHABET[remainder] + encoded
    return "1" * zeros + (encoded or ("" if zeros else "1"))


class DecodeError(ValueError):
    pass


@dataclass(slots=True)
class _Cursor:
    data: bytes
    offset: int = 0

    def take(self, size: int) -> bytes:
        end = self.offset + size
        if size < 0 or end > len(self.data):
            raise DecodeError("event payload ended unexpectedly")
        value = self.data[self.offset : end]
        self.offset = end
        return value


class AnchorEventDecoder:
    """Decode Anchor `Program data:` records using pinned official IDLs."""

    def __init__(self, idl_paths: list[Path]) -> None:
        self.events: dict[tuple[str, bytes], tuple[str, dict[str, Any], dict[str, Any]]] = {}
        self.accounts: dict[tuple[str, bytes], tuple[str, dict[str, Any], dict[str, Any]]] = {}
        for path in idl_paths:
            if not path.exists():
                continue
            idl = json.loads(path.read_text(encoding="utf-8"))
            program = str(idl.get("address") or idl.get("metadata", {}).get("address") or path.stem)
            types = {item["name"]: item["type"] for item in idl.get("types", [])}
            for account in idl.get("accounts", []):
                discriminator = account.get("discriminator")
                account_type = types.get(str(account.get("name")))
                if (
                    not isinstance(discriminator, list)
                    or len(discriminator) != 8
                    or not isinstance(account_type, dict)
                ):
                    continue
                self.accounts[(program, bytes(discriminator))] = (
                    program,
                    {"name": account["name"], "type": account_type},
                    types,
                )
            for event in idl.get("events", []):
                discriminator = event.get("discriminator")
                if not isinstance(discriminator, list) or len(discriminator) != 8:
                    continue
                event_definition = dict(event)
                if not event_definition.get("fields"):
                    matching_type = types.get(str(event.get("name")), {})
                    if matching_type.get("kind") == "struct":
                        event_definition["fields"] = matching_type.get("fields", [])
                self.events[(program, bytes(discriminator))] = (
                    program,
                    event_definition,
                    types,
                )

    def decode_log_line(
        self, line: str, expected_program: str | None = None
    ) -> tuple[str, str, dict[str, Any]] | None:
        marker = "Program data: "
        if marker not in line:
            return None
        encoded = line.split(marker, 1)[1].strip()
        try:
            raw = base64.b64decode(encoded, validate=True)
        except ValueError:
            return None
        if len(raw) < 8:
            return None
        discriminator = raw[:8]
        if expected_program is not None:
            match = self.events.get((expected_program, discriminator))
        else:
            matches = [
                definition
                for (_program, candidate), definition in self.events.items()
                if candidate == discriminator
            ]
            match = matches[0] if len(matches) == 1 else None
        if match is None:
            return None
        program, event, types = match
        cursor = _Cursor(raw[8:])
        values: dict[str, Any] = {}
        try:
            for field in event.get("fields", []):
                values[field["name"]] = self._read(cursor, field["type"], types)
        except (DecodeError, KeyError, TypeError, ValueError, struct.error):
            return None
        values["_remaining_bytes"] = len(cursor.data) - cursor.offset
        return program, str(event["name"]), values

    def decode_account(
        self,
        raw: bytes,
        *,
        expected_program: str | None = None,
        expected_name: str | None = None,
    ) -> tuple[str, str, dict[str, Any]] | None:
        """Decode a pinned Anchor account without trusting caller-provided field offsets."""

        if len(raw) < 8:
            return None
        discriminator = raw[:8]
        if expected_program is not None:
            match = self.accounts.get((expected_program, discriminator))
        else:
            matches = [
                definition
                for (_program, candidate), definition in self.accounts.items()
                if candidate == discriminator
            ]
            match = matches[0] if len(matches) == 1 else None
        if match is None:
            return None
        program, account, types = match
        name = str(account["name"])
        if expected_name is not None and name != expected_name:
            return None
        cursor = _Cursor(raw[8:])
        try:
            values = self._read_defined(cursor, account["type"], types)
        except (DecodeError, KeyError, TypeError, ValueError, struct.error):
            return None
        if not isinstance(values, dict):
            return None
        values["_remaining_bytes"] = len(cursor.data) - cursor.offset
        return program, name, values

    def _read(self, cursor: _Cursor, type_spec: Any, types: dict[str, Any]) -> Any:
        if isinstance(type_spec, str):
            return self._read_primitive(cursor, type_spec)
        if not isinstance(type_spec, dict):
            raise DecodeError(f"unsupported type {type_spec!r}")
        if "option" in type_spec:
            return self._read(cursor, type_spec["option"], types) if cursor.take(1)[0] else None
        if "coption" in type_spec:
            present = struct.unpack("<I", cursor.take(4))[0]
            return self._read(cursor, type_spec["coption"], types) if present else None
        if "vec" in type_spec:
            length = struct.unpack("<I", cursor.take(4))[0]
            if length > 100_000:
                raise DecodeError("unreasonable vector length")
            return [self._read(cursor, type_spec["vec"], types) for _ in range(length)]
        if "array" in type_spec:
            inner, length = type_spec["array"]
            return [self._read(cursor, inner, types) for _ in range(int(length))]
        if "defined" in type_spec:
            defined = type_spec["defined"]
            name = defined.get("name") if isinstance(defined, dict) else defined
            return self._read_defined(cursor, types[str(name)], types)
        raise DecodeError(f"unsupported composite type {type_spec!r}")

    def _read_defined(
        self, cursor: _Cursor, definition: dict[str, Any], types: dict[str, Any]
    ) -> Any:
        kind = definition.get("kind")
        if kind == "struct":
            return {
                field["name"]: self._read(cursor, field["type"], types)
                for field in definition.get("fields", [])
            }
        if kind == "enum":
            variant_index = cursor.take(1)[0]
            variants = definition.get("variants", [])
            if variant_index >= len(variants):
                raise DecodeError("enum variant out of range")
            variant = variants[variant_index]
            fields = variant.get("fields", [])
            if not fields:
                return variant["name"]
            return {
                "variant": variant["name"],
                "fields": [self._read(cursor, field, types) for field in fields],
            }
        if kind == "alias":
            return self._read(cursor, definition["value"], types)
        raise DecodeError(f"unsupported defined kind {kind}")

    @staticmethod
    def _read_primitive(cursor: _Cursor, name: str) -> Any:
        name = name.lower()
        formats = {
            "u8": ("<B", 1),
            "i8": ("<b", 1),
            "u16": ("<H", 2),
            "i16": ("<h", 2),
            "u32": ("<I", 4),
            "i32": ("<i", 4),
            "u64": ("<Q", 8),
            "i64": ("<q", 8),
            "f32": ("<f", 4),
            "f64": ("<d", 8),
        }
        if name in formats:
            fmt, size = formats[name]
            return struct.unpack(fmt, cursor.take(size))[0]
        if name == "u128":
            return int.from_bytes(cursor.take(16), "little", signed=False)
        if name == "i128":
            return int.from_bytes(cursor.take(16), "little", signed=True)
        if name in {"pubkey", "publickey"}:
            return b58encode(cursor.take(32))
        if name == "bool":
            value = cursor.take(1)[0]
            if value not in {0, 1}:
                raise DecodeError("invalid bool")
            return bool(value)
        if name == "string":
            length = struct.unpack("<I", cursor.take(4))[0]
            if length > 1_000_000:
                raise DecodeError("unreasonable string length")
            return cursor.take(length).decode("utf-8", errors="replace")
        if name == "bytes":
            length = struct.unpack("<I", cursor.take(4))[0]
            if length > 1_000_000:
                raise DecodeError("unreasonable byte length")
            return base64.b64encode(cursor.take(length)).decode("ascii")
        raise DecodeError(f"unsupported primitive {name}")
