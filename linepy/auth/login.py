"""
Login Module for LINEPY

Faithful, function-by-function port of linejs
(resource/linejs/packages/linejs/base/login/mod.ts). Handles:
- Email/Password login (loginZ / loginV2, with the full E2EE PIN-verification
  handshake: /LF1 or /Q -> decodeE2EEKeyV1 -> encryptDeviceSecret ->
  confirmE2EELogin -> retry)
- QR code login (legacy SQR and the modern ForSecure flow)
- Token login
"""

import binascii
import logging
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Type, TypeVar

from ..config import PRIMARY_DEVICES, SECONDARY_DEVICE_FOR, is_v3_support
from ..exceptions import LoginError
from ..models.base import ModelBase
from ..models.custom.login import (
    LoginResponse,
    PinCodeResponse,
    QRCodeLoginResponse,
    QRCodeLoginV2Response,
    QRCodeResponse,
    QRSessionResponse,
    RSAKeyInfo,
)

if TYPE_CHECKING:
    from ..base import BaseClient

logger = logging.getLogger("linepy.auth.login")


T = TypeVar("T", bound=ModelBase)


# Regex patterns (from linejs base/login/regex.ts)
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
PASSWORD_REGEX = re.compile(r"^.{6,}$")  # At least 6 characters


def _dump_response(response: Any) -> Any:
    """Normalize a response (ModelBase dataclass or raw dict) to a string-keyed
    field-id dict, for storage.save_login_result and other dict-style
    consumers. Raw dicts (already int/str-keyed) pass through unchanged."""
    if hasattr(response, "model_dump"):
        return response.model_dump(by_alias=True)
    return response


def registration_auth_endpoint(device: str) -> str:
    """Port of 本家 ``registrationAuthEndpoint``.

    ANDROID / ANDROIDSECONDARY use ``/api/v4p/rs``; every other device uses
    the legacy ``/api/v3p/rs``.
    """
    return "/api/v4p/rs" if device in ("ANDROID", "ANDROIDSECONDARY") else "/api/v3p/rs"


class Login:
    """
    Login handler for LINE authentication.

    Faithful port of linejs' ``Login`` class (base/login/mod.ts).
    """

    # Fixed endpoints (from linejs)
    TALK_ENDPOINT = "/api/v3/TalkService.do"
    SECONDARY_QR_ENDPOINT = "/acct/lgn/sq/v1"
    SECONDARY_QR_LP_ENDPOINT = "/acct/lp/lgn/sq/v1"
    E2EE_VERIFY_ENDPOINT = "/LF1"
    LEGACY_VERIFY_ENDPOINT = "/Q"
    RESPOND_E2EE_LOGIN_ENDPOINT = "/S4"

    def __init__(self, client: "BaseClient"):
        self.client = client
        self._cert_cache: Dict[str, str] = {}
        self._qr_cert: Optional[str] = None
        # Populated by *_sqr* / *_email_login* helpers so BaseClient.login_with_*
        # can persist tokens / call verify_login_key() after a successful login,
        # mirroring 本家's outer withQrCode()/withPassword() wrappers.
        self._last_login_response: Any = None
        self._last_sqr_secret: Optional[bytes] = None

    def auth_endpoint(self) -> str:
        """``registrationAuthEndpoint(this.client.device)``."""
        return registration_auth_endpoint(self.client.device)

    # ========== Certificate Management ==========
    # registerCert / getCert / registerQrCert / getQrCert

    def register_cert(self, email: str, cert: str):
        """Save certificate for future logins (``registerCert``)."""
        self._cert_cache[f"cert:{email}"] = cert

    def get_cert(self, email: str) -> Optional[str]:
        """Get saved certificate (``getCert``)."""
        return self._cert_cache.get(f"cert:{email}")

    def register_qr_cert(self, cert: str):
        """Save QR login certificate (``registerQrCert``)."""
        self._qr_cert = cert

    def get_qr_cert(self) -> Optional[str]:
        """Get saved QR certificate (``getQrCert``)."""
        return self._qr_cert

    # ========== RSA ==========

    def get_rsa_key_info(self, provider: int = 0) -> RSAKeyInfo:
        """``getRSAKeyInfo``: RSA public key for credential encryption.

        Path is always the fixed ``/api/v3/TalkService.do`` (NOT the
        device-dependent registration endpoint), protocol 3 (binary).
        """
        return self._request(
            path=self.TALK_ENDPOINT,
            method="getRSAKeyInfo",
            params=[[12, 1, [[8, 2, provider]]]],
            protocol=3,
            response_model=RSAKeyInfo,
        )

    def _encrypt_rsa(self, message: str, nvalue: str, evalue: str) -> str:
        """RSA PKCS1v1.5 encrypt -> hex string (matches 本家's ``getRSACrypto``,
        which uses node-bignumber's ``Key.encrypt()`` == RSA_PKCS1_PADDING)."""
        from ..crypto.primitives import RSA, PKCS1_v1_5

        n = int(nvalue, 16)
        e = int(evalue, 16)
        key = RSA.construct((n, e))
        cipher = PKCS1_v1_5.new(key)
        encrypted = cipher.encrypt(message.encode("utf-8"))
        return binascii.hexlify(encrypted).decode()

    @staticmethod
    def _build_login_message(session_key: str, email: str, password: str) -> str:
        """``chr(len)+data`` for each field, matching 本家's
        ``String.fromCharCode(x.length) + x`` concatenation exactly."""
        return (
            chr(len(session_key)) + session_key
            + chr(len(email)) + email
            + chr(len(password)) + password
        )

    # ========== E2EE helpers (thin wrappers over the verified E2EE engine) ==========

    def _create_secret(self, base64_only: bool = False) -> Tuple[bytes, str]:
        """``client.e2ee.createSqrSecret()``."""
        return self.client.e2ee.create_sqr_secret(base64_only=base64_only)

    # ========== Top-level login dispatch ==========

    def login_with_token(self, auth_token: str):
        """Login with an existing auth token (matches the ``authToken``
        branch of 本家's ``login()``)."""
        self.client.set_auth_token(auth_token)

    def login_with_email(
        self,
        email: str,
        password: str,
        pincode: str = "114514",
        e2ee: bool = True,
        v3: Optional[bool] = None,
    ) -> str:
        """``withPassword``: dispatch to the v1 (loginZ) or v2 (loginV2) flow.

        Only the legacy v1 flow (``requestEmailLogin``) can disable E2EE; the
        v2 flow (``requestEmailLoginV2``) is always E2EE, matching 本家 (it
        takes no ``enableE2EE`` parameter at all).
        """
        if not EMAIL_REGEX.match(email):
            raise LoginError("Invalid email format")
        if not PASSWORD_REGEX.match(password):
            raise LoginError("Password must be at least 6 characters")

        use_v3 = is_v3_support(self.client.device) if v3 is None else v3
        if use_v3:
            auth_token = self._request_email_login_v2(email, password, pincode)
        else:
            auth_token = self._request_email_login(email, password, pincode, e2ee)
        return auth_token

    def login_with_qr(self, v3: Optional[bool] = None) -> str:
        """``withQrCode``: dispatch to the legacy or ForSecure QR flow."""
        self._reject_primary_device()
        use_v3 = is_v3_support(self.client.device) if v3 is None else v3
        if use_v3:
            return self._request_sqr2()
        return self._request_sqr()

    def _reject_primary_device(self) -> None:
        """QR login registers a *secondary* device, so a primary one cannot use it.

        The server does reject it, but with SecondaryQrCodeErrorCode 101
        (APP_UPGRADE_REQUIRED) -- "LINEアプリをアップデートして、もう一度お試しく
        ださい。" -- which sends people chasing an app version that is not the
        problem. Verified against /acct/lgn/sq/v1 createSession: ANDROID and
        IOS are refused; ANDROIDSECONDARY, IOSIPAD, DESKTOPWIN, DESKTOPMAC,
        WATCHOS and WEAROS all succeed on the very same app versions.
        """
        device = self.client.device
        if device not in PRIMARY_DEVICES:
            return

        alternative = SECONDARY_DEVICE_FOR.get(device)
        raise LoginError(
            f"QR login is not available for {device}: it registers a secondary "
            f"device, and {device} is a primary one (the primary device is what "
            f"approves the QR code). "
            + (
                f"Use BaseClient({alternative!r}) to log in by QR, or "
                f"login_with_email() to log in as {device}."
                if alternative
                else "Use a secondary device type, or login_with_email()."
            )
        )

    # ========== Email/Password login (v1: loginZ) ==========

    def _request_email_login(
        self,
        email: str,
        password: str,
        constant_pincode: str = "114514",
        enable_e2ee: bool = True,
    ) -> str:
        """``requestEmailLogin``: legacy loginZ flow, full E2EE handshake."""
        if len(constant_pincode) != 6:
            raise LoginError("The constant pincode should be 6 digits")

        rsa_key = self.get_rsa_key_info()
        message = self._build_login_message(rsa_key.sessionKey, email, password)

        secret: Optional[bytes] = None
        secret_pk: Optional[str] = None
        e2ee_data: Optional[bytes] = None
        if enable_e2ee:
            secret, secret_pk = self._create_secret(base64_only=True)
            e2ee_data = self._build_e2ee_data(constant_pincode, secret_pk)

        encrypted_message = self._encrypt_rsa(message, rsa_key.nvalue, rsa_key.evalue)
        cert = self.get_cert(email)

        response = self._login_v2(
            keynm=rsa_key.keynm,
            encrypted_message=encrypted_message,
            verifier=None,
            secret=e2ee_data,
            cert=cert,
            method="loginZ",
        )

        if not response.auth_token:
            pin = response.pincode or constant_pincode
            print(f"[Login] Enter PIN code: {pin}")
            self.client.emit("pincall", pin)

            if enable_e2ee and secret is not None:
                new_verifier = self._do_e2ee_pin_exchange(response.verifier, secret)
            else:
                new_verifier = self._do_legacy_pin_exchange(response.verifier)

            response = self._login_v2(
                keynm=rsa_key.keynm,
                encrypted_message=encrypted_message,
                verifier=new_verifier,
                secret=e2ee_data,
                cert=cert,
                method="loginZ",
            )

        if response.certificate:
            self.client.emit("update:cert", response.certificate)
            self.register_cert(email, response.certificate)

        if not response.auth_token:
            raise LoginError("Login failed: no auth token received")

        self._last_sqr_secret = secret
        self._last_login_response = _dump_response(response)
        return response.auth_token

    # ========== Email/Password login (v2: loginV2, always E2EE) ==========

    def _request_email_login_v2(
        self,
        email: str,
        password: str,
        constant_pincode: str = "114514",
    ) -> str:
        """``requestEmailLoginV2``: v3-device loginV2 flow, always E2EE."""
        if len(constant_pincode) != 6:
            raise LoginError("The constant pincode should be 6 digits")

        rsa_key = self.get_rsa_key_info()
        message = self._build_login_message(rsa_key.sessionKey, email, password)

        secret, secret_pk = self._create_secret(base64_only=True)
        e2ee_data = self._build_e2ee_data(constant_pincode, secret_pk)

        encrypted_message = self._encrypt_rsa(message, rsa_key.nvalue, rsa_key.evalue)
        cert = self.get_cert(email)

        response = self._login_v2_raw(
            keynm=rsa_key.keynm,
            encrypted_message=encrypted_message,
            verifier=None,
            secret=e2ee_data,
            cert=cert,
            method="loginV2",
        )

        token_info = response.get(9)
        if not token_info:
            verifier = response.get(3)
            print(f"[Login] Enter PIN code: {constant_pincode}")
            self.client.emit("pincall", constant_pincode)

            new_verifier = self._do_e2ee_pin_exchange(verifier, secret)

            response = self._login_v2_raw(
                keynm=rsa_key.keynm,
                encrypted_message=encrypted_message,
                verifier=new_verifier,
                secret=e2ee_data,
                cert=cert,
                method="loginV2",
            )
            token_info = response.get(9)

        certificate = response.get(2)
        if certificate:
            self.client.emit("update:cert", certificate)
            self.register_cert(email, certificate)

        if not token_info:
            raise LoginError("Login failed: no token info")

        auth_token = token_info.get(1)
        refresh_token = token_info.get(2)
        expires_in = token_info.get(3)
        iat = token_info.get(6)

        # 本家 unconditionally persists refreshToken/expire here.
        if refresh_token:
            self.client.token_manager.refresh_token = refresh_token
        if expires_in is not None and iat is not None:
            self.client.token_manager.expire = iat + expires_in

        self._last_sqr_secret = secret
        self._last_login_response = _dump_response(response)
        return auth_token

    # ========== Shared E2EE PIN-verification exchange ==========
    # /LF1 -> decodeE2EEKeyV1 -> encryptDeviceSecret -> confirmE2EELogin

    def _build_e2ee_data(self, constant_pincode: str, secret_pk_b64: str) -> bytes:
        """``encryptAESECB(getSHA256Sum(pincode), Buffer.from(secretPK,"base64"))``."""
        import base64

        e2ee = self.client.e2ee
        pin_hash = e2ee.get_sha256_sum(constant_pincode)
        return e2ee.encrypt_aes_ecb(pin_hash, base64.b64decode(secret_pk_b64))

    def _do_e2ee_pin_exchange(self, verifier: str, secret: bytes) -> str:
        """GET /LF1, decode the keychain, build the device secret, and call
        ``confirmE2EELogin`` to obtain the new verifier for the login retry.

        This is the previously-unimplemented core of the E2EE PIN handshake
        (本家's ``requestEmailLogin``/``requestEmailLoginV2`` "if (enableE2EE
        && secret)" branch).
        """
        import base64

        headers = {
            "user-agent": self.client.request.user_agent,
            "x-line-application": self.client.request.device_name,
            "x-line-access": verifier,
            "x-lal": "ja_JP",
            "x-lpv": "1",
            "x-lhm": "GET",
            "accept-encoding": "gzip",
        }
        url = f"https://{self.client.request.HOST}{self.E2EE_VERIFY_ENDPOINT}"
        http_response = self.client.request.get(url, headers=headers, timeout=120)
        http_response.raise_for_status()
        e2ee_info = http_response.json().get("result")
        if not e2ee_info:
            raise LoginError("/LF1 response has no 'result'")
        metadata = e2ee_info.get("metadata") if isinstance(e2ee_info, dict) else None
        if not metadata:
            raise LoginError("/LF1 result has no 'metadata'")

        self.client.e2ee.decode_e2ee_key_v1(metadata, secret)
        device_secret = self.client.e2ee.encrypt_device_secret(
            base64.b64decode(metadata["publicKey"]),
            secret,
            base64.b64decode(metadata["encryptedKeyChain"]),
        )
        return self.confirm_e2ee_login(verifier, device_secret)

    def _do_legacy_pin_exchange(self, verifier: str) -> str:
        """GET /Q and return ``result.verifier`` (non-E2EE legacy path)."""
        headers = {
            "accept": "application/x-thrift",
            "user-agent": self.client.request.user_agent,
            "x-line-application": self.client.request.device_name,
            "x-line-access": verifier,
            "x-lal": "ja_JP",
            "x-lpv": "1",
            "x-lhm": "GET",
            "accept-encoding": "gzip",
        }
        url = f"https://{self.client.request.HOST}{self.LEGACY_VERIFY_ENDPOINT}"
        http_response = self.client.request.get(url, headers=headers, timeout=120)
        http_response.raise_for_status()
        result = http_response.json().get("result") or {}
        return result.get("verifier", verifier)

    def confirm_e2ee_login(self, verifier: str, device_secret: bytes) -> str:
        """``confirmE2EELogin(verifier, deviceSecret) -> string`` (new verifier)."""
        return self._request(
            path=self.auth_endpoint(),
            method="confirmE2EELogin",
            params=[[11, 1, verifier], [11, 2, device_secret]],
            protocol=3,
        )

    def respond_e2ee_login_request(
        self,
        verifier: str,
        public_key: Dict[str, Any],
        encrypted_key_chain: bytes,
        hash_key_chain: bytes,
        error_code: int = 0,
    ) -> Any:
        """``respondE2EELoginRequest``: primary device approves a pending
        secondary-device login. ``public_key`` may carry ``version``/``keyId``/
        ``keyData`` (field 3 is intentionally absent, matching the
        ``E2EEPublicKey`` thrift struct)."""
        pk_fields = []
        if public_key.get("version") is not None:
            pk_fields.append([8, 1, public_key["version"]])
        if public_key.get("keyId") is not None:
            pk_fields.append([8, 2, public_key["keyId"]])
        if public_key.get("keyData") is not None:
            pk_fields.append([11, 4, public_key["keyData"]])

        return self._request(
            path=self.RESPOND_E2EE_LOGIN_ENDPOINT,
            method="respondE2EELoginRequest",
            params=[
                [11, 1, verifier],
                [12, 2, pk_fields],
                [11, 3, encrypted_key_chain],
                [11, 4, hash_key_chain],
                [8, 5, error_code],
            ],
            protocol=4,
        )

    # ========== Core loginV2/loginZ RPC ==========

    def _build_login_v2_params(
        self,
        keynm: str,
        encrypted_message: str,
        verifier: Optional[str],
        secret: Optional[bytes],
        cert: Optional[str],
    ) -> List:
        """Struct fields shared by ``loginV2``/``loginZ``, matching 本家's
        private ``loginV2`` builder exactly. ``deviceName`` (field 7) is the
        raw device string (``client.device``, e.g. "DESKTOPWIN"), NOT a
        display/system name. Fields left ``None`` are omitted entirely,
        matching 本家's ``undefined``-skip behaviour.
        """
        # 本家: `if (!secret) loginType = 0; if (verifier) loginType = 1;` --
        # JS objects (a Buffer) are truthy even when empty, so this checks
        # identity/None-ness, not Python bytes truthiness (b"" is falsy in
        # Python but a present, non-empty-semantics Buffer in JS).
        login_type = 2  # E2EE
        if secret is None:
            login_type = 0  # Normal
        if verifier:
            login_type = 1  # Verifier retry

        return [
            [8, 1, login_type],
            [8, 2, 1],  # identityProvider = LINE
            [11, 3, keynm],
            [11, 4, encrypted_message],
            [2, 5, False],  # keepLoggedIn (本家 hardcodes this)
            [11, 6, ""],
            [11, 7, self.client.device],
            [11, 8, cert],
            [11, 9, verifier],
            [11, 10, secret],
            [8, 11, 1],
            [11, 12, "System Product Name"],
        ]

    def _login_v2(
        self,
        keynm: str,
        encrypted_message: str,
        verifier: Optional[str],
        secret: Optional[bytes],
        cert: Optional[str],
        method: str = "loginZ",
    ) -> LoginResponse:
        """loginZ call, response parsed against the named ``LoginResult``
        struct (fields 1-8)."""
        params = [[12, 2, self._build_login_v2_params(
            keynm, encrypted_message, verifier, secret, cert
        )]]
        return self._request(
            path=self.auth_endpoint(),
            method=method,
            params=params,
            protocol=3,
            response_model=LoginResponse,
        )

    def _login_v2_raw(
        self,
        keynm: str,
        encrypted_message: str,
        verifier: Optional[str],
        secret: Optional[bytes],
        cert: Optional[str],
        method: str = "loginV2",
    ) -> Dict[int, Any]:
        """loginV2 call, returned as the raw field-id dict (本家 parses this
        with ``parse=false`` -- no named struct)."""
        params = [[12, 2, self._build_login_v2_params(
            keynm, encrypted_message, verifier, secret, cert
        )]]
        return self._request(
            path=self.auth_endpoint(),
            method=method,
            params=params,
            protocol=3,
            response_model=None,
        )

    # ========== QR Code Login (legacy v1: SQR) ==========

    def _request_sqr(self) -> str:
        """``requestSQR``: legacy (non-ForSecure) QR login."""
        session = self._request(
            path=self.SECONDARY_QR_ENDPOINT,
            method="createSession",
            params=[],
            protocol=4,
            response_model=QRSessionResponse,
        )
        sqr = session.sqr

        qr_response = self._request(
            path=self.SECONDARY_QR_ENDPOINT,
            method="createQrCode",
            params=[[12, 1, [[11, 1, sqr]]]],
            protocol=4,
            response_model=QRCodeResponse,
        )
        secret, secret_url = self._create_secret()
        url = qr_response.url + secret_url

        self._print_qr(url)
        self.client.emit("qrcall", url)

        if not self.check_qr_code_verified(sqr):
            raise LoginError("TimeoutError: checkQrCodeVerified timed out")

        try:
            self.verify_certificate(sqr, self.get_qr_cert())
        except Exception:
            pincode = self.create_pin_code(sqr).pincode
            self.client.emit("pincall", pincode)
            print(f"[Login] Enter PIN code: {pincode}")
            self.check_pin_code_verified(sqr)

        response = self.qr_code_login(sqr)

        if response.certificate:
            self.client.emit("update:qrcert", response.certificate)
            self.register_qr_cert(response.certificate)

        self._bootstrap_e2ee_keys(response.e2ee_info, secret)

        if not response.auth_token:
            raise LoginError("No auth token in response")

        self._last_sqr_secret = secret
        self._last_login_response = _dump_response(response)
        return response.auth_token

    # ========== QR Code Login (v2: ForSecure) ==========

    def _request_sqr2(self) -> str:
        """``requestSQR2``: the modern ForSecure QR login flow used by
        LINE 26+ Android clients. The legacy ``createQrCode`` RPC still
        exists but the server marks those sessions expired immediately."""
        session = self._request(
            path=self.SECONDARY_QR_ENDPOINT,
            method="createSession",
            params=[],
            protocol=4,
            response_model=QRSessionResponse,
        )
        sqr = session.sqr

        for_secure = self.create_qr_code_for_secure(sqr)
        # Response shape per 本家 (oc4.i): 1=callbackUrl, 2=longPollingMaxCount,
        # 3=longPollingIntervalSec, 4=nonce.
        url = for_secure.get(1, "")
        long_polling_max_count = for_secure.get(2) or 12
        long_polling_interval_sec = for_secure.get(3) or 30
        nonce = for_secure.get(4) or ""

        secret, secret_url = self._create_secret()
        url = url + secret_url

        self._print_qr(url)
        self.client.emit("qrcall", url)

        if not self.check_qr_code_verified(
            sqr, long_polling_max_count, long_polling_interval_sec
        ):
            raise LoginError("TimeoutError: checkQrCodeVerified timed out")

        try:
            self.verify_certificate(sqr, self.get_qr_cert())
        except Exception:
            pincode = self.create_pin_code(sqr).pincode
            print(f"[Login] Enter PIN code: {pincode}")
            self.client.emit("pincall", pincode)
            self.check_pin_code_verified(
                sqr, long_polling_max_count, long_polling_interval_sec
            )

        response = self.qr_code_login_v2_for_secure(sqr, nonce)

        if response.certificate:
            self.client.emit("update:qrcert", response.certificate)
            self.register_qr_cert(response.certificate)

        # e2eeInfo historically arrived in field 10 on the non-ForSecure
        # response, and in metaData["e2eeInfo"] on ForSecure. Try both.
        e2ee_info = response.e2ee_info
        if not e2ee_info and response.metadata:
            e2ee_info = response.metadata.get("e2eeInfo")
            if isinstance(e2ee_info, str):
                import json as _json
                try:
                    e2ee_info = _json.loads(e2ee_info)
                except Exception:
                    e2ee_info = None
        self._bootstrap_e2ee_keys(e2ee_info, secret)

        token_info = response.token_info
        if not token_info:
            raise LoginError("No token info in response")

        if token_info.refresh_token:
            self.client.token_manager.refresh_token = token_info.refresh_token
        if token_info.expires_in is not None and token_info.iat is not None:
            self.client.token_manager.expire = token_info.iat + token_info.expires_in

        self._last_sqr_secret = secret
        self._last_login_response = _dump_response(response)
        return token_info.auth_token

    def _bootstrap_e2ee_keys(self, e2ee_info: Optional[Dict[str, Any]], secret: bytes) -> None:
        """``decodeE2EEKeyV1(e2eeInfo, secret)`` or, failing that,
        ``registerE2EEKeyPair()`` -- matches both ``requestSQR`` and
        ``requestSQR2``'s post-login E2EE bootstrap exactly."""
        e2ee_key_result = None
        if e2ee_info:
            try:
                e2ee_key_result = self.client.e2ee.decode_e2ee_key_v1(e2ee_info, secret)
            except Exception as exc:
                logger.warning("decodeE2EEKeyV1 failed: %s", exc)
        if not e2ee_key_result:
            try:
                self.client.e2ee.register_e2ee_key_pair()
            except Exception as exc:
                logger.warning("registerE2EEKeyPair failed: %s", exc)

    @staticmethod
    def _print_qr(url: str) -> None:
        print(f"[Login] QR Code URL: {url}")
        try:
            import qrcode

            qr = qrcode.QRCode(border=1)
            qr.add_data(url)
            qr.make(fit=True)
            qr.print_ascii(invert=True)
            print("[Login] Please scan the QR code above.")
        except ImportError:
            pass
        except Exception:
            pass

    # ========== QR Code Login RPCs ==========
    # createSession / createQrCode / checkQrCodeVerified / verifyCertificate /
    # createPinCode / checkPinCodeVerified / qrCodeLogin / qrCodeLoginV2 /
    # createQrCodeForSecure / qrCodeLoginV2ForSecure

    def check_qr_code_verified(
        self, qrcode: str, max_count: int = 1, interval_sec: int = 30
    ) -> bool:
        """``checkQrCodeVerified``: long-poll up to ``max_count`` times of
        ``interval_sec`` seconds each. A timeout on the LAST attempt (or any
        other error) is fatal; a timeout on an earlier attempt just means
        "no user action yet" and the loop continues.
        """
        return self._poll_verified(
            "checkQrCodeVerified", qrcode, max_count, interval_sec, "scanned"
        )

    def check_pin_code_verified(
        self, qrcode: str, max_count: int = 1, interval_sec: int = 30
    ) -> bool:
        """``checkPinCodeVerified``: same long-polling contract as
        :meth:`check_qr_code_verified`."""
        return self._poll_verified(
            "checkPinCodeVerified", qrcode, max_count, interval_sec, "verified"
        )

    # Matches 本家's `/Timeout|timed out|status=408|status=410/i` (its custom
    # fetch wrapper embeds "status=NNN" in the message text literally).
    _RETRYABLE_RE = re.compile(r"timeout|timed out|status=408|status=410", re.IGNORECASE)

    def _is_retryable_poll_error(self, exc: Exception) -> bool:
        """A timed-out long-poll just means "no user action yet" and the
        loop should continue; anything else is fatal. Checked structurally
        first (httpx exception types/status codes), then via 本家's regex as
        a fallback for any other exception shape (e.g. a wrapped LoginError).
        """
        try:
            import httpx

            if isinstance(exc, httpx.TimeoutException):
                return True
            if isinstance(exc, httpx.HTTPStatusError):
                return exc.response.status_code in (408, 410)
        except ImportError:
            pass
        return bool(self._RETRYABLE_RE.search(str(exc)))

    def _poll_verified(
        self, method: str, qrcode: str, max_count: int, interval_sec: int, label: str
    ) -> bool:
        interval_ms = interval_sec * 1000
        for i in range(max_count):
            try:
                self._request(
                    path=self.SECONDARY_QR_LP_ENDPOINT,
                    method=method,
                    params=[[12, 1, [[11, 1, qrcode]]]],
                    protocol=4,
                    extra_headers={
                        "x-lst": str(interval_ms),
                        "x-line-access": qrcode,
                    },
                    timeout=(interval_ms + 5000) / 1000,
                )
                logger.info("QR code %s", label)
                return True
            except Exception as exc:
                if self._is_retryable_poll_error(exc) and i < max_count - 1:
                    continue
                raise
        return False

    def verify_certificate(self, qrcode: str, cert: Optional[str] = None) -> Any:
        return self._request(
            path=self.SECONDARY_QR_ENDPOINT,
            method="verifyCertificate",
            params=[[12, 1, [[11, 1, qrcode], [11, 2, cert]]]],
            protocol=4,
        )

    def create_pin_code(self, qrcode: str) -> PinCodeResponse:
        return self._request(
            path=self.SECONDARY_QR_ENDPOINT,
            method="createPinCode",
            params=[[12, 1, [[11, 1, qrcode]]]],
            protocol=4,
            response_model=PinCodeResponse,
        )

    def qr_code_login(
        self, auth_session_id: str, auto_login_is_required: bool = True
    ) -> QRCodeLoginResponse:
        return self._request(
            path=self.SECONDARY_QR_ENDPOINT,
            method="qrCodeLogin",
            params=[[12, 1, [
                [11, 1, auth_session_id],
                [11, 2, self.client.device],
                [2, 3, auto_login_is_required],
            ]]],
            protocol=4,
            response_model=QRCodeLoginResponse,
        )

    def qr_code_login_v2(
        self,
        auth_session_id: str,
        model_name: str = "evex-device",
        system_name: str = "linejs-v2",
        auto_login_is_required: bool = True,
    ) -> QRCodeLoginV2Response:
        return self._request(
            path=self.SECONDARY_QR_ENDPOINT,
            method="qrCodeLoginV2",
            params=[[12, 1, [
                [11, 1, auth_session_id],
                [11, 2, system_name],
                [11, 3, model_name],
                [2, 4, auto_login_is_required],
            ]]],
            protocol=4,
            response_model=QRCodeLoginV2Response,
        )

    def create_qr_code_for_secure(self, auth_session_id: str) -> Dict[int, Any]:
        """``createQrCodeForSecure``. Response fields (schema ``oc4.i``):
        1=callbackUrl, 2=longPollingMaxCount, 3=longPollingIntervalSec,
        4=nonce. Returned as a raw field-id dict (本家 parses with
        ``parse=false``)."""
        return self._request(
            path=self.SECONDARY_QR_ENDPOINT,
            method="createQrCodeForSecure",
            params=[[12, 1, [[11, 1, auth_session_id]]]],
            protocol=4,
            response_model=None,
        )

    def qr_code_login_v2_for_secure(
        self,
        auth_session_id: str,
        nonce: str,
        model_name: str = "evex-device",
        system_name: str = "linejs-v2",
        auto_login_is_required: bool = True,
    ) -> QRCodeLoginV2Response:
        """``qrCodeLoginV2ForSecure``: echoes back the ``nonce`` from
        :meth:`create_qr_code_for_secure`. Schema ``oc4.p``: 1=authSessionId,
        2=systemName, 3=modelName, 4=autoLoginIsRequired, 5=nonce."""
        return self._request(
            path=self.SECONDARY_QR_ENDPOINT,
            method="qrCodeLoginV2ForSecure",
            params=[[12, 1, [
                [11, 1, auth_session_id],
                [11, 2, system_name],
                [11, 3, model_name],
                [2, 4, auto_login_is_required],
                [11, 5, nonce],
            ]]],
            protocol=4,
            response_model=QRCodeLoginV2Response,
        )

    # ========== Request Helper ==========

    def _request(
        self,
        path: str,
        method: str,
        params: List,
        protocol: int = 4,
        timeout: Optional[float] = None,
        extra_headers: Optional[Dict] = None,
        response_model: Optional[Type[T]] = None,
    ) -> Any:
        """Send a Thrift request using linejs-style ``[[type, id, value], ...]``
        params, mirroring 本家's ``client.request.request(...)``.
        """
        from ..protocol.thrift import write_thrift

        data = write_thrift(params, method, protocol)

        response = self.client.request.request(
            path=path,
            data=data,
            protocol=protocol,
            timeout=timeout,
            extra_headers=extra_headers,
        )

        if isinstance(response, dict) and "error" in response:
            error = response["error"]
            error_code = error.get("code") or error.get("_data", {}).get(1)
            error_msg = error.get("message") or error.get("_data", {}).get(
                2, "Unknown error"
            )
            raise LoginError(f"[{error_code}] {error_msg}")

        if response_model:
            from ..services.base import validate_response_model

            return validate_response_model(response, response_model)

        return response
