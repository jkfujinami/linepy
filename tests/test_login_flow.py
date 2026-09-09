#!/usr/bin/env python3
"""
Function-by-function login.py fidelity tests vs 本家 (linejs base/login/mod.ts).

Every RPC parameter layout, field-omission rule, endpoint routing, retry
semantics, and the full E2EE PIN-verification handshake (previously an
unimplemented TODO) are checked against the reference TS implementation.
"""

import base64
import os
import tempfile

import pytest

from linepy.auth.login import registration_auth_endpoint
from linepy.base import BaseClient
from linepy.crypto.primitives import AES
from linepy.models import (
    LoginResponse,
    PinCodeResponse,
    QRCodeLoginResponse,
    QRCodeLoginV2Response,
    QRCodeResponse,
    QRSessionResponse,
    RSAKeyInfo,
)
from linepy.protocol.thrift import ThriftReader


@pytest.fixture
def client():
    return BaseClient(device="DESKTOPWIN", storage=os.path.join(tempfile.mkdtemp(), "s.json"))


@pytest.fixture
def android_client():
    return BaseClient(device="ANDROID", storage=os.path.join(tempfile.mkdtemp(), "s.json"))


# ------------------------------------------------------------------ endpoint

def test_registration_auth_endpoint():
    assert registration_auth_endpoint("ANDROID") == "/api/v4p/rs"
    assert registration_auth_endpoint("ANDROIDSECONDARY") == "/api/v4p/rs"
    assert registration_auth_endpoint("DESKTOPWIN") == "/api/v3p/rs"
    assert registration_auth_endpoint("IOS") == "/api/v3p/rs"


def test_auth_endpoint_method(client, android_client):
    assert client.login_handler.auth_endpoint() == "/api/v3p/rs"
    assert android_client.login_handler.auth_endpoint() == "/api/v4p/rs"


def test_get_rsa_key_info_uses_fixed_talkservice_path(client):
    captured = {}

    def fake_request(path, method, params, protocol=4, timeout=None,
                     extra_headers=None, response_model=None):
        captured.update(path=path, method=method, params=params, protocol=protocol)
        return RSAKeyInfo.from_dict({"1": "k", "2": "1", "3": "1", "4": "s"})

    client.login_handler._request = fake_request
    client.login_handler.get_rsa_key_info()
    # getRSAKeyInfo always hits the fixed TalkService.do path, NOT the
    # device-dependent registration endpoint.
    assert captured["path"] == "/api/v3/TalkService.do"
    assert captured["protocol"] == 3
    assert captured["params"] == [[12, 1, [[8, 2, 0]]]]


# --------------------------------------------------------- loginV2/loginZ

def test_login_v2_params_omit_absent_fields(client):
    lh = client.login_handler
    fields = lh._build_login_v2_params("keynm1", "encmsg", None, None, None)
    field_map = {f[1]: f for f in fields}
    # cert(8)/verifier(9)/secret(10) must be OMITTED (None), matching 本家's
    # undefined-skip -- not written as empty string/bytes.
    assert field_map[8][2] is None
    assert field_map[9][2] is None
    assert field_map[10][2] is None
    assert field_map[1][2] == 0  # loginType = Normal (no secret, no verifier)
    assert field_map[5][2] is False  # keepLoggedIn hardcoded false
    assert field_map[7][2] == "DESKTOPWIN"  # raw client.device, not system_name
    assert field_map[12][2] == "System Product Name"


def test_login_v2_login_type_computation(client):
    lh = client.login_handler
    # secret only -> E2EE (2)
    f = {x[1]: x[2] for x in lh._build_login_v2_params("k", "e", None, b"sec", "cert")}
    assert f[1] == 2
    # verifier present -> Verifier retry (1), regardless of secret
    f = {x[1]: x[2] for x in lh._build_login_v2_params("k", "e", "ver", b"sec", None)}
    assert f[1] == 1
    # neither -> Normal (0)
    f = {x[1]: x[2] for x in lh._build_login_v2_params("k", "e", None, None, None)}
    assert f[1] == 0


def test_login_v2_fields_are_omitted_on_the_wire(client):
    """End-to-end: encode with the real binary writer and confirm the
    omitted fields never appear on the wire at all."""
    from linepy.protocol.thrift import write_thrift

    lh = client.login_handler
    fields = lh._build_login_v2_params("k", "e", None, None, None)
    data = write_thrift([[12, 2, fields]], "loginZ", 3)
    r = ThriftReader(data)
    r.read_message_begin()
    _, ftype, fid = r.read_field_begin()
    struct = r.read_value(ftype)
    assert 8 not in struct and 9 not in struct and 10 not in struct
    assert struct[7] == "DESKTOPWIN"


def test_confirm_e2ee_login_wire_format(android_client):
    lh = android_client.login_handler
    captured = {}

    def fake_request(path, data, protocol=4, timeout=None, extra_headers=None):
        captured["path"] = path
        captured["protocol"] = protocol
        r = ThriftReader(data)
        r.read_message_begin()
        out = {}
        while True:
            _, ftype, fid = r.read_field_begin()
            if ftype == 0:
                break
            out[fid] = r.read_value(ftype)
        captured["struct"] = out
        return "NEWVERIFIER"

    android_client.request.request = fake_request
    result = lh.confirm_e2ee_login("verifierABC", b"devsecretbytes")
    assert result == "NEWVERIFIER"
    assert captured["path"] == "/api/v4p/rs"  # ANDROID -> v4p
    assert captured["protocol"] == 3
    assert captured["struct"][1] == "verifierABC"


def test_respond_e2ee_login_request_structure(client):
    lh = client.login_handler
    captured = {}

    def fake(path, method, params, protocol=4, timeout=None, extra_headers=None, response_model=None):
        captured.update(path=path, method=method, params=params, protocol=protocol)
        return None

    lh._request = fake
    lh.respond_e2ee_login_request(
        verifier="verX",
        public_key={"version": 1, "keyId": 5, "keyData": b"pubkeybytes"},
        encrypted_key_chain=b"enckc",
        hash_key_chain=b"hashkc",
    )
    assert captured["path"] == "/S4"
    assert captured["method"] == "respondE2EELoginRequest"
    assert captured["protocol"] == 4
    assert captured["params"] == [
        [11, 1, "verX"],
        [12, 2, [[8, 1, 1], [8, 2, 5], [11, 4, b"pubkeybytes"]]],
        [11, 3, b"enckc"],
        [11, 4, b"hashkc"],
        [8, 5, 0],
    ]


# ------------------------------------------------------ E2EE PIN exchange

def _build_encrypted_keychain(e, secret, key_id):
    """Build a valid AES-256-CBC encrypted keychain blob, matching
    decryptKeyChainEntries's expected wire format (compact struct, field 1 =
    list of {2:keyId,4:pubKey,5:privKey})."""
    from linepy.protocol.thrift import CompactWriter, _write_struct

    secret_pub = e.public_from_private(secret)
    server_priv = os.urandom(32)
    server_pub = e.public_from_private(server_priv)
    kc_priv = os.urandom(32)
    kc_pub = e.public_from_private(kc_priv)

    entry = [[8, 2, key_id], [11, 4, kc_pub], [11, 5, kc_priv]]
    w = CompactWriter()
    _write_struct(w, [[15, 1, [12, [entry]]]])
    struct_bytes = w.get_bytes()
    if not struct_bytes or struct_bytes[-1] != 0:
        struct_bytes += b"\x00"
    struct_bytes += b"\x00" * ((16 - len(struct_bytes) % 16) % 16)

    shared = e.generate_shared_secret(server_priv, secret_pub)
    ak = e.get_sha256_sum(shared, "Key")
    iv = e.xor(e.get_sha256_sum(shared, "IV"))
    enc = AES.new(ak, AES.MODE_CBC, iv).encrypt(struct_bytes)
    return server_pub, enc, kc_priv, kc_pub


def test_do_e2ee_pin_exchange_full_roundtrip(client):
    """GET /LF1 -> decodeE2EEKeyV1 -> encryptDeviceSecret -> confirmE2EELogin.

    This is the exchange that was previously a TODO stub (``e2ee_login =
    verifier``) -- now verified end to end.
    """
    lh = client.login_handler
    e = client.e2ee
    secret = os.urandom(32)
    key_id = 7
    server_pub, enc_keychain, kc_priv, kc_pub = _build_encrypted_keychain(e, secret, key_id)

    lf1_json = {"result": {"metadata": {
        "keyId": key_id,
        "publicKey": base64.b64encode(server_pub).decode(),
        "encryptedKeyChain": base64.b64encode(enc_keychain).decode(),
        "e2eeVersion": 2,
    }}}

    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return lf1_json

    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        return _Resp()

    client.request._http.get = fake_get

    confirm_calls = []

    def fake_confirm(verifier, device_secret):
        confirm_calls.append((verifier, device_secret))
        return "NEW_VERIFIER_XYZ"

    lh.confirm_e2ee_login = fake_confirm

    new_verifier = lh._do_e2ee_pin_exchange("OLD_VERIFIER_123", secret)

    assert new_verifier == "NEW_VERIFIER_XYZ"
    assert captured["url"] == f"https://{client.request.HOST}/LF1"
    h = captured["headers"]
    assert h["x-line-access"] == "OLD_VERIFIER_123"
    assert "accept" not in h  # 本家 sends no explicit accept header for /LF1
    assert h["accept-encoding"] == "gzip"
    assert confirm_calls and confirm_calls[0][0] == "OLD_VERIFIER_123"

    # the keychain must actually have been decrypted and persisted
    stored = e.get_self_key_data_by_key_id(key_id)
    assert stored and base64.b64decode(stored["privKey"]) == kc_priv


def test_do_legacy_pin_exchange_headers_and_result(client):
    lh = client.login_handler
    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"result": {"verifier": "NEWLEGACYVERIFIER"}}

    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        return _Resp()

    client.request._http.get = fake_get
    result = lh._do_legacy_pin_exchange("OLDVER")
    assert result == "NEWLEGACYVERIFIER"
    assert captured["url"] == f"https://{client.request.HOST}/Q"
    h = captured["headers"]
    assert h["accept"] == "application/x-thrift"
    assert h["x-line-access"] == "OLDVER"


# --------------------------------------------------------- email login v2

def _fake_rsa_key():
    """A throwaway (n, e) pair for mocking ``getRSAKeyInfo`` responses.

    The flows under test only encrypt *toward* this key and never decrypt,
    so ``n`` need not be a real RSA modulus (semiprime) -- just large enough
    to fit the PKCS1v1.5-padded login message.
    """
    n = int.from_bytes(b"\x80" + os.urandom(127), "big")  # 1024-bit, top bit set
    return format(n, "x"), format(65537, "x")


def test_request_email_login_v2_full_flow(client):
    lh = client.login_handler
    n_hex, e_hex = _fake_rsa_key()
    calls = []

    def fake_request(path, method, params, protocol=4, timeout=None,
                     extra_headers=None, response_model=None):
        calls.append(method)
        if method == "getRSAKeyInfo":
            return RSAKeyInfo.from_dict({"1": "keynm1", "2": n_hex, "3": e_hex, "4": "sesskey"})
        if method == "loginV2":
            d = {f[1]: f[2] for f in params[0][2]}
            if d[9] is None:
                return {2: None, 3: "VERIFIER_STAGE1", 9: None}
            assert d[9] == "NEW_VERIFIER_FROM_CONFIRM"
            return {2: "CERT_XYZ", 9: {1: "FINAL_AUTH_TOKEN", 2: "REFRESH_TOK",
                                        3: 3600, 6: 1700000000}}
        raise AssertionError(method)

    lh._request = fake_request
    lh._do_e2ee_pin_exchange = lambda verifier, secret: (
        "NEW_VERIFIER_FROM_CONFIRM" if verifier == "VERIFIER_STAGE1"
        else (_ for _ in ()).throw(AssertionError(verifier))
    )

    auth_token = lh._request_email_login_v2("test@example.com", "password123", "123456")
    assert auth_token == "FINAL_AUTH_TOKEN"
    assert calls == ["getRSAKeyInfo", "loginV2", "loginV2"]
    assert client.token_manager.refresh_token == "REFRESH_TOK"
    assert client.token_manager.expire == 1700003600  # iat + expires_in
    assert lh.get_cert("test@example.com") == "CERT_XYZ"


def test_request_email_login_v2_succeeds_without_pin(client):
    """When the first loginV2 already returns tokenInfo, no PIN/E2EE
    exchange should happen at all."""
    lh = client.login_handler
    n_hex, e_hex = _fake_rsa_key()
    calls = []

    def fake_request(path, method, params, protocol=4, timeout=None,
                     extra_headers=None, response_model=None):
        calls.append(method)
        if method == "getRSAKeyInfo":
            return RSAKeyInfo.from_dict({"1": "k", "2": n_hex, "3": e_hex, "4": "s"})
        if method == "loginV2":
            return {9: {1: "DIRECT_TOKEN", 2: "RT", 3: 100, 6: 1000}}
        raise AssertionError(method)

    lh._request = fake_request

    def fail_pin_exchange(*a, **k):
        raise AssertionError("should not need PIN exchange")

    lh._do_e2ee_pin_exchange = fail_pin_exchange

    auth_token = lh._request_email_login_v2("a@b.com", "password1", "114514")
    assert auth_token == "DIRECT_TOKEN"
    assert calls == ["getRSAKeyInfo", "loginV2"]


# --------------------------------------------------------- email login v1

def test_request_email_login_v1_e2ee_branch(client):
    lh = client.login_handler
    n_hex, e_hex = _fake_rsa_key()
    calls = []

    def fake_request(path, method, params, protocol=4, timeout=None,
                     extra_headers=None, response_model=None):
        calls.append(method)
        if method == "getRSAKeyInfo":
            return RSAKeyInfo.from_dict({"1": "k", "2": n_hex, "3": e_hex, "4": "s"})
        if method == "loginZ":
            d = {f[1]: f[2] for f in params[0][2]}
            if d[9] is None:
                return LoginResponse.from_dict({"3": "VERIFIER_1", "4": "999999"})
            assert d[9] == "NEW_VERIFIER_2"
            return LoginResponse.from_dict({"1": "AUTH_TOKEN_FINAL", "2": "CERT_ABC"})
        raise AssertionError(method)

    lh._request = fake_request
    lh._do_e2ee_pin_exchange = lambda v, s: "NEW_VERIFIER_2" if v == "VERIFIER_1" else None

    auth_token = lh._request_email_login("u@example.com", "password123", "114514", True)
    assert auth_token == "AUTH_TOKEN_FINAL"
    assert lh.get_cert("u@example.com") == "CERT_ABC"


def test_request_email_login_v1_legacy_branch(client):
    """enable_e2ee=False must use /Q, never touch the E2EE exchange."""
    lh = client.login_handler
    n_hex, e_hex = _fake_rsa_key()

    def fake_request(path, method, params, protocol=4, timeout=None,
                     extra_headers=None, response_model=None):
        if method == "getRSAKeyInfo":
            return RSAKeyInfo.from_dict({"1": "k", "2": n_hex, "3": e_hex, "4": "s"})
        if method == "loginZ":
            d = {f[1]: f[2] for f in params[0][2]}
            assert d[10] is None  # secret omitted entirely (enable_e2ee=False)
            if d[9] is None:
                return LoginResponse.from_dict({"3": "VERIFIER_LEGACY"})
            assert d[9] == "LEGACY_NEW_VERIFIER"
            return LoginResponse.from_dict({"1": "LEGACY_TOKEN"})
        raise AssertionError(method)

    lh._request = fake_request

    def fail_e2ee(*a, **k):
        raise AssertionError("must not use E2EE exchange")

    lh._do_e2ee_pin_exchange = fail_e2ee
    lh._do_legacy_pin_exchange = lambda v: "LEGACY_NEW_VERIFIER"

    auth_token = lh._request_email_login("u2@example.com", "password123", "114514", False)
    assert auth_token == "LEGACY_TOKEN"


def test_login_with_email_dispatches_v1_vs_v2(client, android_client):
    """DESKTOPWIN (not v3-listed... actually IS v3) -- use a genuinely
    non-v3 device to exercise the v1 dispatch branch."""
    from linepy.config import TOKEN_V3_SUPPORT
    assert "DESKTOPWIN" in TOKEN_V3_SUPPORT  # sanity: v2 branch expected

    calls = {"v1": 0, "v2": 0}
    client.login_handler._request_email_login = lambda *a, **k: calls.__setitem__("v1", calls["v1"] + 1) or "T1"
    client.login_handler._request_email_login_v2 = lambda *a, **k: calls.__setitem__("v2", calls["v2"] + 1) or "T2"
    tok = client.login_handler.login_with_email("a@b.com", "password1")
    assert tok == "T2" and calls == {"v1": 0, "v2": 1}

    # force v1 via the v3 override
    client.login_handler._request_email_login = lambda *a, **k: calls.__setitem__("v1", calls["v1"] + 1) or "T1"
    tok2 = client.login_handler.login_with_email("a@b.com", "password1", v3=False)
    assert tok2 == "T1" and calls["v1"] == 1


# --------------------------------------------------------------- QR login

def test_request_sqr_legacy_bootstraps_e2ee_from_field4(client):
    """Legacy QR (v1) must extract e2eeInfo from field 4 and bootstrap keys
    -- previously completely missing."""
    lh = client.login_handler

    def fake_request(path, method, params, protocol=4, timeout=None,
                     extra_headers=None, response_model=None):
        if method == "createSession":
            return QRSessionResponse.from_dict({"1": "SQR123"})
        if method == "createQrCode":
            return QRCodeResponse.from_dict({"1": "https://qr.example/"})
        if method == "qrCodeLogin":
            return QRCodeLoginResponse.from_dict({
                "1": "PEM_CERT", "2": "AUTH_TOK_LEGACY",
                "4": {"keyId": 1, "publicKey": "AA==", "encryptedKeyChain": "AA=="},
                "5": "uMID",
            })
        raise AssertionError(method)

    lh._request = fake_request
    lh.check_qr_code_verified = lambda sqr, max_count=1, interval_sec=30: True
    lh.verify_certificate = lambda sqr, cert=None: (_ for _ in ()).throw(Exception("no cert"))
    lh.create_pin_code = lambda sqr: PinCodeResponse.from_dict({"1": "654321"})
    lh.check_pin_code_verified = lambda sqr, max_count=1, interval_sec=30: True

    bootstrap_calls = []
    lh._bootstrap_e2ee_keys = lambda info, secret: bootstrap_calls.append(info)

    token = lh._request_sqr()
    assert token == "AUTH_TOK_LEGACY"
    assert bootstrap_calls and bootstrap_calls[0]["publicKey"] == "AA=="


def test_request_sqr2_uses_forsecure_flow(android_client):
    """ForSecure QR (v2): createQrCodeForSecure -> long-poll with its
    parameters -> qrCodeLoginV2ForSecure (never the legacy qrCodeLoginV2)."""
    lh = android_client.login_handler
    calls = []

    def fake_request(path, method, params, protocol=4, timeout=None,
                     extra_headers=None, response_model=None):
        calls.append(method)
        if method == "createSession":
            return QRSessionResponse.from_dict({"1": "SQR456"})
        if method == "createQrCodeForSecure":
            return {1: "https://qr.example/cb", 2: 5, 3: 15, 4: "NONCE_ABC"}
        if method == "qrCodeLoginV2ForSecure":
            return QRCodeLoginV2Response.from_dict({
                "1": "PEM2",
                "3": {"1": "AUTH_TOK_V2", "2": "REFRESH2", "3": 7200, "6": 1700000000},
                "4": "uMID2",
                "6": {"e2eeInfo": '{"keyId": 2, "publicKey": "BB==", "encryptedKeyChain": "BB=="}'},
            })
        raise AssertionError(method)

    lh._request = fake_request
    poll_args = []

    def fake_poll(sqr, max_count=1, interval_sec=30):
        poll_args.append((max_count, interval_sec))
        return True

    lh.check_qr_code_verified = fake_poll
    lh.verify_certificate = lambda sqr, cert=None: (_ for _ in ()).throw(Exception("no cert"))
    lh.create_pin_code = lambda sqr: PinCodeResponse.from_dict({"1": "111222"})
    lh.check_pin_code_verified = lambda sqr, max_count=1, interval_sec=30: True

    bootstrap_calls = []
    lh._bootstrap_e2ee_keys = lambda info, secret: bootstrap_calls.append(info)

    token = lh._request_sqr2()
    assert token == "AUTH_TOK_V2"
    assert calls == ["createSession", "createQrCodeForSecure", "qrCodeLoginV2ForSecure"]
    assert poll_args == [(5, 15)]  # long-polling params from createQrCodeForSecure
    assert bootstrap_calls and bootstrap_calls[0]["keyId"] == 2  # from metaData JSON fallback
    assert android_client.token_manager.refresh_token == "REFRESH2"
    assert android_client.token_manager.expire == 1700007200


def test_check_qr_code_verified_retries_on_timeout_then_succeeds(client):
    lh = client.login_handler
    attempts = []

    def fake_request(path, method, params, protocol=4, timeout=None,
                     extra_headers=None, response_model=None):
        attempts.append(1)
        if len(attempts) < 3:
            raise Exception("Request timed out (status=408)")
        return {"ok": True}

    lh._request = fake_request
    assert lh.check_qr_code_verified("sqr1", max_count=3, interval_sec=1) is True
    assert len(attempts) == 3


def test_check_qr_code_verified_fatal_error_no_retry(client):
    lh = client.login_handler
    attempts = []

    def fake_request(path, method, params, protocol=4, timeout=None,
                     extra_headers=None, response_model=None):
        attempts.append(1)
        raise Exception("[401] Unauthorized")

    lh._request = fake_request
    with pytest.raises(Exception):
        lh.check_qr_code_verified("sqr2", max_count=5, interval_sec=1)
    assert len(attempts) == 1


def test_check_qr_code_verified_raises_on_final_timeout(client):
    lh = client.login_handler
    attempts = []

    def fake_request(path, method, params, protocol=4, timeout=None,
                     extra_headers=None, response_model=None):
        attempts.append(1)
        raise Exception("Timeout")

    lh._request = fake_request
    with pytest.raises(Exception):
        lh.check_qr_code_verified("sqr3", max_count=2, interval_sec=1)
    assert len(attempts) == 2


def test_poll_error_classification_httpx_timeout(client):
    """A genuine httpx timeout exception is always retryable, independent of
    its exact message text."""
    import httpx

    lh = client.login_handler
    assert lh._is_retryable_poll_error(httpx.ReadTimeout("boom")) is True
    assert lh._is_retryable_poll_error(httpx.ConnectTimeout("boom")) is True


def test_poll_error_classification_http_status(client):
    import httpx

    lh = client.login_handler
    req = httpx.Request("POST", "https://example.com")
    resp408 = httpx.Response(408, request=req)
    resp410 = httpx.Response(410, request=req)
    resp500 = httpx.Response(500, request=req)
    assert lh._is_retryable_poll_error(
        httpx.HTTPStatusError("x", request=req, response=resp408)
    ) is True
    assert lh._is_retryable_poll_error(
        httpx.HTTPStatusError("x", request=req, response=resp410)
    ) is True
    assert lh._is_retryable_poll_error(
        httpx.HTTPStatusError("x", request=req, response=resp500)
    ) is False


def test_poll_error_classification_regex_fallback(client):
    lh = client.login_handler
    assert lh._is_retryable_poll_error(Exception("Request timed out")) is True
    assert lh._is_retryable_poll_error(Exception("[401] Unauthorized")) is False


def test_check_qr_code_verified_request_shape(client):
    lh = client.login_handler
    captured = {}

    def fake_request(path, method, params, protocol=4, timeout=None,
                     extra_headers=None, response_model=None):
        captured.update(path=path, method=method, params=params, protocol=protocol,
                        extra_headers=extra_headers, timeout=timeout)
        return {"ok": True}

    lh._request = fake_request
    lh.check_qr_code_verified("sqrX", max_count=1, interval_sec=15)
    assert captured["path"] == lh.SECONDARY_QR_LP_ENDPOINT
    assert captured["method"] == "checkQrCodeVerified"
    assert captured["params"] == [[12, 1, [[11, 1, "sqrX"]]]]
    assert captured["extra_headers"] == {"x-lst": "15000", "x-line-access": "sqrX"}
    assert captured["timeout"] == 20.0  # (15000 + 5000) / 1000


# ------------------------------------------------------- individual RPCs

def test_verify_certificate_omits_none_cert(client):
    lh = client.login_handler
    captured = {}

    def fake(path, method, params, protocol=4, timeout=None, extra_headers=None, response_model=None):
        captured["params"] = params

    lh._request = fake
    lh.verify_certificate("sqrA", None)
    assert captured["params"] == [[12, 1, [[11, 1, "sqrA"], [11, 2, None]]]]
    lh.verify_certificate("sqrA", "CERTVAL")
    assert captured["params"] == [[12, 1, [[11, 1, "sqrA"], [11, 2, "CERTVAL"]]]]


def test_qr_code_login_uses_raw_device(client):
    lh = client.login_handler
    captured = {}
    lh._request = lambda path, method, params, **k: captured.update(params=params)
    lh.qr_code_login("sqrC")
    assert captured["params"] == [[12, 1, [[11, 1, "sqrC"], [11, 2, "DESKTOPWIN"], [2, 3, True]]]]


def test_qr_code_login_v2_defaults(client):
    lh = client.login_handler
    captured = {}
    lh._request = lambda path, method, params, **k: captured.update(params=params)
    lh.qr_code_login_v2("sqrD")
    assert captured["params"] == [[12, 1, [
        [11, 1, "sqrD"], [11, 2, "linejs-v2"], [11, 3, "evex-device"], [2, 4, True],
    ]]]


def test_create_qr_code_for_secure_shape(client):
    lh = client.login_handler
    captured = {}
    lh._request = lambda path, method, params, protocol=4, response_model=None, **k: (
        captured.update(path=path, method=method, params=params, response_model=response_model)
    )
    lh.create_qr_code_for_secure("sqrE")
    assert captured["path"] == lh.SECONDARY_QR_ENDPOINT
    assert captured["method"] == "createQrCodeForSecure"
    assert captured["params"] == [[12, 1, [[11, 1, "sqrE"]]]]
    assert captured["response_model"] is None  # raw dict, matches 本家's parse=false


def test_qr_code_login_v2_for_secure_echoes_nonce(client):
    lh = client.login_handler
    captured = {}
    lh._request = lambda path, method, params, **k: captured.update(method=method, params=params)
    lh.qr_code_login_v2_for_secure("sqrF", "nonceXYZ")
    assert captured["method"] == "qrCodeLoginV2ForSecure"
    assert captured["params"] == [[12, 1, [
        [11, 1, "sqrF"], [11, 2, "linejs-v2"], [11, 3, "evex-device"],
        [2, 4, True], [11, 5, "nonceXYZ"],
    ]]]


# --------------------------------------------------------- outer wrappers

def test_login_with_qr_calls_verify_login_key(client):
    """本家's withQrCode() unconditionally calls client.e2ee.verifyLoginKey()
    after a successful login."""
    client.login_handler.login_with_qr = lambda v3=None: "TOKEN123"
    verify_calls = []
    client.e2ee.verify_login_key = lambda: verify_calls.append(1)
    client.get_profile = lambda: type("P", (), {"mid": "u1", "display_name": "x"})()

    client.login_with_qr(save=False)
    assert verify_calls == [1]


def test_login_with_email_calls_verify_login_key(client):
    client.login_handler.login_with_email = lambda **kw: "TOKEN456"
    verify_calls = []
    client.e2ee.verify_login_key = lambda: verify_calls.append(1)
    client.get_profile = lambda: type("P", (), {"mid": "u1", "display_name": "x"})()

    client.login_with_email("a@b.com", "password1")
    assert verify_calls == [1]
