#!/usr/bin/env python3
"""Patch AndroidX DataStore Preferences for ScreenStream RTSP audio toggles.

This script edits only the RTSP DataStore keys needed for audio capture:
ENABLE_MIC and ENABLE_DEVICE_AUDIO. It keeps all existing preference entries.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        if offset >= len(data):
            raise ValueError("unexpected EOF while reading varint")
        b = data[offset]
        offset += 1
        value |= (b & 0x7F) << shift
        if not b & 0x80:
            return value, offset
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")


def write_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        to_write = value & 0x7F
        value >>= 7
        if value:
            out.append(to_write | 0x80)
        else:
            out.append(to_write)
            return bytes(out)


def parse_len_field(data: bytes, offset: int) -> tuple[int, bytes, int]:
    tag, offset = read_varint(data, offset)
    wire_type = tag & 0x07
    field_no = tag >> 3
    if wire_type != 2:
        raise ValueError(f"expected length-delimited field, got field={field_no} wire={wire_type}")
    length, offset = read_varint(data, offset)
    end = offset + length
    if end > len(data):
        raise ValueError("length-delimited field exceeds input")
    return field_no, data[offset:end], end


def parse_value(data: bytes) -> dict:
    offset = 0
    result: dict[str, object] = {"raw_hex": data.hex()}
    while offset < len(data):
        tag, offset = read_varint(data, offset)
        field_no = tag >> 3
        wire_type = tag & 0x07
        if field_no == 1 and wire_type == 0:
            value, offset = read_varint(data, offset)
            result["type"] = "boolean"
            result["value"] = bool(value)
        elif field_no == 3 and wire_type == 0:
            value, offset = read_varint(data, offset)
            result["type"] = "integer"
            result["value"] = value
        elif field_no == 4 and wire_type == 0:
            value, offset = read_varint(data, offset)
            result["type"] = "long"
            result["value"] = value
        elif field_no == 5 and wire_type == 2:
            length, offset = read_varint(data, offset)
            raw = data[offset : offset + length]
            offset += length
            result["type"] = "string"
            result["value"] = raw.decode("utf-8", errors="replace")
        elif field_no in (2, 7) and wire_type in (1, 5):
            size = 8 if wire_type == 1 else 4
            raw = data[offset : offset + size]
            offset += size
            result["type"] = "fixed"
            result["value_hex"] = raw.hex()
        elif wire_type == 2:
            length, offset = read_varint(data, offset)
            raw = data[offset : offset + length]
            offset += length
            result.setdefault("unknown_len", []).append({"field": field_no, "hex": raw.hex()})
        elif wire_type == 0:
            value, offset = read_varint(data, offset)
            result.setdefault("unknown_varint", []).append({"field": field_no, "value": value})
        else:
            raise ValueError(f"unsupported value field={field_no} wire={wire_type}")
    return result


def encode_string_value(value: str) -> bytes:
    raw = value.encode("utf-8")
    return write_varint((5 << 3) | 2) + write_varint(len(raw)) + raw


def encode_boolean_value(value: bool) -> bytes:
    return write_varint((1 << 3) | 0) + write_varint(1 if value else 0)


def parse_preference_map(data: bytes) -> dict[str, bytes]:
    offset = 0
    entries: dict[str, bytes] = {}
    while offset < len(data):
        field_no, entry_raw, offset = parse_len_field(data, offset)
        if field_no != 1:
            raise ValueError(f"unexpected top-level field {field_no}; expected preferences map field 1")

        inner_offset = 0
        key = None
        value = None
        while inner_offset < len(entry_raw):
            tag, inner_offset = read_varint(entry_raw, inner_offset)
            entry_field = tag >> 3
            wire_type = tag & 0x07
            if entry_field == 1 and wire_type == 2:
                length, inner_offset = read_varint(entry_raw, inner_offset)
                key = entry_raw[inner_offset : inner_offset + length].decode("utf-8")
                inner_offset += length
            elif entry_field == 2 and wire_type == 2:
                length, inner_offset = read_varint(entry_raw, inner_offset)
                value = entry_raw[inner_offset : inner_offset + length]
                inner_offset += length
            else:
                raise ValueError(f"unexpected map entry field={entry_field} wire={wire_type}")

        if key is None or value is None:
            raise ValueError("map entry missing key or value")
        entries[key] = value

    return entries


def encode_preference_map(entries: dict[str, bytes]) -> bytes:
    out = bytearray()
    for key in sorted(entries):
        key_raw = key.encode("utf-8")
        value_raw = entries[key]
        entry = (
            write_varint((1 << 3) | 2)
            + write_varint(len(key_raw))
            + key_raw
            + write_varint((2 << 3) | 2)
            + write_varint(len(value_raw))
            + value_raw
        )
        out += write_varint((1 << 3) | 2)
        out += write_varint(len(entry))
        out += entry
    return bytes(out)


def report(entries: dict[str, bytes]) -> dict[str, dict]:
    return {key: parse_value(value) for key, value in sorted(entries.items())}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--enable-mic", action="store_true")
    parser.add_argument("--enable-device-audio", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    entries = parse_preference_map(args.input.read_bytes())
    before = report(entries)

    if args.enable_mic:
        entries["ENABLE_MIC"] = encode_boolean_value(True)
    if args.enable_device_audio:
        entries["ENABLE_DEVICE_AUDIO"] = encode_boolean_value(True)

    encoded = encode_preference_map(entries)
    reparsed = parse_preference_map(encoded)
    after = report(reparsed)

    payload = {
        "input": str(args.input),
        "output": str(args.out) if args.out else None,
        "before": before,
        "after": after,
        "size_before": args.input.stat().st_size,
        "size_after": len(encoded),
    }

    if args.out:
        args.out.write_bytes(encoded)
    if args.report:
        args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
