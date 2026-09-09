#!/usr/bin/env python3
"""Event dispatcher tests (Phase 3 Step 10)."""

import os
import tempfile

import pytest

from linepy.base import BaseClient
from linepy.realtime.dispatcher import EventDispatcher
from linepy.realtime.message import SquareMessage, TalkMessage


@pytest.fixture
def client():
    c = BaseClient(device="DESKTOPMAC", storage=os.path.join(tempfile.mkdtemp(), "s.json"))
    c.mid = "u" + "a" * 32
    return c


def test_receive_message_emits_talkmessage(client):
    got = []
    client.on("message", lambda m: got.append(m))
    d = EventDispatcher(client)
    op = {"type": "RECEIVE_MESSAGE",
          "message": {"from": "u" + "b" * 32, "to": "c" + "1" * 32,
                      "id_": "m1", "text": "hi", "content_type": 0,
                      "content_metadata": {}}}
    d.dispatch_talk_operation(op)
    assert len(got) == 1
    assert isinstance(got[0], TalkMessage)
    assert got[0].text == "hi"


def test_numeric_optype(client):
    got = []
    client.on("message", lambda m: got.append(m))
    d = EventDispatcher(client)
    op = {"type": 26, "message": {"from": "u1", "to": "c1", "id_": "m2",
                                  "text": "yo", "content_type": 0, "content_metadata": {}}}
    d.dispatch_talk_operation(op)
    assert got and got[0].text == "yo"


def test_edit_message_event(client):
    got = []
    client.on("edit", lambda m: got.append(m))
    d = EventDispatcher(client)
    d.dispatch_talk_operation({"type": 159, "message": {"id_": "m3", "text": "e"}})
    assert got and got[0].id == "m3"


def test_dispatch_isolation_on_bad_message(client):
    """A callback raising must not propagate out of the dispatcher."""
    errors = []
    client.on("message", lambda m: (_ for _ in ()).throw(RuntimeError("boom")))
    client.on("error", lambda e: errors.append(e))
    d = EventDispatcher(client)
    # Should not raise
    d.dispatch_talk_operation({"type": 26, "message": {"id_": "x", "content_metadata": {}}})
    assert errors and isinstance(errors[0], RuntimeError)


def test_e2ee_message_decrypted_on_receive(client):
    import base64
    # We are the receiver; sender is frm.
    our_priv = os.urandom(32)
    our_pub = client.e2ee.public_from_private(our_priv)
    client.e2ee.save_self_key_data(7, {"keyId": 7, "privKey": base64.b64encode(our_priv).decode(),
                                       "pubKey": base64.b64encode(our_pub).decode()})
    sender_priv = os.urandom(32)
    sender_pub = client.e2ee.public_from_private(sender_priv)
    frm = "u" + "b" * 32
    client.token_manager.save_user_public_key(
        f"{frm}:3", {"key": base64.b64encode(sender_pub).decode(), "keyId": 3})

    key_data = client.e2ee.generate_shared_secret(sender_priv, our_pub)
    chunks = client.e2ee.encrypt_e2ee_text_message(3, 7, key_data, 2, "秘密", client.mid, frm)

    got = []
    client.on("message", lambda m: got.append(m))
    d = EventDispatcher(client)
    op = {"type": 26, "message": {"from": frm, "to": client.mid, "id_": "m9",
                                  "contentType": "NONE",
                                  "content_metadata": {"e2eeVersion": "2"},
                                  "chunks": chunks}}
    d.dispatch_talk_operation(op)
    assert got and got[0].text == "秘密"


def test_square_notification_message(client):
    got = []
    client.on("square:message", lambda m: got.append(m))
    d = EventDispatcher(client)
    event = {"type": "NOTIFICATION_MESSAGE",
             "payload": {"notificationMessage": {"squareMessage": {"message": {
                 "from": "p" + "x" * 32, "to": "m" + "9" * 32, "id_": "sq1",
                 "text": "hello sq", "content_type": 0, "content_metadata": {}}}}}}
    d.dispatch_square_event(event)
    assert got and isinstance(got[0], SquareMessage)
    assert got[0].text == "hello sq"
