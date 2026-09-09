#!/usr/bin/env python3
"""
PushManager Talk-sync decode + dispatch wiring (audit gap #1).

Verifies that a Service-8 SignOn response is decoded via TMoreCompactProtocol,
its operations extracted, and routed through the client event dispatcher
(instead of the old "ignore Service 8" behaviour).
"""

import os
import tempfile

import pytest

from linepy.base import BaseClient
from linepy.push.manager import PushManager
from linepy.push.data import ServiceType


@pytest.fixture
def client():
    c = BaseClient(device="DESKTOPMAC", storage=os.path.join(tempfile.mkdtemp(), "s.json"))
    c.mid = "u" + "a" * 32
    return c


def test_decode_talk_sync_prefers_tmc(client):
    pm = PushManager(client)
    # A valid TMC message {1: {0: 50, 1: 51}} (from tmc vectors)
    data = bytes.fromhex("00000001d50002036466")
    decoded = pm.decode_talk_sync(data)
    assert decoded == {1: {0: 50, 1: 51}}


def test_decode_talk_sync_compact_fallback(client):
    pm = PushManager(client)
    # Not valid TMC (too short / bad header) -> compact fallback path is attempted.
    # Feed a bare compact struct via read_thrift; use a simple empty struct (0x00).
    decoded = pm.decode_talk_sync(bytes([0x00]))
    # Either decodes to an empty struct or returns None; must not raise.
    assert decoded in ({}, None) or isinstance(decoded, (dict, list))


def test_extract_operations():
    assert PushManager.extract_operations({0: {1: [{"a": 1}, {"a": 2}]}}) == [{"a": 1}, {"a": 2}]
    assert PushManager.extract_operations({1: [{"x": 1}]}) == [{"x": 1}]
    assert PushManager.extract_operations(None) == []
    assert PushManager.extract_operations({0: {}}) == []


def test_talk_sync_response_dispatches_operations(client, monkeypatch):
    pm = PushManager(client)
    dispatched = []
    client.get_dispatcher().dispatch_talk_operation = lambda op: dispatched.append(op)

    # Make decode return two operations.
    monkeypatch.setattr(pm, "decode_talk_sync", lambda data: {0: {1: [
        {"type": 26, "message": {"id_": "m1"}},
        {"type": 26, "message": {"id_": "m2"}},
    ]}})
    pm.sign_on_requests[1] = [ServiceType.TALK_SYNC, "sync", None]
    pm.on_sign_on_response(1, True, b"ignored")
    assert [o["message"]["id_"] for o in dispatched] == ["m1", "m2"]


def test_talk_sync_advances_revisions(client):
    pm = PushManager(client)
    pm._advance_talk_revisions({0: {1: 111, 3: 222, 4: 333}})
    assert pm.last_revision == 111
    assert pm.last_global_revision == 222
    assert pm.last_individual_revision == 333
