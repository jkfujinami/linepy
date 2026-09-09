#!/usr/bin/env python3
"""
E2EE known-answer tests cross-validated against 本家 (linejs).

Vectors in tests/vectors/linejs_vectors.json are produced by running the
REAL linejs crypto functions (tools/gen_vectors.ts) with fixed inputs. These
tests assert the Python port produces byte-identical output.
"""

import json
import os

import pytest

from linepy.e2ee import E2EE, byte2int

VECTORS = os.path.join(os.path.dirname(__file__), "vectors", "linejs_vectors.json")


class _FakeClient:
    mid = "u-self"
    talk = None
    token_manager = None


@pytest.fixture(scope="module")
def vec():
    with open(VECTORS) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def e2ee():
    return E2EE(_FakeClient())


def _h(s):  # hex -> bytes
    return bytes.fromhex(s)


# ---------------------------------------------------------------- primitives

def test_public_from_private(e2ee, vec):
    e = vec["e2ee"]
    assert e2ee.public_from_private(_h(e["privA"])) == _h(e["pubA"])
    assert e2ee.public_from_private(_h(e["privB"])) == _h(e["pubB"])


def test_shared_secret(e2ee, vec):
    e = vec["e2ee"]
    got = e2ee.generate_shared_secret(_h(e["privA"]), _h(e["pubB"]))
    assert got == _h(e["shared"])
    # symmetry
    assert e2ee.generate_shared_secret(_h(e["privB"]), _h(e["pubA"])) == _h(e["shared"])


def test_sha256(e2ee, vec):
    for case in vec["e2ee"]["sha256"]:
        args = []
        for a in case["args"]:
            args.append(a["v"] if a["t"] == "str" else _h(a["v"]))
        assert e2ee.get_sha256_sum(*args) == _h(case["out"])


def test_xor(e2ee, vec):
    e = vec["e2ee"]
    assert e2ee.xor(_h(e["xor_input"])) == _h(e["xor_out"])


def test_int_bytes(e2ee, vec):
    for case in vec["e2ee"]["intBytes"]:
        assert e2ee.get_int_bytes(case["i"]) == _h(case["out"]), case["i"]


def test_int_bytes_roundtrip_byte2int(e2ee):
    for n in (0, 1, 255, 256, 65536, 2147483647):
        assert byte2int(e2ee.get_int_bytes(n)) == n


def test_generate_aad(e2ee, vec):
    a = vec["e2ee"]["aad"]
    got = e2ee.generate_aad(a["to"], a["from"], a["c"], a["d"], a["e"], a["f"])
    assert got == _h(a["out"])


# ---------------------------------------------------------------- messages

def test_encrypt_v2_deterministic(e2ee, vec):
    g = vec["e2ee"]["gcm_v2"]
    data = g["data_utf8"].encode("utf-8")
    out = e2ee.encrypt_e2ee_message_v2(data, _h(g["gcmKey"]), _h(g["nonce"]), _h(g["aad"]))
    assert out == _h(g["out"]), "AES-256-GCM output must match 本家 byte-for-byte"


def test_decrypt_v2_matches(e2ee, vec):
    """Decrypt the 本家-produced GCM blob via the full V2 path."""
    e = vec["e2ee"]
    g = e["gcm_v2"]
    # chunks: [salt, encData(ct+tag), nonce, sKeyId, rKeyId]
    chunks = [
        _h(g["salt"]),
        _h(g["out"]),
        _h(g["nonce"]),
        e2ee.get_int_bytes(3),
        e2ee.get_int_bytes(7),
    ]
    # AAD was built with to="u-to", from="u-from"; keys derive from shared secret.
    dec = e2ee.decrypt_e2ee_message_v2(
        "u-to", "u-from", chunks, _h(e["privA"]), _h(e["pubB"]), 2, 0
    )
    assert dec["text"] == json.loads(g["data_utf8"])["text"]


def test_decrypt_v1_matches(e2ee, vec):
    e = vec["e2ee"]
    v1 = e["cbc_v1"]
    chunks = [
        _h(v1["salt"]),
        _h(v1["ciphertext"]),
        os.urandom(12),
        e2ee.get_int_bytes(3),
        e2ee.get_int_bytes(7),
    ]
    dec = e2ee.decrypt_e2ee_message_v1(chunks, _h(e["privA"]), _h(e["pubB"]))
    assert dec["text"] == json.loads(v1["plain_utf8"])["text"]


def test_v1_key_iv_derivation(e2ee, vec):
    e = vec["e2ee"]
    v1 = e["cbc_v1"]
    shared = _h(e["shared"])
    salt = _h(v1["salt"])
    assert e2ee.get_sha256_sum(shared, salt, "Key") == _h(v1["aesKey"])
    assert e2ee.xor(e2ee.get_sha256_sum(shared, salt, "IV")) == _h(v1["aesIv"])


# ---------------------------------------------------------------- media

def test_derive_key_material(e2ee, vec):
    k = vec["e2ee"]["keyMaterial"]
    enc_key, mac_key, nonce = e2ee.derive_key_material(_h(k["input"]))
    assert enc_key == _h(k["encKey"])
    assert mac_key == _h(k["macKey"])
    assert nonce == _h(k["nonce"])


def test_encrypt_by_key_material_deterministic(e2ee, vec):
    k = vec["e2ee"]["keyMaterial"]
    r = e2ee.encrypt_by_key_material(k["raw_utf8"].encode("utf-8"), _h(k["input"]))
    assert r["keyMaterial"] == k["keyMaterial_b64"]
    assert r["encryptedData"] == _h(k["encryptedData"]), "media enc must match 本家"


def test_decrypt_by_key_material_matches(e2ee, vec):
    k = vec["e2ee"]["keyMaterial"]
    raw = e2ee.decrypt_by_key_material(_h(k["encryptedData"]), k["keyMaterial_b64"])
    assert raw.decode("utf-8") == k["raw_utf8"]


def test_sign_data(e2ee, vec):
    s = vec["e2ee"]["signData"]
    assert e2ee.sign_data(_h(s["data"]), _h(s["key"])) == _h(s["out"])
