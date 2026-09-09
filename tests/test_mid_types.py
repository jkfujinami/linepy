#!/usr/bin/env python3
"""MID-prefix -> MIDType resolution.

``get_mid_type`` in linepy.config is now the single source of truth; both
``BaseClient.get_to_type`` (full map, ``None`` for unknown prefixes) and
``e2ee.get_to_type`` (user/room/group only, defaulting to USER) build on it.
"""

import os
import tempfile

import pytest

from linepy.base import BaseClient
from linepy.config import (
    MID_TYPE_BOT,
    MID_TYPE_GROUP,
    MID_TYPE_ROOM,
    MID_TYPE_SQUARE,
    MID_TYPE_SQUARE_CHAT,
    MID_TYPE_SQUARE_MEMBER,
    MID_TYPE_USER,
    get_mid_type,
)
from linepy.crypto.e2ee import get_to_type


@pytest.fixture
def client():
    return BaseClient(
        device="DESKTOPMAC", storage=os.path.join(tempfile.mkdtemp(), "s.json")
    )


@pytest.mark.parametrize(
    "prefix,expected",
    [
        ("u", MID_TYPE_USER),
        ("r", MID_TYPE_ROOM),
        ("c", MID_TYPE_GROUP),
        ("s", MID_TYPE_SQUARE),
        ("m", MID_TYPE_SQUARE_CHAT),
        ("p", MID_TYPE_SQUARE_MEMBER),
        ("v", MID_TYPE_BOT),
        ("t", 7),
    ],
)
def test_get_mid_type_covers_every_prefix(prefix, expected):
    assert get_mid_type(prefix + "0" * 32) == expected


@pytest.mark.parametrize("mid", ["", None, "z" + "0" * 32])
def test_get_mid_type_is_none_for_unknown(mid):
    assert get_mid_type(mid) is None


def test_base_client_get_to_type_matches_config(client):
    for prefix in "urcsmpvt":
        mid = prefix + "0" * 32
        assert client.get_to_type(mid) == get_mid_type(mid)
    assert client.get_to_type("") is None


@pytest.mark.parametrize(
    "prefix,expected",
    [
        ("u", MID_TYPE_USER),
        ("r", MID_TYPE_ROOM),
        ("c", MID_TYPE_GROUP),
        # E2EE only knows user/room/group; everything else is a 1:1 chat.
        ("s", MID_TYPE_USER),
        ("m", MID_TYPE_USER),
        ("v", MID_TYPE_USER),
    ],
)
def test_e2ee_get_to_type_falls_back_to_user(prefix, expected):
    assert get_to_type(prefix + "0" * 32) == expected


def test_e2ee_get_to_type_handles_empty_mid():
    assert get_to_type("") == MID_TYPE_USER
