#!/usr/bin/env python3
"""
OBS E2EE media tests (Phase 2 Step 6).

The X-Talk-Meta known-answer vector was captured from 本家 (linejs) by running
``writeStruct([[11,4,id],[15,27,[12,[]]]], TBinaryProtocol)`` and the base64
wrapping in obs mod.ts:

    id = "m1234567890"
    inner_hex = 0b00040000000b6d313233343536373839300f001b0c0000000000
    talkMeta  = eyJtZXNzYWdlIjoiQ3dBRUFBQUFDMjB4TWpNME5UWTNPRGt3RHdBYkRBQUFBQUFBIn0=
"""

import base64
import json
import os
import tempfile

import pytest

from linepy.obs import build_talk_meta, _write_binary_struct, E2EE_MEDIA_TYPESET
from linepy.base import BaseClient


_ID = "m1234567890"
_INNER_HEX = "0b00040000000b6d313233343536373839300f001b0c0000000000"
_TALK_META = "eyJtZXNzYWdlIjoiQ3dBRUFBQUFDMjB4TWpNME5UWTNPRGt3RHdBYkRBQUFBQUFBIn0="


def test_binary_struct_matches_honmoto():
    inner = _write_binary_struct([[11, 4, _ID], [15, 27, [12, []]]])
    assert inner.hex() == _INNER_HEX


def test_build_talk_meta_matches_honmoto():
    assert build_talk_meta(_ID) == _TALK_META


def test_talk_meta_decodes_roundtrip():
    payload = json.loads(base64.b64decode(build_talk_meta(_ID)))
    inner = base64.b64decode(payload["message"])
    assert inner.hex() == _INNER_HEX


def test_typeset():
    assert E2EE_MEDIA_TYPESET == {
        "image": ("emi", 1),
        "video": ("emv", 2),
        "audio": ("ema", 3),
        "file": ("emf", 14),
        "gif": ("emi", 1),
    }


def _client():
    c = BaseClient(device="DESKTOPMAC", storage=os.path.join(tempfile.mkdtemp(), "s.json"))
    c.mid = "u" + "a" * 32
    c.auth_token = "token"
    return c


def test_upload_media_by_e2ee_flow(monkeypatch):
    """Upload encrypts with keyMaterial, uploads to the right OBS paths, and
    sends an E2EE data message carrying SID/OID/keyMaterial."""
    import base64 as b64
    c = _client()
    to = "u" + "b" * 32

    # self + peer keys for E2EE
    priv = os.urandom(32)
    pub = c.e2ee.public_from_private(priv)
    c.e2ee.save_self_key_data(2, {"keyId": 2, "privKey": b64.b64encode(priv).decode(),
                                  "pubKey": b64.b64encode(pub).decode()})
    peer_pub = c.e2ee.public_from_private(os.urandom(32))

    class _Neg:
        spec_version = 2

        class public_key:
            key_id = 5
            key_data = b64.b64encode(peer_pub).decode()

    class _Talk:
        def negotiate_e2_ee_public_key(self, mid=None):
            return _Neg()

    c.talk = _Talk()

    uploads = []

    def fake_upload(obs_path, data, params):
        uploads.append((obs_path, len(data), dict(params)))
        return {"objId": "OBJ123", "objHash": "h", "headers": {}}

    c.obs._upload_object_for_service = fake_upload

    sent = {}

    def fake_send(**kw):
        sent.update(kw)
        return {"ok": True}

    c.send_message = fake_send

    c.obs.upload_media_by_e2ee(b"raw-image-bytes", "image", to, filename="pic.jpg")

    # main + preview upload
    assert uploads[0][0] == "talk/emi/reqid-" + uploads[0][0].split("reqid-")[1]
    assert uploads[1][0] == "talk/emi/OBJ123__ud-preview"
    assert sent["content_type"] == 1
    assert sent["content_metadata"]["SID"] == "emi"
    assert sent["content_metadata"]["OID"] == "OBJ123"
    assert sent["content_metadata"]["e2eeVersion"] == "2"
    assert len(sent["chunks"]) == 5


def test_download_media_by_e2ee_roundtrip(monkeypatch):
    """A message whose chunks carry keyMaterial+fileName is downloaded and
    decrypted back to the original bytes."""
    import base64 as b64
    c = _client()
    to = c.mid  # receiving on our own account (isSelf path uses receiver key)
    frm = "u" + "b" * 32

    # Set up keys: we are receiver (to == our mid); sender is frm.
    our_priv = os.urandom(32)
    our_pub = c.e2ee.public_from_private(our_priv)
    c.e2ee.save_self_key_data(7, {"keyId": 7, "privKey": b64.b64encode(our_priv).decode(),
                                  "pubKey": b64.b64encode(our_pub).decode()})
    sender_priv = os.urandom(32)
    sender_pub = c.e2ee.public_from_private(sender_priv)
    c.token_manager.save_user_public_key(
        f"{frm}:3", {"key": b64.b64encode(sender_pub).decode(), "keyId": 3})

    # Original media + its encryption.
    raw = b"hello media payload 0123456789"
    enc = c.e2ee.encrypt_by_key_material(raw)
    key_material = enc["keyMaterial"]
    encrypted_blob = enc["encryptedData"]

    # Build an E2EE data message: sender encrypts {keyMaterial,fileName} to us.
    key_data = c.e2ee.generate_shared_secret(sender_priv, our_pub)
    payload = {"keyMaterial": key_material, "fileName": "pic.jpg"}
    chunks = c.e2ee.encrypt_e2ee_message_by_data(3, 7, key_data, 2, payload, to, frm, 1)

    message = {
        "from": frm, "to": to, "id_": "m999",
        "contentType": 1,
        "contentMetadata": {"e2eeVersion": "2", "SID": "emi", "OID": "OBJ123"},
        "chunks": chunks,
    }

    class _Resp:
        content = encrypted_blob

        def raise_for_status(self):
            pass

    captured = {}

    def fake_get(url, headers=None):
        captured["url"] = url
        captured["headers"] = headers
        return _Resp()

    c.request._http.get = fake_get

    out = c.obs.download_media_by_e2ee(message)
    assert out["fileName"] == "pic.jpg"
    assert out["data"] == raw
    assert captured["headers"]["X-Talk-Meta"] == build_talk_meta("m999")
    assert captured["url"].endswith("/talk/emi")


