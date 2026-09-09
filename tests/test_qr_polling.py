#!/usr/bin/env python3
"""QR long-polling budget and its timeout.

/acct/lp/lgn/sq/v1 holds each poll open for the window in `x-lst` and answers
410 Gone when it elapses with nobody having scanned. Measured: a 10s window
returns 410 after 10.0s, so 410 means "not yet", not "session dead".

Two things went wrong with that. The legacy (non-v3) flow polled exactly once,
so a single unscanned window ended the login; and the final 410 escaped as a
bare httpx.HTTPStatusError, which reads like the session died.
"""

import os
import tempfile

import httpx
import pytest

from linepy.base import BaseClient
from linepy.exceptions import LoginError

LP_PATH = "/acct/lp/lgn/sq/v1"


@pytest.fixture
def login():
    client = BaseClient(
        device="IOSIPAD", storage=os.path.join(tempfile.mkdtemp(), "s.json")
    )
    return client.login_handler


def _gone():
    request = httpx.Request("POST", "https://legy.line-apps.com" + LP_PATH)
    return httpx.HTTPStatusError(
        "410 Gone", request=request, response=httpx.Response(410, request=request)
    )


def _poller(login, outcomes):
    """Replace the transport with a scripted sequence of poll outcomes."""
    calls = []

    def _request(path, **kwargs):
        calls.append(path)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    login.client.request.request = _request
    return calls


def test_a_410_mid_budget_is_retried(login):
    calls = _poller(login, [_gone(), _gone(), {}])

    assert login.check_qr_code_verified("SQ1", max_count=3, interval_sec=1) is True
    assert len(calls) == 3
    assert calls[0] == LP_PATH


def test_the_last_410_becomes_a_login_error(login):
    """It used to surface as httpx.HTTPStatusError: 410 Gone."""
    _poller(login, [_gone(), _gone()])

    with pytest.raises(LoginError) as ei:
        login.check_qr_code_verified("SQ1", max_count=2, interval_sec=30)

    message = str(ei.value)
    assert "60s" in message and "2 polls" in message
    assert "410" not in message
    assert isinstance(ei.value.__cause__, httpx.HTTPStatusError)


def test_a_timeout_is_retried_like_a_410(login):
    calls = _poller(login, [httpx.ReadTimeout("slow"), {}])

    assert login.check_qr_code_verified("SQ1", max_count=2, interval_sec=1) is True
    assert len(calls) == 2


def test_a_real_error_is_not_swallowed(login):
    request = httpx.Request("POST", "https://legy.line-apps.com" + LP_PATH)
    forbidden = httpx.HTTPStatusError(
        "403", request=request, response=httpx.Response(403, request=request)
    )
    calls = _poller(login, [forbidden])

    with pytest.raises(httpx.HTTPStatusError):
        login.check_qr_code_verified("SQ1", max_count=5, interval_sec=1)

    assert len(calls) == 1, "a fatal error must stop the loop immediately"


def test_poll_window_is_sent_as_x_lst(login):
    seen = {}

    def _request(path, extra_headers=None, timeout=None, **kwargs):
        seen.update(headers=extra_headers, timeout=timeout)
        return {}

    login.client.request.request = _request
    login.check_qr_code_verified("SQ1", max_count=1, interval_sec=30)

    assert seen["headers"]["x-lst"] == "30000"
    assert seen["headers"]["x-line-access"] == "SQ1"
    assert seen["timeout"] == 35.0


# ---- the budget the flows actually use -------------------------------------


def test_legacy_flow_polls_for_the_full_budget(login, monkeypatch):
    """_request_sqr called check_qr_code_verified(sqr) -- one 30s attempt."""
    from linepy.models.custom.login import QRCodeResponse, QRSessionResponse

    seen = {}

    def _request(method, **kw):
        if method == "createSession":
            return QRSessionResponse(sqr="SQ1")
        if method == "createQrCode":
            return QRCodeResponse(url="https://line.me/R/au/lgn/sq/SQ1")
        raise AssertionError(f"unexpected call: {method}")

    monkeypatch.setattr(login, "_request", lambda path, method, **kw: _request(method))

    def _check(qrcode, max_count=1, interval_sec=30):
        seen["qr"] = (max_count, interval_sec)
        raise LoginError("stop here")

    monkeypatch.setattr(login, "check_qr_code_verified", _check)
    monkeypatch.setattr(login, "_print_qr", lambda url: None)

    with pytest.raises(LoginError):
        login._request_sqr()

    assert seen["qr"] == (
        login.DEFAULT_LONG_POLLING_MAX_COUNT,
        login.DEFAULT_LONG_POLLING_INTERVAL_SEC,
    )
    assert seen["qr"] != (1, 30), "still only one attempt"


def test_default_budget_is_six_minutes(login):
    total = login.DEFAULT_LONG_POLLING_MAX_COUNT * login.DEFAULT_LONG_POLLING_INTERVAL_SEC
    assert total == 360
