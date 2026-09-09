#!/usr/bin/env python3
"""linepy.helpers.talk.

This module was dead for its whole life: it lived at linepy/helpers.py while
linepy/helpers/ shadowed it, so nothing could import it and nobody noticed it
called an API that does not exist. These tests exist because it is reachable
now.
"""

import os
import tempfile

import pytest

from linepy.base import BaseClient
from linepy.helpers.talk import reply_message, reply_target, send_chat_message
from linepy.models import Chat, Message

ME = "u" + "0" * 32
OTHER = "u" + "1" * 32
GROUP = "c" + "2" * 32
ROOM = "r" + "3" * 32


@pytest.fixture
def client():
    client = BaseClient(
        device="DESKTOPMAC", storage=os.path.join(tempfile.mkdtemp(), "s.json")
    )
    client.mid = ME
    client.sent = []
    client.send_message = lambda **kw: client.sent.append(kw) or {"ok": True}
    return client


def _message(sender, to, message_id="MSG1"):
    return Message.from_dict({"1": sender, "2": to, "4": message_id})


def test_reachable_from_the_helpers_package():
    """The package used to shadow the module entirely."""
    from linepy import helpers

    assert helpers.reply_message is reply_message
    assert helpers.send_chat_message is send_chat_message


@pytest.mark.parametrize("chat", [GROUP, ROOM])
def test_group_and_room_replies_go_back_to_the_chat(client, chat):
    assert reply_target(client, _message(OTHER, chat)) == chat


def test_one_to_one_reply_goes_to_the_sender(client):
    """In a 1:1 chat `to` is us, so replying means answering `from`."""
    assert reply_target(client, _message(OTHER, ME)) == OTHER


def test_reply_to_our_own_message_goes_to_the_recipient(client):
    assert reply_target(client, _message(ME, OTHER)) == OTHER


@pytest.mark.parametrize(
    "sender,to", [(None, GROUP), (OTHER, None), (None, None)]
)
def test_reply_target_is_none_without_both_ends(client, sender, to):
    assert reply_target(client, _message(sender, to)) is None


def test_reply_message_quotes_the_original(client):
    result = reply_message(client, _message(OTHER, GROUP, "MSG42"), "hi")

    assert result == {"ok": True}
    assert client.sent == [
        {"to": GROUP, "text": "hi", "related_message_id": "MSG42"}
    ]


def test_reply_message_uses_the_id_field_the_model_actually_has(client):
    """Message names it `id_`; the old helper read `message.id`."""
    message = _message(OTHER, GROUP, "MSG7")

    assert not hasattr(message, "id")
    assert message.id_ == "MSG7"

    reply_message(client, message, "hi")
    assert client.sent[0]["related_message_id"] == "MSG7"


def test_reply_message_returns_none_when_there_is_no_target(client):
    assert reply_message(client, _message(None, None), "hi") is None
    assert client.sent == []


def test_send_chat_message(client):
    send_chat_message(client, Chat.from_dict({"2": GROUP}), "yo")

    assert client.sent == [{"to": GROUP, "text": "yo"}]


def test_send_chat_message_without_a_mid(client):
    assert send_chat_message(client, Chat.from_dict({}), "yo") is None
    assert client.sent == []


def test_helpers_send_through_the_client_not_the_generated_service(client):
    """BaseClient.send_message takes to=/text=; TalkService takes (seq, message).

    The old helper called the latter with the former's keywords, so its first
    real call would have been a TypeError.
    """
    import inspect

    service_params = set(
        inspect.signature(type(client).send_message).parameters
    )
    assert {"to", "text", "related_message_id"} <= service_params

    generated = set(inspect.signature(client.talk.send_message).parameters)
    assert generated == {"seq", "message"}
