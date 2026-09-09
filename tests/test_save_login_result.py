#!/usr/bin/env python3
"""TokenManager.save_login_result: accepts both raw int-keyed field dicts and
pydantic model_dump(by_alias=True) (string-keyed) shapes, matching the two
call sites in login.py (_login_v2_raw's raw dict vs. QRCodeLoginV2Response's
_dump_response)."""

from linepy.login import _dump_response
from linepy.models.login import QRCodeLoginV2Response
from linepy.storage import MemoryStorage, TokenManager


def test_save_login_result_int_keyed_dict():
    tm = TokenManager(MemoryStorage())
    tm.save_login_result({3: {1: "TOK1", 2: "REF1", 3: 100, 6: 5000}, 4: "uMidInt"})
    assert tm.auth_token == "TOK1"
    assert tm.refresh_token == "REF1"
    assert tm.expire == 5100  # iat(6000... wait 5000) + expires_in(100) = 5100
    assert tm.mid == "uMidInt"


def test_save_login_result_str_keyed_from_model_dump():
    model = QRCodeLoginV2Response.from_dict({
        "1": "PEM", "3": {"1": "TOK2", "2": "REF2", "3": 200, "6": 6000}, "4": "uMidStr",
    })
    dumped = _dump_response(model)
    tm = TokenManager(MemoryStorage())
    tm.save_login_result(dumped)
    assert tm.auth_token == "TOK2"
    assert tm.refresh_token == "REF2"
    assert tm.expire == 6200
    assert tm.mid == "uMidStr"


def test_save_login_result_missing_token_info_is_noop():
    tm = TokenManager(MemoryStorage())
    tm.save_login_result({1: "cert only"})
    assert tm.auth_token is None
    assert tm.refresh_token is None


def test_dump_response_passthrough_for_plain_dict():
    raw = {3: {1: "x"}}
    assert _dump_response(raw) is raw
