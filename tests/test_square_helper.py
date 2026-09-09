#!/usr/bin/env python3
"""
Tests for linepy.helpers.square.SquareEventData.from_event.

This module still referenced camelCase attribute names (squareChatMid,
sMemberMid, notifiedMarkAsRead, ...) left over from before the model
generator was made to consistently emit snake_case fields (Phase: pydantic
-> dataclass migration). Those attributes don't exist on the current
generated models, so from_event() raised AttributeError for every event.
"""

from linepy.helpers.square import SquareEventData
from linepy.models._generated import (
    SquareEvent,
    SquareEventPayload,
    SquareEventReceiveMessage,
    SquareMessage,
    Message,
    SquareEventNotifiedMarkAsRead,
)


def test_from_event_receive_message():
    msg = Message(from_="u1", text="hello", id_="m100", content_type=0,
                  related_message_id=None, content_metadata={})
    sq_msg = SquareMessage(message=msg)
    recv = SquareEventReceiveMessage(
        square_chat_mid="m-chat", square_message=sq_msg,
        sender_display_name="Taro", square_mid="s-sq",
    )
    payload = SquareEventPayload(receive_message=recv)
    event = SquareEvent(type_=0, payload=payload, sync_token="tok123", created_time=1000)

    data = SquareEventData.from_event(event)
    assert data.square_chat_mid == "m-chat"
    assert data.square_mid == "s-sq"
    assert data.sender_name == "Taro"
    assert data.member_mid == "u1"
    assert data.message_text == "hello"
    assert data.message_id == "m100"
    assert data.sync_token == "tok123"


def test_from_event_receive_message_with_mentions():
    import json

    meta = {"MENTION": json.dumps({"MENTIONEES": ["u9", "u10"]})}
    msg = Message(from_="u1", text="hi @u9", id_="m1", content_type=0, content_metadata=meta)
    recv = SquareEventReceiveMessage(square_chat_mid="c1", square_message=SquareMessage(message=msg))
    event = SquareEvent(type_=0, payload=SquareEventPayload(receive_message=recv))

    data = SquareEventData.from_event(event)
    assert data.mention_mids == ["u9", "u10"]


def test_from_event_notified_mark_as_read():
    read = SquareEventNotifiedMarkAsRead(square_chat_mid="m-chat2", s_member_mid="u2", message_id="55")
    event = SquareEvent(type_=6, payload=SquareEventPayload(notified_mark_as_read=read))

    data = SquareEventData.from_event(event)
    assert data.square_chat_mid == "m-chat2"
    assert data.member_mid == "u2"
    assert data.message_id == "55"


def test_from_event_no_payload_returns_bare_data():
    event = SquareEvent(type_=99, payload=None)
    data = SquareEventData.from_event(event)
    assert data.square_event_type == 99
    assert data.member_mid is None
