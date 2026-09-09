#!/usr/bin/env python3
"""Exception plumbing.

``linepy.exceptions`` is the single home for LineException / LoginError /
CompactMessageProtocolError. These tests cover both the import surface and
the error paths that actually raise them -- the paths were previously
uncovered, so a missing import in ServiceBase._call stayed invisible until a
real request failed.
"""

import os
import tempfile

import httpx
import pytest

import linepy
from linepy.exceptions import (
    CompactMessageProtocolError,
    LineException,
    LoginError,
)


def _storage():
    return os.path.join(tempfile.mkdtemp(), "s.json")


# ---- import surface --------------------------------------------------------


def test_exported_from_package_root():
    assert linepy.LineException is LineException
    assert linepy.LoginError is LoginError
    assert linepy.CompactMessageProtocolError is CompactMessageProtocolError


def test_legacy_import_locations_still_work():
    """Callers that learned `from linepy.base import LineException` keep working."""
    from linepy.base import LineException as FromBase
    from linepy.compact import CompactMessageProtocolError as FromCompact
    from linepy.login import LoginError as FromLogin

    assert FromBase is LineException
    assert FromLogin is LoginError
    assert FromCompact is CompactMessageProtocolError


def test_line_exception_carries_code_message_metadata():
    exc = LineException(119, "Access token refresh required", {"url": "/S4"})

    assert exc.code == 119
    assert exc.message == "Access token refresh required"
    assert exc.metadata == {"url": "/S4"}
    assert "[119]" in str(exc)
    assert "/S4" in str(exc)


def test_line_exception_without_metadata():
    exc = LineException(-1, "boom")
    assert exc.metadata == {}
    assert str(exc) == "[-1] boom"


# ---- error paths that raise them -------------------------------------------


@pytest.fixture
def client():
    return linepy.BaseClient(device="DESKTOPMAC", storage=_storage())


def test_service_call_raises_on_thrift_error(client, monkeypatch):
    """A decoded response carrying an `error` struct becomes a LineException."""
    monkeypatch.setattr(
        client.request,
        "request",
        lambda **kw: {"error": {"code": 8, "message": "NOT_FOUND", "metadata": {"a": 1}}},
    )

    with pytest.raises(LineException) as ei:
        client.talk.get_profile()

    assert ei.value.code == 8
    assert ei.value.message == "NOT_FOUND"
    assert ei.value.metadata == {"a": 1}


def test_service_call_raises_on_http_error(client, monkeypatch):
    request = httpx.Request("POST", "https://gw.line.naver.jp/S4")
    response = httpx.Response(403, request=request, text="forbidden")

    def _raise(**kw):
        raise httpx.HTTPStatusError("403", request=request, response=response)

    monkeypatch.setattr(client.request, "request", _raise)

    with pytest.raises(LineException) as ei:
        client.talk.get_profile()

    assert ei.value.code == 403
    assert ei.value.metadata["body"] == "forbidden"
    assert ei.value.metadata["url"].endswith("/S4")


def test_channel_call_raises_on_thrift_error(client, monkeypatch):
    monkeypatch.setattr(
        client.request,
        "request",
        lambda **kw: {"error": {"code": 5, "message": "CHANNEL_ERROR"}},
    )

    with pytest.raises(LineException) as ei:
        client.channel.issue_channel_token("1341209850")

    assert ei.value.code == 5
    assert ei.value.message == "CHANNEL_ERROR"


def test_compact_error_carries_optional_code():
    assert CompactMessageProtocolError("bad").code is None
    assert CompactMessageProtocolError("bad", code=82).code == 82
