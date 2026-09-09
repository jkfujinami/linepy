#!/usr/bin/env python3
"""
High-level send_message orchestration tests (Phase 2 Step 5.2).

Network is mocked; we assert the Thrift request struct and the E2EE / reply /
failover behaviour match the 本家 (linejs) sendMessage semantics.
"""

import base64
import os
import tempfile

import pytest

from linepy.base import BaseClient
from linepy.protocol.thrift import CompactReader


class _FakePub:
    key_id = 5

    def __init__(self, key_data):
        self.key_data = key_data


class _FakeNeg:
    spec_version = 2

    def __init__(self, key_data):
        self.public_key = _FakePub(key_data)


class _FakeTalk:
    def __init__(self, peer_pub_b64):
        self._peer = peer_pub_b64

    def negotiate_e2_ee_public_key(self, mid=None):
        return _FakeNeg(self._peer)


@pytest.fixture
def client():
    c = BaseClient(device="DESKTOPMAC", storage=os.path.join(tempfile.mkdtemp(), "s.json"))
    c.mid = "u" + "a" * 32
    return c


def _capture(client):
    box = {}

    def fake_request(path, data, protocol=4, timeout=None, **kw):
        box["path"] = path
        r = CompactReader(data)
        box["method"], _t, _s = r.read_message_begin()
        box["struct"] = r.read_struct()
        return {"ok": True}

    client.request.request = fake_request
    return box


def test_plain_text_build(client):
    box = _capture(client)
    client.send_message("u" + "0" * 32, "hello 本家")
    msg = box["struct"][2]
    assert box["method"] == "sendMessage"
    assert box["path"] == "/S4"
    assert msg[2] == "u" + "0" * 32
    assert msg[10] == "hello 本家"
    assert msg[15] == 0


def test_reply_metadata(client):
    box = _capture(client)
    client.send_message("c" + "1" * 32, "re", related_message_id="987")
    msg = box["struct"][2]
    assert msg[21] == "987"
    assert msg[22] == 3   # REPLY
    assert msg[24] == 1   # TALK


def test_seq_increments(client):
    box = _capture(client)
    client.send_message("u" + "0" * 32, "a")
    seq1 = box["struct"][1]
    client.send_message("u" + "0" * 32, "b")
    seq2 = box["struct"][1]
    assert seq2 == seq1 + 1


def _setup_e2ee(client, to):
    priv = os.urandom(32)
    pub = client.e2ee.public_from_private(priv)
    client.e2ee.save_self_key_data(
        2, {"keyId": 2, "privKey": base64.b64encode(priv).decode(),
            "pubKey": base64.b64encode(pub).decode()}
    )
    peer_priv = os.urandom(32)
    peer_pub = client.e2ee.public_from_private(peer_priv)
    client.talk = _FakeTalk(base64.b64encode(peer_pub).decode())
    return priv, pub, peer_priv, peer_pub


def test_e2ee_send_builds_decryptable_chunks(client):
    box = _capture(client)
    to = "u" + "b" * 32
    priv, pub, peer_priv, peer_pub = _setup_e2ee(client, to)

    # Capture the exact chunk bytes handed to the transport.
    real_encrypt = client.e2ee.encrypt_e2ee_message
    grabbed = {}

    def spy(to_, data, content_type=0, spec_version=2):
        chunks = real_encrypt(to_, data, content_type, spec_version)
        grabbed["chunks"] = chunks
        return chunks

    client.e2ee.encrypt_e2ee_message = spy

    client.send_message(to, "秘密メッセージ🔐", e2ee=True)
    msg = box["struct"][2]
    assert msg[18] == {"e2eeVersion": "2", "contentType": "0", "e2eeMark": "2"}
    assert len(msg[20]) == 5

    # The recipient must be able to decrypt with shared(peer_priv, our_pub).
    dec = client.e2ee.decrypt_e2ee_message_v2(
        to, client.mid, grabbed["chunks"], peer_priv, pub, 2, 0
    )
    assert dec["text"] == "秘密メッセージ🔐"


def test_e2ee_failover_on_plain_error(client):
    """A plain send failing with an E2EE error auto-retries encrypted."""
    to = "u" + "c" * 32
    _setup_e2ee(client, to)

    calls = {"n": 0}

    class _Err(Exception):
        message = "TalkException: E2EE_RETRY_REQUIRED"

    captured = {}

    def fake_request(path, data, protocol=4, timeout=None, **kw):
        calls["n"] += 1
        r = CompactReader(data)
        _m, _t, _s = r.read_message_begin()
        struct = r.read_struct()
        if calls["n"] == 1:
            # first (plain) attempt fails with an E2EE error
            raise _Err()
        captured["struct"] = struct
        return {"ok": True}

    client.request.request = fake_request
    client.send_message(to, "テスト")  # e2ee unspecified -> should failover
    assert calls["n"] == 2
    assert len(captured["struct"][2][20]) == 5  # retried with chunks


def test_compact_plain_and_e2ee(client):
    from linepy.protocol import compact

    to = "u" + "d" * 32
    _setup_e2ee(client, to)
    seen = {}

    def fake_compact(path, seq_id, body, **kw):
        seen["path"] = path
        seen["body"] = body
        seen["seq"] = seq_id
        # craft a valid success response: bool(1) + i32 seq + i64 msgId + i64 timeMs
        out = bytearray([1])
        compact.write_compact_i32(out, seq_id)
        compact.write_compact_i64(out, 111)
        compact.write_compact_i64(out, 1700000000000)
        return bytes(out)

    client.request.compact_request = fake_compact

    res = client.send_compact_plain_message(to, "compact hi")
    assert seen["path"] == compact.COMPACT_PLAIN_MESSAGE_ENDPOINT
    assert res["sequenceId"] == seen["seq"]
    # frame decodes back to the same bytes shape
    assert seen["body"] == compact.pack_compact_plain_message(seen["seq"], to, "compact hi")

    res2 = client.send_compact_e2ee_message(to=to, text="secret")
    assert seen["path"] == compact.COMPACT_E2EE_MESSAGE_ENDPOINT
    assert res2["messageId"] == 111
