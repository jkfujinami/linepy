#!/usr/bin/env python3
"""OO message wrapper tests (Phase 2 Step 7)."""

import json
import types

import pytest

from linepy.message import TalkMessage, SquareMessage


class _StubClient:
    def __init__(self):
        self.mid = "u" + "a" * 32
        self.square_mid = "p" + "s" * 32
        self.calls = []
        client = self

        class _Talk:
            def send_chat_checked(self, seq=None, chat_mid=None, last_message_id=None, **kw):
                client.calls.append(("read", chat_mid, last_message_id))

            def unsend_message(self, seq=None, message_id=None):
                client.calls.append(("unsend", message_id))

            def create_chat_room_announcement(self, req_seq=None, chat_room_mid=None, **kw):
                client.calls.append(("announce", chat_room_mid))
                return {"ok": True}

            def _call(self, method, params, response_model=None):
                client.calls.append(("react_talk", method))
                return None

        class _Square:
            def sendSquareMessage(self, chat, text, relatedMessageId=None, **kw):
                client.calls.append(("sq_reply", chat, text, relatedMessageId))
                return {"to": chat, "id_": "sqNEW", "text": text}

            def reactToMessage(self, chat, mid, rtype):
                client.calls.append(("sq_react", chat, mid, rtype))
                return {"ok": True}

            def unsendSquareMessage(self, chat, mid):
                client.calls.append(("sq_unsend", chat, mid))
                return {"ok": True}

        class _Obs:
            def download_media_by_e2ee(self, raw):
                client.calls.append(("dl_e2ee",))
                return {"data": b"MEDIA", "fileName": "f.bin"}

            def download_message_data(self, message_id, is_preview=False, is_square=False):
                client.calls.append(("dl_plain", message_id, is_square))
                return {"data": b"PLAIN", "fileName": "p.bin"}

        self.talk = _Talk()
        self.square = _Square()
        self.obs = _Obs()
        self._seq = 0

    def get_reqseq(self):
        self._seq += 1
        return self._seq

    def send_message(self, to, text, related_message_id=None, **kw):
        self.calls.append(("send", to, text, related_message_id))
        return {"to": to, "id_": "newid", "text": text}


@pytest.fixture
def client():
    return _StubClient()


def _talk_msg(client, **over):
    raw = {"from": "u" + "b" * 32, "to": "c" + "1" * 32, "id_": "m100",
           "text": "hi", "content_type": 0, "content_metadata": {}}
    raw.update(over)
    return TalkMessage(raw, client)


def test_talk_fields(client):
    m = _talk_msg(client)
    assert m.id == "m100" and m.to == "c" + "1" * 32
    assert m.sender_mid == "u" + "b" * 32
    assert m.text == "hi"


def test_talk_reply(client):
    m = _talk_msg(client)
    r = m.reply("pong")
    assert ("send", m.to, "pong", "m100") in client.calls
    assert isinstance(r, TalkMessage) and r.text == "pong"


def test_talk_read_unsend_react_announce(client):
    m = _talk_msg(client)
    m.read()
    m.unsend()
    m.react(3)
    m.announce()
    kinds = [c[0] for c in client.calls]
    assert kinds == ["read", "unsend", "react_talk", "announce"]
    assert ("read", m.to, "m100") in client.calls
    assert ("unsend", "m100") in client.calls


def test_talk_is_my_message(client):
    mine = _talk_msg(client, **{"from": client.mid})
    other = _talk_msg(client)
    assert mine.is_my_message() is True
    assert other.is_my_message() is False


def test_talk_get_data_e2ee(client):
    # message with chunks -> E2EE download path
    m = _talk_msg(client, content_type=1, chunks=[b"x"] * 5)
    assert m.get_data() == b"MEDIA"
    assert ("dl_e2ee",) in client.calls


def test_talk_get_data_plain(client):
    # message without chunks -> plain download (isSquare=False)
    m = _talk_msg(client, content_type=1)
    assert m.get_data() == b"PLAIN"
    assert ("dl_plain", "m100", False) in client.calls


def test_square_get_data_is_plain(client):
    m = _sq_msg(client, content_type=1)
    assert m.get_data() == b"PLAIN"
    # Square media must be downloaded as plain OBS (isSquare=True), never E2EE.
    assert ("dl_plain", "sq1", True) in client.calls
    assert ("dl_e2ee",) not in client.calls


def test_get_mentions_and_sticker():
    client = _StubClient()
    meta = {
        "MENTION": json.dumps({"MENTIONEES": [{"S": "0", "E": "5", "M": "u1"}]}),
        "STKID": "12345",
    }
    m = _talk_msg(client, content_metadata=meta)
    mentions = m.get_mentions()
    assert mentions and mentions[0]["M"] == "u1"
    assert m.get_sticker_url().endswith("/12345/iPhone/sticker.png")


def _sq_msg(client, **over):
    raw = {"from": "p" + "x" * 32, "to": "m" + "9" * 32, "id_": "sq1",
           "text": "yo", "content_type": 0, "content_metadata": {}}
    raw.update(over)
    return SquareMessage(raw, client)


def test_square_reply_react_unsend(client):
    m = _sq_msg(client)
    r = m.reply("re")
    assert ("sq_reply", m.square_chat_mid, "re", "sq1") in client.calls
    assert isinstance(r, SquareMessage)

    m.react(4)
    assert ("sq_react", m.square_chat_mid, "sq1", 4) in client.calls

    m.unsend()
    assert ("sq_unsend", m.square_chat_mid, "sq1") in client.calls


def test_square_delete_is_unsend(client):
    m = _sq_msg(client)
    m.delete()
    assert ("sq_unsend", m.square_chat_mid, "sq1") in client.calls


def test_square_is_my_message(client):
    mine = _sq_msg(client, **{"from": client.square_mid})
    assert mine.is_my_message() is True
