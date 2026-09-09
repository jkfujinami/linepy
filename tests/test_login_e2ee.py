#!/usr/bin/env python3
"""Login E2EE key bootstrap tests (audit gap #2).

Covers decode_e2ee_key_v1 wiring (keychain decrypt + persist) and the
register-if-absent fallback.
"""

import base64
import os
import tempfile

import pytest

from linepy.base import BaseClient
from linepy.crypto.primitives import AES
from linepy.protocol.thrift import CompactWriter, _write_struct


@pytest.fixture
def client():
    return BaseClient(device="DESKTOPMAC", storage=os.path.join(tempfile.mkdtemp(), "s.json"))


def _make_e2ee_info(e, secret_pub, key_id, kc_priv, kc_pub):
    server_priv = os.urandom(32)
    server_pub = e.public_from_private(server_priv)
    entry = [[8, 2, key_id], [11, 4, kc_pub], [11, 5, kc_priv]]
    w = CompactWriter()
    _write_struct(w, [[15, 1, [12, [entry]]]])
    struct_bytes = w.get_bytes()
    if not struct_bytes or struct_bytes[-1] != 0:
        struct_bytes += b"\x00"
    struct_bytes += b"\x00" * ((16 - len(struct_bytes) % 16) % 16)
    shared = e.generate_shared_secret(server_priv, secret_pub)
    ak = e.get_sha256_sum(shared, "Key")
    iv = e.xor(e.get_sha256_sum(shared, "IV"))
    enc = AES.new(ak, AES.MODE_CBC, iv).encrypt(struct_bytes)
    return {
        "keyId": key_id,
        "publicKey": base64.b64encode(server_pub).decode(),
        "encryptedKeyChain": base64.b64encode(enc).decode(),
        "e2eeVersion": 2,
    }


def test_decode_e2ee_key_v1_persists_keychain(client):
    e = client.e2ee
    secret = os.urandom(32)
    secret_pub = e.public_from_private(secret)
    kc_priv = os.urandom(32)
    kc_pub = e.public_from_private(kc_priv)

    info = _make_e2ee_info(e, secret_pub, 42, kc_priv, kc_pub)
    result = e.decode_e2ee_key_v1(info, secret)
    assert result["keyId"] == 42
    assert result["privKey"] == kc_priv and result["pubKey"] == kc_pub

    stored = e.get_self_key_data_by_key_id(42)
    assert stored and base64.b64decode(stored["privKey"]) == kc_priv


def test_bootstrap_decodes_e2ee_info(client):
    """``Login._bootstrap_e2ee_keys`` (matches 本家's requestSQR/requestSQR2
    post-login "decodeE2EEKeyV1 or registerE2EEKeyPair" step)."""
    e = client.e2ee
    secret = os.urandom(32)
    secret_pub = e.public_from_private(secret)
    kc_priv = os.urandom(32)
    kc_pub = e.public_from_private(kc_priv)
    info = _make_e2ee_info(e, secret_pub, 7, kc_priv, kc_pub)

    client.login_handler._bootstrap_e2ee_keys(info, secret)
    stored = e.get_self_key_data_by_key_id(7)
    assert stored and base64.b64decode(stored["privKey"]) == kc_priv


def test_bootstrap_registers_when_no_e2ee_info(client):
    calls = []

    class _Talk:
        def register_e2_ee_public_key(self, req_seq=None, public_key=None):
            calls.append(public_key)

            class _R:
                key_id = 99
            return _R()

    client.talk = _Talk()
    assert client.e2ee.get_self_key_data() is None
    client.login_handler._bootstrap_e2ee_keys(None, os.urandom(32))
    # a keypair was registered and persisted
    assert calls, "register_e2ee_public_key should be called"
    assert client.e2ee.get_self_key_data() is not None
