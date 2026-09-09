#!/usr/bin/env python3
"""High-level Client exposure + media routing tests (audit gap #5)."""

import os
import tempfile

import pytest

from linepy.client import Client


@pytest.fixture
def client():
    return Client(device="DESKTOPMAC", storage=os.path.join(tempfile.mkdtemp(), "s.json"))


def test_feature_properties(client):
    from linepy.services.liff import LiffService
    from linepy.services.voom import VoomService

    assert isinstance(client.liff, LiffService)
    assert isinstance(client.voom, VoomService)
    assert client.obs is client.base.obs
    assert client.e2ee is client.base.e2ee


def test_on_and_emit_delegate(client):
    got = []
    client.on("x", lambda v: got.append(v))
    client.emit("x", 42)
    assert got == [42]


def test_media_routing_square(client):
    seen = {}
    client.base.obs.upload_obj_square_chat = lambda **kw: seen.update(kw) or {"objId": "O"}
    client.send_image("m" + "1" * 32, b"IMG")
    assert seen["square_chat_mid"].startswith("m")
    assert seen["content_type"] == "image"


def test_media_routing_talk_e2ee(client):
    seen = {}
    client.base.obs.upload_media_by_e2ee = lambda **kw: seen.update(kw) or {"ok": True}
    client.send_video("u" + "2" * 32, b"VIDBYTES")
    assert seen["to"].startswith("u")
    assert seen["o_type"] == "video"
    assert seen["data"] == b"VIDBYTES"


def test_media_routing_group_talk(client):
    seen = {}
    client.base.obs.upload_media_by_e2ee = lambda **kw: seen.update(kw) or {"ok": True}
    client.send_file("c" + "3" * 32, b"FILEBYTES", filename="a.bin")
    assert seen["to"].startswith("c")
    assert seen["o_type"] == "file"
    assert seen["filename"] == "a.bin"
