# -*- coding: utf-8 -*-
"""
Compact message protocol for LINEPY (/CA5, /ECA5).

Faithful Python port of linejs
(resource/linejs/packages/linejs/base/service/talk/compact.ts).

Bypasses Thrift serialization and packs a minimal binary frame for very fast
plain (msgType 2) and E2EE (msgType 5/6) message sends.
"""

import struct
from typing import List, Sequence, Union

from .exceptions import CompactMessageProtocolError

COMPACT_PLAIN_MESSAGE_ENDPOINT = "/CA5"
COMPACT_E2EE_MESSAGE_ENDPOINT = "/ECA5"


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------

def _assert_byte(value: int, name: str) -> int:
    if not isinstance(value, int) or value < 0 or value > 0xFF:
        raise ValueError(f"{name} must be a byte")
    return value


def write_varint(out: bytearray, value: int) -> None:
    """Unsigned LEB128 varint."""
    if value < 0:
        raise ValueError("compact varint value must be unsigned")
    while True:
        if (value & ~0x7F) == 0:
            out.append(value)
            return
        out.append((value & 0x7F) | 0x80)
        value >>= 7


def write_compact_i32(out: bytearray, value: int) -> None:
    """ZigZag + varint for a signed 32-bit int."""
    if not isinstance(value, int):
        raise TypeError("compact i32 value must be an integer")
    if value < -0x80000000 or value > 0x7FFFFFFF:
        raise ValueError("compact i32 value out of range")
    write_varint(out, (value << 1) ^ (value >> 31))


def write_compact_i64(out: bytearray, value: int) -> None:
    write_varint(out, (value << 1) ^ (value >> 63))


def _write_compact_binary(out: bytearray, data: bytes) -> None:
    write_varint(out, len(data))
    out.extend(data)


def encode_compact_text(text: str) -> bytes:
    """Pick the shorter of UTF-8-with-BOM and UTF-16LE-with-BOM (as 本家 does).

    ``text.length`` in JS counts UTF-16 code units, so the UTF-16 branch is
    reproduced with Python's ``utf-16-le`` codec (surrogate pairs included).
    """
    utf8 = b"\xef\xbb\xbf" + text.encode("utf-8")
    utf16_body = text.encode("utf-16-le")
    utf16 = b"\xff\xfe" + utf16_body
    return utf16 if len(utf8) > len(utf16) else utf8


def _get_mid_type_by_mid(mid: str) -> int:
    first = mid[0] if mid else ""
    if first == "u":
        return 0
    if first == "r":
        return 1
    if first == "c":
        return 2
    raise CompactMessageProtocolError("unsupported compact message MID type")


def _mid_to_bytes(mid: str) -> bytes:
    hex_part = mid[1:]
    if len(hex_part) != 32 or any(c not in "0123456789abcdefABCDEF" for c in hex_part):
        raise CompactMessageProtocolError("invalid compact message MID format")
    return bytes.fromhex(hex_part)


def _read_signed_i32(b: bytes) -> int:
    if len(b) != 4:
        raise CompactMessageProtocolError("compact E2EE key id chunk must be 4 bytes")
    (value,) = struct.unpack(">I", b)
    return value - 0x100000000 if value > 0x7FFFFFFF else value


def _normalize_e2ee_chunks(chunks: Sequence[bytes]) -> List[bytes]:
    if len(chunks) < 5:
        raise CompactMessageProtocolError("compact E2EE message requires 5 chunks")
    return [bytes(c) for c in chunks[:5]]


def pack_compact_message(
    msg_type: int,
    seq_id: int,
    to: str,
    args: Union[str, Sequence[bytes]],
    plain_suffix: int = 0,
) -> bytes:
    """Pack a compact message frame (plain text or E2EE chunk list)."""
    out = bytearray()
    out.append(_assert_byte(msg_type, "msgType"))
    out.append(_get_mid_type_by_mid(to))
    write_compact_i32(out, seq_id)
    out.extend(_mid_to_bytes(to))

    if isinstance(args, str):
        _write_compact_binary(out, encode_compact_text(args))
        out.append(_assert_byte(plain_suffix, "plainSuffix"))
        return bytes(out)

    chunks = _normalize_e2ee_chunks(args)
    out.append(2)
    for chunk in chunks[:3]:
        _write_compact_binary(out, chunk)
    write_compact_i32(out, _read_signed_i32(chunks[3]))
    write_compact_i32(out, _read_signed_i32(chunks[4]))
    return bytes(out)


def pack_compact_plain_message(seq_id: int, to: str, text: str) -> bytes:
    return pack_compact_message(2, seq_id, to, text)


def pack_compact_e2ee_message(
    seq_id: int, to: str, chunks: Sequence[bytes], msg_type: int = 5
) -> bytes:
    return pack_compact_message(msg_type, seq_id, to, chunks)


# ---------------------------------------------------------------------------
# Response decoding
# ---------------------------------------------------------------------------

class CompactReader:
    def __init__(self, data: bytes):
        self._data = data
        self._offset = 0

    def _read_byte(self) -> int:
        if self._offset >= len(self._data):
            raise CompactMessageProtocolError("unexpected end of compact data")
        b = self._data[self._offset]
        self._offset += 1
        return b

    def _read_varint(self) -> int:
        shift = 0
        result = 0
        while True:
            byte = self._read_byte()
            result |= (byte & 0x7F) << shift
            if (byte & 0x80) == 0:
                return result
            shift += 7
            if shift > 70:
                raise CompactMessageProtocolError("compact varint is too long")

    def read_bool(self) -> bool:
        value = self._read_byte()
        if value == 1:
            return True
        if value == 2:
            return False
        raise CompactMessageProtocolError(f"invalid compact bool value {value}")

    def read_i32(self) -> int:
        n = self._read_varint()
        decoded = (n >> 1) ^ -(n & 1)
        if decoded < -0x80000000 or decoded > 0x7FFFFFFF:
            raise CompactMessageProtocolError("compact i32 out of range")
        return decoded

    def read_i64(self) -> int:
        n = self._read_varint()
        return (n >> 1) ^ -(n & 1)

    def assert_done(self) -> None:
        if self._offset != len(self._data):
            raise CompactMessageProtocolError(
                "unexpected trailing compact message response bytes"
            )


def decode_compact_message_response(data: bytes) -> dict:
    """Decode a /CA5 or /ECA5 response -> {sequenceId, messageId, createdTime}."""
    reader = CompactReader(data)
    success = reader.read_bool()
    if not success:
        code = reader.read_i32()
        raise CompactMessageProtocolError(
            f"compact message failed: error code {code}", code
        )
    sequence_id = reader.read_i32()
    message_id = reader.read_i64()
    created_time_ms = reader.read_i64()
    reader.assert_done()
    return {
        "sequenceId": sequence_id,
        "messageId": message_id,
        "createdTime": created_time_ms // 1000,
    }
