#!/usr/bin/env python3
"""Tests for Client.get_all_friends / Client.get_all_chats.

These were missing entirely (examples/basic.py called
client.get_all_friends() and it raised AttributeError) -- added as thin
wrappers combining the bulk-id RPC with the existing get_contacts/get_chats.
"""

import os
import tempfile

import pytest

from linepy.client import Client
from linepy.models import GetAllChatMidsResponse


@pytest.fixture
def client():
    return Client(device="DESKTOPWIN", storage=os.path.join(tempfile.mkdtemp(), "s.json"))


def test_get_all_friends_fetches_contacts_for_all_ids(client):
    client.base.talk.get_all_contact_ids = lambda: ["u1", "u2"]
    captured = {}

    def fake_get_contacts(mids):
        captured["mids"] = mids
        return [{"mid": m} for m in mids]

    client.base.talk.get_contacts = fake_get_contacts
    friends = client.get_all_friends()
    assert friends == [{"mid": "u1"}, {"mid": "u2"}]
    assert captured["mids"] == ["u1", "u2"]


def test_get_all_friends_empty_short_circuits(client):
    client.base.talk.get_all_contact_ids = lambda: []
    called = []
    client.base.talk.get_contacts = lambda mids: called.append(mids)
    assert client.get_all_friends() == []
    assert called == []  # never called get_contacts with an empty list


def test_get_all_chats_merges_member_and_invited_deduped(client):
    client.base.talk.get_all_chat_mids = lambda: GetAllChatMidsResponse(
        member_chat_mids=["c1", "c2"], invited_chat_mids=["c2", "c3"]
    )
    captured = {}

    def fake_get_chats(mids, with_members=True, with_invitees=True):
        captured["mids"] = mids

        class R:
            chats = [{"mid": m} for m in mids]

        return R()

    client.base.talk.get_chats = fake_get_chats
    chats = client.get_all_chats()
    assert captured["mids"] == ["c1", "c2", "c3"]  # deduped, order preserved
    assert chats == [{"mid": "c1"}, {"mid": "c2"}, {"mid": "c3"}]


def test_get_all_chats_empty_short_circuits(client):
    client.base.talk.get_all_chat_mids = lambda: GetAllChatMidsResponse(
        member_chat_mids=[], invited_chat_mids=[]
    )
    called = []
    client.base.talk.get_chats = lambda *a, **k: called.append(1)
    assert client.get_all_chats() == []
    assert called == []
