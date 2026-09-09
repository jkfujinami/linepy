#!/usr/bin/env python3
"""One event bus, one polling loop.

Event reception used to be spread across four independent implementations:
realtime/push, realtime/polling, a third thread-per-chat loop inside
SquareHelper with its own on/emit registry, and the dispatcher. SquareHelper
now drives PollingManager and emits on the client's bus, so there is one of
each.
"""

import ast
import os
import pathlib
import tempfile

import pytest

from linepy.base import BaseClient
from linepy.helpers.square import SquareEvent, SquareHelper

REPO = pathlib.Path(__file__).resolve().parent.parent
HELPER_SRC = (REPO / "linepy" / "helpers" / "square.py").read_text()


@pytest.fixture
def client():
    return BaseClient(
        device="DESKTOPMAC", storage=os.path.join(tempfile.mkdtemp(), "s.json")
    )


class _FakePolling:
    def __init__(self, client):
        self.client = client
        self.started = None
        self.stopped = False

    def start(self, watched_chats=None, on_event=None, fetch_type=2):
        self.started = {
            "watched_chats": watched_chats,
            "on_event": on_event,
            "fetch_type": fetch_type,
        }

    def stop(self):
        self.stopped = True


# ---- SquareHelper no longer polls on its own -------------------------------


@pytest.mark.parametrize(
    "name", ["_poll_chat", "_handle_event", "on", "emit"]
)
def test_squarehelper_dropped_its_private_event_machinery(name):
    assert not hasattr(SquareHelper, name), f"SquareHelper still defines {name}"


def test_squarehelper_spawns_no_threads_of_its_own():
    tree = ast.parse(HELPER_SRC)
    threads = [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and "Thread" in ast.unparse(node.func)
    ]
    assert not threads, f"SquareHelper still starts threads: {threads}"


def test_start_polling_delegates_to_the_polling_manager(client, monkeypatch):
    monkeypatch.setattr("linepy.realtime.polling.PollingManager", _FakePolling)

    mids = ["m" + "1" * 32, "m" + "2" * 32]
    client.square_helper.start_polling(mids, fetch_type=1)

    assert isinstance(client.polling, _FakePolling)
    assert client.polling.started["watched_chats"] == mids
    assert client.polling.started["fetch_type"] == 1


def test_stop_polling_delegates_too(client, monkeypatch):
    monkeypatch.setattr("linepy.realtime.polling.PollingManager", _FakePolling)

    client.square_helper.start_polling(["m" + "1" * 32])
    client.square_helper.stop_polling()

    assert client.polling.stopped


# ---- dispatch --------------------------------------------------------------


def _raw_event(event_type):
    """SquareEvent reads the type off the first digit key of `payload`."""
    return {"payload": {str(event_type): {}}, "createdTime": 0}


def test_event_decorator_receives_matching_events(client, monkeypatch):
    monkeypatch.setattr("linepy.realtime.polling.PollingManager", _FakePolling)
    helper = client.square_helper
    seen = []

    @helper.event(1)
    def on_message(event, h):
        seen.append((event.event_type, h))

    helper.start_polling(["m" + "1" * 32])
    client.polling.started["on_event"](3, _raw_event(1))

    assert seen == [(1, helper)]


def test_handlers_for_other_types_are_not_called(client, monkeypatch):
    monkeypatch.setattr("linepy.realtime.polling.PollingManager", _FakePolling)
    helper = client.square_helper
    seen = []

    helper.event(1)(lambda event, h: seen.append(event.event_type))
    helper.start_polling(["m" + "1" * 32])
    client.polling.started["on_event"](3, _raw_event(2))

    assert seen == []


def test_a_raising_handler_does_not_stop_dispatch(client, monkeypatch):
    monkeypatch.setattr("linepy.realtime.polling.PollingManager", _FakePolling)
    helper = client.square_helper
    seen = []

    helper.event(1)(lambda event, h: (_ for _ in ()).throw(RuntimeError("boom")))
    helper.event(1)(lambda event, h: seen.append("second"))

    helper.start_polling(["m" + "1" * 32])
    client.polling.started["on_event"](3, _raw_event(1))

    assert seen == ["second"]


def test_events_also_reach_the_client_event_bus(client, monkeypatch):
    """SquareHelper used to keep a second, private registry."""
    monkeypatch.setattr("linepy.realtime.polling.PollingManager", _FakePolling)
    seen = []
    client.on("square:event", lambda event: seen.append(event))

    client.square_helper.start_polling(["m" + "1" * 32])
    client.polling.started["on_event"](3, _raw_event(1))

    assert len(seen) == 1
    assert isinstance(seen[0], SquareEvent)


def test_client_has_exactly_one_event_registry(client):
    registries = [
        name
        for name in ("_callbacks", "_event_callbacks")
        if hasattr(client, name) or hasattr(client.square_helper, name)
    ]
    assert registries == ["_callbacks"]
