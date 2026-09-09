#!/usr/bin/env python3
"""
LEGY transport & auth-token known-answer tests vs 本家 (linejs).

Cross-validates the exported legy.ts / auth_token.ts functions against the
Python port using vectors produced by tools/gen_vectors.ts.
"""

import json
import os

import pytest

from linepy.protocol import legy

VECTORS = os.path.join(os.path.dirname(__file__), "vectors", "linejs_vectors.json")


def _h(s):
    return bytes.fromhex(s)


@pytest.fixture(scope="module")
def vec():
    with open(VECTORS) as f:
        return json.load(f)


# ------------------------------------------------------------------- xxhash

def test_xxhash32(vec):
    for case in vec["legy"]["xxhash32"]:
        got = legy.xxhash32(case["input_utf8"].encode("utf-8"), case["seed"])
        assert got == case["out"], case["input_utf8"]


def test_legy_hmac_length():
    # legyHmac is not exported by 本家; verify structure (4 bytes, xxhash-based).
    h = legy.legy_hmac(bytes(range(16)), b"payload")
    assert len(h) == 4


# ------------------------------------------------------------------- headers

def test_encode_legy_headers(vec):
    c = vec["legy"]["encodeLegyHeaders"]
    got = legy.encode_legy_headers(c["headers"])
    assert got.hex() == c["out"]


def test_decode_legy_headers(vec):
    c = vec["legy"]["decodeLegyHeaders"]
    headers, data = legy.decode_legy_headers(_h(c["encoded"]))
    assert headers == c["headers"]
    assert data.hex() == c["data"]


def test_encode_decode_roundtrip():
    hdrs = {"x-lpqs": "/CA5?x=1", "x-lt": "abc-トークン"}
    body = b"\x00\x01thrift-body"
    headers, data = legy.decode_legy_headers(legy.encode_legy_headers(hdrs) + body)
    assert headers == hdrs
    assert data == body


# --------------------------------------------------------------- auth_token

def test_is_jwt(vec):
    for case in vec["auth_token"]["isJwt"]:
        assert legy.is_jwt(case["token"]) == case["out"], case["token"]


def test_create_primary_access_token(vec):
    c = vec["auth_token"]["createPrimaryAccessToken"]
    got = legy.create_primary_access_token(c["authKey"], c["now"])
    assert got == c["out"]


def test_resolve_line_access_token(vec):
    for case in vec["auth_token"]["resolveLineAccessToken"]:
        assert legy.resolve_line_access_token(case["token"]) == case["out"]


def test_should_use_legy_encrypted_access(vec):
    for case in vec["auth_token"]["shouldUseLegyEncryptedAccess"]:
        assert legy.should_use_legy_encrypted_access(case["token"]) == case["out"]


# --------------------------------------------------------------- transport

def test_transport_roundtrip_same_key():
    """A request encoded then decoded with the same session key round-trips."""
    t = legy.LegyEncryptedTransport()
    inner = legy.encode_legy_headers({"x-lc": "200"}) + b"RESPONSE-BODY"
    fake_response = t._encrypt(bytes([7]) + inner)  # server: [le]+headers+body
    headers, body = t.decode_response_body(fake_response)
    assert headers == {"x-lc": "200"}
    assert body == b"RESPONSE-BODY"


def test_x_lcs_format():
    t = legy.LegyEncryptedTransport()
    lcs = t._get_x_lcs()
    assert lcs.startswith("0008")
    # stable across calls
    assert t._get_x_lcs() == lcs


def test_is_legy_talk_path():
    for p in ["/S3", "/S4", "/V4", "/SYNC3", "/SYNC4", "/P4", "/P5",
              "/NP4", "/NP5", "/C5", "/CA5", "/ECA5"]:
        assert legy.is_legy_talk_path(p)
    assert not legy.is_legy_talk_path("/SQ1")
    assert legy.is_legy_talk_path("/CA5?query=1")  # query ignored
