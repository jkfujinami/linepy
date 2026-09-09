#!/usr/bin/env python3
"""E2EE group-key negotiation / unwrap / register tests (audit gap #3)."""

import base64
import os
import tempfile

import pytest

from linepy.base import BaseClient
from linepy.crypto.primitives import AES


@pytest.fixture
def client():
    c = BaseClient(device="DESKTOPMAC", storage=os.path.join(tempfile.mkdtemp(), "s.json"))
    c.mid = "u" + "a" * 32
    return c


def _b64(b):
    return base64.b64encode(b).decode()


class _GSK:
    def __init__(self, creator, creator_key_id, receiver_key_id, group_key_id, enc):
        self.creator = creator
        self.creator_key_id = creator_key_id
        self.receiver_key_id = receiver_key_id
        self.group_key_id = group_key_id
        self.encrypted_shared_key = _b64(enc)


def test_unwrap_group_shared_key(client):
    e = client.e2ee
    self_priv = os.urandom(32)
    self_pub = e.public_from_private(self_priv)
    e.save_self_key_data(4, {"keyId": 4, "privKey": _b64(self_priv), "pubKey": _b64(self_pub)})

    creator = "u" + "c" * 32
    creator_priv = os.urandom(32)
    creator_pub = e.public_from_private(creator_priv)
    client.token_manager.save_user_public_key(f"{creator}:9", {"key": _b64(creator_pub), "keyId": 9})

    group_priv = os.urandom(32)
    shared = e.generate_shared_secret(creator_priv, self_pub)
    ak = e.get_sha256_sum(shared, "Key")
    iv = e.xor(e.get_sha256_sum(shared, "IV"))
    enc = AES.new(ak, AES.MODE_CBC, iv).encrypt(group_priv)

    class _Talk:
        def get_e2_ee_group_shared_key(self, **kw):
            raise Exception("NOT_FOUND")

        def get_last_e2_ee_group_shared_key(self, key_version=None, chat_mid=None):
            return _GSK(creator, 9, 4, 11, enc)

    client.talk = _Talk()
    priv, key_id = client.e2ee._get_group_key("c" + "1" * 32, 11)
    assert priv == group_priv
    assert key_id == 11
    # cached for reuse (no second server call needed)
    cached = client.token_manager.get_group_key("c" + "1" * 32 + ":11")
    assert cached and base64.b64decode(cached["privKey"]) == group_priv


def test_group_message_end_to_end(client):
    e = client.e2ee
    chat = "c" + "1" * 32
    # both members share the same group private key
    group_priv = os.urandom(32)
    client.token_manager.save_group_key(f"{chat}:11", {"privKey": _b64(group_priv), "keyId": 11})

    # self key so decrypt can read self pubKey
    self_priv = os.urandom(32)
    self_pub = e.public_from_private(self_priv)
    e.save_self_key_data(4, {"keyId": 4, "privKey": _b64(self_priv), "pubKey": _b64(self_pub)})

    sender = "u" + "b" * 32
    sender_priv = os.urandom(32)
    sender_pub = e.public_from_private(sender_priv)
    client.token_manager.save_user_public_key(f"{sender}:3", {"key": _b64(sender_pub), "keyId": 3})

    key_data = e.generate_shared_secret(group_priv, sender_pub)
    chunks = e.encrypt_e2ee_text_message(3, 11, key_data, 2, "グループ秘密", chat, sender)
    msg = {"from": sender, "to": chat, "contentType": "NONE",
           "contentMetadata": {"e2eeVersion": "2"}, "chunks": chunks}
    text, _meta = e.decrypt_e2ee_text_message(msg)
    assert text == "グループ秘密"


def test_try_register_group_key(client):
    e = client.e2ee
    self_priv = os.urandom(32)
    self_pub = e.public_from_private(self_priv)
    e.save_self_key_data(4, {"keyId": 4, "privKey": _b64(self_priv), "pubKey": _b64(self_pub)})

    member = "u" + "d" * 32
    member_pub = e.public_from_private(os.urandom(32))

    class _Key:
        def __init__(self, key_id, key_data):
            self.key_id = key_id
            self.key_data = key_data

    registered = {}

    class _Talk:
        def get_last_e2_ee_public_keys(self, chat_mid=None):
            return {client.mid: _Key(4, _b64(self_pub)), member: _Key(2, _b64(member_pub))}

        def register_e2_ee_group_key(self, key_version=None, chat_mid=None, members=None,
                                     key_ids=None, encrypted_shared_keys=None):
            registered.update(dict(members=members, key_ids=key_ids,
                                   n=len(encrypted_shared_keys)))
            return {"ok": True}

    client.talk = _Talk()
    client.e2ee.try_register_e2ee_group_key("c" + "9" * 32)
    assert set(registered["members"]) == {client.mid, member}
    assert registered["n"] == 2  # one encrypted key per member
