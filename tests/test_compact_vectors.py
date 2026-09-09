#!/usr/bin/env python3
"""Compact message protocol KATs vs 本家 (linejs compact.ts)."""

import json
import os

import pytest

from linepy import compact


VECTORS = os.path.join(os.path.dirname(__file__), "vectors", "linejs_vectors.json")


@pytest.fixture(scope="module")
def vec():
    with open(VECTORS) as f:
        return json.load(f)["compact"]


def test_pack_plain_message(vec):
    p = vec["plain"]
    got = compact.pack_compact_plain_message(p["seqId"], p["to"], p["text"])
    assert got.hex() == p["out"]


def test_pack_plain_ascii(vec):
    p = vec["plain_ascii"]
    got = compact.pack_compact_plain_message(p["seqId"], p["to"], p["text"])
    assert got.hex() == p["out"]


def test_pack_e2ee_message(vec):
    e = vec["e2ee"]
    chunks = [bytes.fromhex(c) for c in e["chunks"]]
    got = compact.pack_compact_e2ee_message(e["seqId"], e["to"], chunks, e["msgType"])
    assert got.hex() == e["out"]


def test_encode_compact_text(vec):
    for case in vec["encodeCompactText"]:
        assert compact.encode_compact_text(case["text"]).hex() == case["out"], case["text"]


def test_write_compact_i32(vec):
    for case in vec["writeCompactI32"]:
        out = bytearray()
        compact.write_compact_i32(out, case["v"])
        assert bytes(out).hex() == case["out"], case["v"]


def test_decode_response(vec):
    r = vec["response"]
    decoded = compact.decode_compact_message_response(bytes.fromhex(r["bytes"]))
    assert decoded["sequenceId"] == r["decoded"]["sequenceId"]
    assert decoded["messageId"] == int(r["decoded"]["messageId"])
    assert decoded["createdTime"] == r["decoded"]["createdTime"]


def test_decode_error_response():
    # bool=false(2) then zigzag i32 error code 5 -> 0x0a
    data = bytes([2, 0x0A])
    with pytest.raises(compact.CompactMessageProtocolError) as ei:
        compact.decode_compact_message_response(data)
    assert ei.value.code == 5


def test_mid_type_and_format_errors():
    with pytest.raises(compact.CompactMessageProtocolError):
        compact.pack_compact_plain_message(1, "x" + "0" * 32, "hi")  # bad prefix
    with pytest.raises(compact.CompactMessageProtocolError):
        compact.pack_compact_plain_message(1, "u123", "hi")  # bad length
