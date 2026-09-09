#!/usr/bin/env python3
"""VOOM (Step 12) and LIFF (Step 11) tests."""

import json
import os
import tempfile

import pytest

from linepy.base import BaseClient
from linepy.services import liff as liff_mod
from linepy.services import voom as voom_mod


@pytest.fixture
def client():
    c = BaseClient(device="ANDROID", storage=os.path.join(tempfile.mkdtemp(), "s.json"))
    c.mid = "u" + "a" * 32
    c.auth_token = "ACCESS"
    return c


# ------------------------------------------------------------------- VOOM

def test_routing_prefixes_match_spec():
    assert voom_mod.VOOM_ROUTING_PREFIX == {
        "MYHOME": "/mh", "MYHOME_RENEWAL": "/hm", "TIMELINE": "/tl",
        "TIMELINE_GATEWAY": "/ext/timeline/tlgw", "NOTE": "/ext/note/nt",
        "HOMEAPI": "/ma", "SQUARE_NOTE": "/sn", "ALBUM": "/ext/album",
        "STORY": "/st", "SOCIAL_NOTIFICATION": "/eg", "TRANSLATION": "/ds",
    }


def test_channel_ids():
    assert voom_mod.VOOM_CHANNEL_ID["TIMELINE"] == "1341209950"
    assert voom_mod.VOOM_CHANNEL_ID["NOTE"] == "1655599932"


def test_build_request_get(client):
    req = client.voom.build_request("/api/v57/timeline/tab/status.json",
                                    routing="TIMELINE", channel_token="CTOK")
    assert req["url"] == "https://gw.line.naver.jp/tl/api/v57/timeline/tab/status.json"
    assert req["method"] == "GET"
    assert req["headers"]["X-Line-ChannelToken"] == "CTOK"
    assert "X-Line-Access" not in req["headers"]
    assert req["headers"]["X-Line-Mid"] == client.mid


def test_build_request_post_with_access(client):
    req = client.voom.build_request("api/v57/post/list.json", body={"a": 1})
    assert req["url"] == "https://gw.line.naver.jp/mh/api/v57/post/list.json"
    assert req["method"] == "POST"
    assert req["headers"]["X-Line-Access"] == "ACCESS"
    assert req["headers"]["content-type"] == "application/json"
    assert json.loads(req["body"]) == {"a": 1}


def test_get_token_caches(client):
    calls = []

    class _Ch:
        def issue_channel_token(self, cid):
            calls.append(cid)
            return {"token": "TOKEN-" + cid}

    client.channel = _Ch()
    t1 = client.voom.get_token("TIMELINE")
    t2 = client.voom.get_token("TIMELINE")
    assert t1 == "TOKEN-1341209950" == t2
    assert calls == ["1341209950"]  # issued once, then cached


# ------------------------------------------------------------------- LIFF

def test_liff_message_builders():
    assert liff_mod.LiffTextMessage("hi") == {"type": "text", "text": "hi"}
    flex = liff_mod.LiffFlexMessage("alt", {"type": "bubble"})
    assert flex == {"type": "flex", "altText": "alt", "contents": {"type": "bubble"}}
    stk = liff_mod.LiffStickerMessage(1, 2)
    assert stk == {"type": "sticker", "packageId": "1", "stickerId": "2"}


def test_issue_liff_view_params(client):
    captured = {}

    def fake_call(path, method, params, **kw):
        captured["path"] = path
        captured["method"] = method
        captured["params"] = params
        return {3: "LIFF_TOKEN"}

    client._call_service = fake_call
    tok = client.liff.get_liff_token("c" + "1" * 32, "myliff-1")
    assert tok == "LIFF_TOKEN"
    assert captured["path"] == "/LIFF1"
    assert captured["method"] == "issueLiffView"
    # top struct: [[12,1,[[11,1,liffId],[12,2,[context]],[11,3,lang]]]]
    inner = captured["params"][0][2]
    assert inner[0] == [11, 1, "myliff-1"]
    # chat context: prefix 'c' -> chaType 2, context=[12,2,[[11,1,chatMid]]]
    context = inner[1][2][0]
    assert context[0] == 12 and context[1] == 2
    assert context[2][0] == [11, 1, "c" + "1" * 32]


def test_send_liff(client):
    client._call_service = lambda path, method, params, **kw: {3: "TK"}

    sent = {}

    def fake_post(url, content=None, headers=None):
        sent["url"] = url
        sent["headers"] = headers
        sent["body"] = content

        class _R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"ok": True}

        return _R()

    client.request._http.post = fake_post
    msgs = [liff_mod.LiffTextMessage("hello")]
    res = client.liff.send_liff("u" + "b" * 32, msgs)
    assert res == {"ok": True}
    assert sent["url"] == "https://api.line.me/message/v3/share"
    assert sent["headers"]["Authorization"] == "Bearer TK"
    assert json.loads(sent["body"]) == {"messages": [{"type": "text", "text": "hello"}]}
