#!/usr/bin/env python3
"""PollingManager, and the reply targeting it used to exercise.

The previous version of this file tested a `Client._handle_operation` and a
`Message(dump, client)` wrapper that no longer exist -- it had been failing
on every run for a long time. It is rewritten here against the current API:
PollingManager's worker/queue plumbing (which had no coverage at all) and
TalkMessage's reply targeting (which had coverage for group chats only, and
was wrong for 1:1).
"""

import os
import queue
import tempfile

import pytest

from linepy.base import BaseClient
from linepy.realtime.message import TalkMessage, reply_target
from linepy.realtime.polling import ChatWorker, DispatchWorker, PollingManager

ME = "u" + "0" * 32
OTHER = "u" + "1" * 32
GROUP = "c" + "2" * 32
ROOM = "r" + "3" * 32
CHAT = "m" + "4" * 32


@pytest.fixture
def client():
    client = BaseClient(
        device="DESKTOPMAC", storage=os.path.join(tempfile.mkdtemp(), "s.json")
    )
    client.mid = ME
    return client


# ---- reply targeting -------------------------------------------------------


@pytest.mark.parametrize(
    "sender,to,expected",
    [
        # Group / room: reply goes to the chat.
        (OTHER, GROUP, GROUP),
        (OTHER, ROOM, ROOM),
        (ME, GROUP, GROUP),
        # 1:1 we received: `to` is us, so answer the sender.
        (OTHER, ME, OTHER),
        # 1:1 we sent: `to` is already the other party.
        (ME, OTHER, OTHER),
        # Missing sender: nothing better than `to`.
        (None, OTHER, OTHER),
        (None, None, None),
    ],
)
def test_reply_target(sender, to, expected):
    assert reply_target(sender, to, ME) == expected


def _talk_message(client, sender, to):
    return TalkMessage(
        {"from_": sender, "to": to, "id_": "MSG1", "text": "hi"}, client
    )


def test_reply_in_a_group_goes_to_the_group(client):
    sent = []
    client.send_message = lambda to, text, **kw: sent.append((to, text)) or {}

    _talk_message(client, OTHER, GROUP).reply("pong")

    assert sent == [(GROUP, "pong")]


def test_reply_in_a_one_to_one_goes_to_the_sender(client):
    """reply() used to send to `to`, which in a received 1:1 message is us."""
    sent = []
    client.send_message = lambda to, text, **kw: sent.append((to, text)) or {}

    message = _talk_message(client, OTHER, ME)

    assert message.reply_target == OTHER
    message.reply("pong")
    assert sent == [(OTHER, "pong")]


def test_reply_quotes_the_original(client):
    sent = []
    client.send_message = lambda to, text, **kw: sent.append(kw) or {}

    _talk_message(client, OTHER, GROUP).reply("pong")

    assert sent == [{"related_message_id": "MSG1"}]


# ---- PollingManager --------------------------------------------------------


class _Response:
    def __init__(self, sync_token=None, events=(), continuation_token=None):
        self.sync_token = sync_token
        self.events = list(events)
        self.continuation_token = continuation_token


def test_dispatch_worker_drains_the_queue():
    q = queue.Queue()
    seen = []
    worker = DispatchWorker(q, lambda service, event: seen.append((service, event)))
    worker.start()
    try:
        q.put((3, "A"))
        q.put((3, "B"))
        q.join()
    finally:
        worker.stop()
        worker.join(timeout=2)

    assert seen == [(3, "A"), (3, "B")]


def test_chat_worker_fetches_with_the_stored_sync_token(client):
    calls = []

    def fetch(**kwargs):
        calls.append(kwargs)
        return _Response(sync_token="TOK2", events=["E1"])

    client.square.fetchSquareChatEvents = fetch
    client.token_manager.set_square_sync_token(CHAT, "TOK1")

    q = queue.Queue()
    worker = ChatWorker(client, CHAT, q, client.token_manager, fetch_type=2)
    worker._fetch_once()

    assert calls[0]["syncToken"] == "TOK1"
    assert calls[0]["squareChatMid"] == CHAT
    assert q.get_nowait() == (3, "E1")


def test_chat_worker_persists_the_new_sync_token(client):
    client.square.fetchSquareChatEvents = lambda **kw: _Response(sync_token="TOK2")
    client.token_manager.set_square_sync_token(CHAT, "TOK1")

    worker = ChatWorker(client, CHAT, queue.Queue(), client.token_manager)
    worker._fetch_once()

    assert client.token_manager.get_square_sync_token(CHAT) == "TOK2"


def test_chat_worker_initialises_a_missing_token(client):
    calls = []

    def fetch(*args, **kwargs):
        # _init_token passes the chat mid positionally.
        calls.append({"args": args, **kwargs})
        return _Response(sync_token="TOK1")

    client.square.fetchSquareChatEvents = fetch
    worker = ChatWorker(client, CHAT, queue.Queue(), client.token_manager)

    assert worker.sync_token is None
    worker._fetch_once()  # no token yet -> initialises instead of fetching

    assert calls[0]["limit"] == 1
    assert worker.sync_token == "TOK1"
    assert client.token_manager.get_square_sync_token(CHAT) == "TOK1"


def test_manager_tracks_watched_chats_before_start(client):
    manager = PollingManager(client)
    manager.add_watched_chat(CHAT)
    manager.add_watched_chat(CHAT)  # idempotent

    assert manager.watched_chats == [CHAT]
    assert manager._workers == {}  # not running, so no threads yet


def test_manager_stop_is_safe_before_start(client):
    PollingManager(client).stop()
