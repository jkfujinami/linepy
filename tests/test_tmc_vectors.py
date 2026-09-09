#!/usr/bin/env python3
"""
TMoreCompactProtocol decoder tests vs 本家 (linejs tmc.ts).

Vectors in tests/vectors/tmc_vectors.json are produced by decoding hand-crafted
TMC byte strings with the REAL linejs decoder; the Python port must decode the
identical bytes to the identical structure, and its deterministic tables
(Huffman tree, zigzag, bitmap, compact→TType map) must match 本家.
"""

import json
import os

import pytest

from linepy.thrift.tmc import TMoreCompactProtocol, decode_tmc

VECTORS = os.path.join(os.path.dirname(__file__), "vectors", "tmc_vectors.json")


def _norm(obj):
    """Normalise 本家 JSON (string dict keys) to compare with Python output."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            try:
                nk = int(k)
            except (ValueError, TypeError):
                nk = k
            out[nk] = _norm(v)
        return out
    if isinstance(obj, list):
        return [_norm(x) for x in obj]
    return obj


@pytest.fixture(scope="module")
def vec():
    with open(VECTORS) as f:
        return json.load(f)


def test_huffman_tree_matches(vec):
    t = TMoreCompactProtocol()
    assert t.huffman_tree == vec["huffmanTree"]


def test_zigzag_matches(vec):
    t = TMoreCompactProtocol()
    inputs = [0, 2, 4, 100, 200, 1, 3, 5, 7, 199, 398, 0]
    assert [t.decode_zigzag(x) for x in inputs] == vec["zigzag"]


def test_compact_ttype_matches(vec):
    t = TMoreCompactProtocol()
    got = [t.convert_compact_type_to_ttype(x) for x in range(13)]
    assert got == vec["ttypes"]


def test_field_bitmap_matches(vec):
    t = TMoreCompactProtocol()
    for case in vec["bitmaps"]:
        assert t.decode_field_bitmap(case["b"]) == case["ids"]


@pytest.mark.parametrize("name", ["structII", "listStr", "mapStrI32", "structBoolI64"])
def test_sample_decodes_like_honmoto(vec, name):
    sample = vec["samples"][name]
    data = bytes.fromhex(sample["hex"])
    assert decode_tmc(data) == _norm(sample["res"])


def test_empty_message():
    # headerLength 0, empty string table, fieldIdBits 0 -> empty result
    data = bytes([0, 0, 0, 0x00, 0x00, 0x00])
    assert decode_tmc(data) == {}
