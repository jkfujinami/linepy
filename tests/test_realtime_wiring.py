#!/usr/bin/env python3
"""Regression tests for the PUSH / polling wiring on Client and BaseClient.

Each test here pins a defect that used to be silent at import time and only
blew up (or quietly did nothing) once a real PUSH loop was started.
"""

import os
import tempfile

import pytest

from linepy.base import BaseClient
from linepy.client import Client
from linepy.realtime.push import PushManager
from linepy.realtime.push.data import ServiceType


def _storage():
    return os.path.join(tempfile.mkdtemp(), "s.json")


@pytest.fixture
def client():
    return Client(device="DESKTOPMAC", storage=_storage())


@pytest.fixture
def base():
    return BaseClient(device="DESKTOPMAC", storage=_storage())


class _FakePush:
    """Stand-in for PushManager that records what start() received."""

    def __init__(self, client):
        self.client = client
        self.watched_chats = []
        self.on_event = None
        self.started = None

    def add_watched_chat(self, chat_mid):
        if chat_mid not in self.watched_chats:
            self.watched_chats.append(chat_mid)

    def start(self, watched_chats=None, on_event=None, fetch_type=1, services=None):
        if watched_chats is not None:
            self.watched_chats = list(watched_chats)
        if on_event:
            self.on_event = on_event
        self.started = {"fetch_type": fetch_type, "services": services}


def test_client_start_push_delegates_to_base(client, monkeypatch):
    """Client.start_push used to read a self.push it never had -> AttributeError."""
    monkeypatch.setattr("linepy.realtime.push.PushManager", _FakePush)

    client.start_push(["m" + "1" * 32], fetch_type=2)

    assert isinstance(client.base.push, _FakePush)
    assert client.push is client.base.push
    assert client.base.push.started["fetch_type"] == 2


def test_start_push_keeps_watched_chats(base, monkeypatch):
    """start() must not wipe the chats add_watched_chat() just registered."""
    monkeypatch.setattr("linepy.realtime.push.PushManager", _FakePush)

    mids = ["m" + "1" * 32, "m" + "2" * 32]
    base.start_push(mids)

    assert base.push.watched_chats == mids


def test_push_manager_start_preserves_registered_chats(base):
    """Same guarantee, on the real PushManager (without opening a socket)."""
    push = PushManager(base)
    push.add_watched_chat("m" + "3" * 32)
    push._running = True  # short-circuits start() before it spawns a thread

    push.start()

    assert push.watched_chats == ["m" + "3" * 32]


def test_listen_enables_both_talk_and_square(base, monkeypatch):
    monkeypatch.setattr("linepy.realtime.push.PushManager", _FakePush)

    base.listen()

    assert base.push.started["services"] == [ServiceType.SQUARE, ServiceType.TALK_SYNC]


def test_listen_can_select_a_single_service(base, monkeypatch):
    monkeypatch.setattr("linepy.realtime.push.PushManager", _FakePush)

    base.listen(talk=False)

    assert base.push.started["services"] == [ServiceType.SQUARE]


def test_listen_rejects_an_empty_service_set(base):
    with pytest.raises(ValueError):
        base.listen(talk=False, square=False)


def test_listen_watches_registered_chats(base, monkeypatch):
    """listen() read a _watch_chat_mids that was never initialised."""
    monkeypatch.setattr("linepy.realtime.push.PushManager", _FakePush)

    base.watch_chats("m" + "4" * 32, "m" + "5" * 32)
    base.watch_chats("m" + "4" * 32)  # duplicates are ignored
    base.listen()

    assert base.push.watched_chats == ["m" + "4" * 32, "m" + "5" * 32]


def test_listen_callback_takes_service_type_and_event(base, monkeypatch):
    """PushManager calls on_event(service_type, event); listen() passed a 1-arg fn."""
    monkeypatch.setattr("linepy.realtime.push.PushManager", _FakePush)

    seen = []

    class _Dispatcher:
        def dispatch_talk_operation(self, op):
            seen.append(("talk", op))

        def dispatch_square_event(self, ev):
            seen.append(("square", ev))

    base._dispatcher = _Dispatcher()
    base.listen()

    base.push.on_event(ServiceType.SQUARE, "SQ")
    base.push.on_event(ServiceType.TALK_SYNC, "OP")

    assert seen == [("square", "SQ"), ("talk", "OP")]


def test_polling_attribute_exists_before_start(base):
    assert base.polling is None
    base.stop_polling()  # must not raise on a client that never polled
