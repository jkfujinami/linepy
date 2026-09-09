# -*- coding: utf-8 -*-
"""
LEGY Encrypted Transport for LINEPY

Faithful Python port of linejs:
  - resource/linejs/packages/linejs/base/request/legy.ts
  - resource/linejs/packages/linejs/base/request/auth_token.ts

Implements the `/enc` encrypted transport used by the LINE Talk/Square APIs:
AES-128-CBC body encryption with a fixed IV, an RSA-OAEP(SHA1) wrapped session
key carried in the ``x-lcs`` header, LEGY inner-header framing, and the
xxhash32-based ``legyHmac`` integrity trailer.
"""

import base64
import hashlib
import hmac as _hmac
import json
import os
import re
import struct
import time
from typing import Dict, Optional, Tuple

from ..crypto.primitives import AES, PKCS1_OAEP, RSA, SHA1, xxh32_intdigest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LEGY_ENDPOINT = "https://gf.line.naver.jp/enc"
LEGY_LE = "7"
LEGY_LAP = "5"
LEGY_LCS_PREFIX = "0008"
LEGY_IV = bytes(
    [78, 9, 72, 62, 56, 245, 255, 114, 128, 18, 123, 158, 251, 92, 45, 51]
)

LINE_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAsMC6HAYeMq4R59e2yRw6
W1OWT2t9aepiAp4fbSCXzRj7A29BOAFAvKlzAub4oxN13Nt8dbcB+ICAufyDnN5N
d3+vXgDxEXZ/sx2/wuFbC3B3evSNKR4hKcs80suRs8aL6EeWi+bAU2oYIc78Bbqh
Nzx0WCzZSJbMBFw1VlsU/HQ/XdiUufopl5QSa0S246XXmwJmmXRO0v7bNvrxaNV0
cbviGkOvTlBt1+RerIFHMTw3SwLDnCOolTz3CuE5V2OrPZCmC0nlmPRzwUfxoxxs
/6qFdpZNoORH/s5mQenSyqPkmH8TBOlHJWPH3eN1k6aZIlK5S54mcUb/oNRRq9wD
1wIDAQAB
-----END PUBLIC KEY-----"""

# Talk/Square paths eligible for LEGY encryption (see isLegyTalkPath in mod.ts).
LEGY_TALK_PATHS = frozenset(
    ["/S3", "/S4", "/V4", "/SYNC3", "/SYNC4", "/P4", "/P5", "/NP4", "/NP5",
     "/C5", "/CA5", "/ECA5"]
)


# ---------------------------------------------------------------------------
# Header framing
# ---------------------------------------------------------------------------

def _u16be(value: int) -> bytes:
    return struct.pack(">H", value)


def encode_legy_headers(headers: Dict[str, str]) -> bytes:
    """Serialize inner LEGY headers: [bodyLen 2B][count 2B][ (klen key vlen val) ... ]."""
    parts = [_u16be(len(headers))]
    for key, value in headers.items():
        key_buf = key.encode("ascii")
        value_buf = value.encode("utf-8")
        parts.append(_u16be(len(key_buf)))
        parts.append(key_buf)
        parts.append(_u16be(len(value_buf)))
        parts.append(value_buf)
    body = b"".join(parts)
    return _u16be(len(body)) + body


def decode_legy_headers(data: bytes) -> Tuple[Dict[str, str], bytes]:
    """Split serialized response into (headers, remaining body)."""
    offset = 0

    def read_u16() -> int:
        nonlocal offset
        value = struct.unpack_from(">H", data, offset)[0]
        offset += 2
        return value

    data_length = read_u16() + 2
    count = read_u16()
    headers: Dict[str, str] = {}
    for _ in range(count):
        key_length = read_u16()
        key = data[offset:offset + key_length].decode("ascii")
        offset += key_length
        value_length = read_u16()
        value = data[offset:offset + value_length].decode("utf-8", "replace")
        offset += value_length
        headers[key] = value
    return headers, data[data_length:]


# ---------------------------------------------------------------------------
# xxhash32 / legyHmac
# ---------------------------------------------------------------------------

def xxhash32(data: bytes, seed: int = 0) -> int:
    """xxHash32 (matches the hand-rolled implementation in legy.ts)."""
    return xxh32_intdigest(data, seed)


def legy_hmac(key: bytes, data: bytes) -> bytes:
    """xxhash32-based double HMAC used as the LEGY integrity trailer (4 bytes)."""
    opad = bytes(0x5C ^ key[i] for i in range(16))
    ipad = bytes(0x36 ^ key[i] for i in range(16))
    inner_hex = format(xxhash32(ipad + data), "08x")
    outer_hex = format(xxhash32(opad + bytes.fromhex(inner_hex)), "08x")
    return bytes.fromhex(outer_hex)


# ---------------------------------------------------------------------------
# PKCS7
# ---------------------------------------------------------------------------

def _pkcs7_pad(buf: bytes, block_size: int = 16) -> bytes:
    size = block_size - (len(buf) % block_size)
    return buf + bytes([size]) * size


def _pkcs7_unpad(buf: bytes) -> bytes:
    if not buf:
        return buf
    size = buf[-1]
    return buf[:-size] if 0 < size <= 16 else buf


# ---------------------------------------------------------------------------
# Auth token resolution (auth_token.ts port)
# ---------------------------------------------------------------------------

def _base64url_decode(value: str) -> bytes:
    normalized = value.replace("-", "+").replace("_", "/")
    padded = normalized + "=" * ((4 - len(normalized) % 4) % 4)
    return base64.b64decode(padded)


def is_jwt(value: str) -> bool:
    parts = value.split(".")
    if len(parts) != 3:
        return False
    try:
        header = json.loads(_base64url_decode(parts[0]).decode("utf-8"))
        payload = json.loads(_base64url_decode(parts[1]).decode("utf-8"))
    except Exception:
        return False
    return isinstance(header.get("alg"), str) and any(
        k in payload for k in ("ver", "scp", "exp", "iat", "sub", "iss", "aud")
    )


def is_primary_access_token(value: str) -> bool:
    colon = value.find(":")
    if colon == -1:
        return False
    payload = value[colon + 1:]
    first = payload.split(".")[0]
    try:
        return base64.b64decode(first + "=" * (-len(first) % 4)).decode(
            "utf-8", "replace"
        ).startswith("iat:")
    except Exception:
        return False


_AUTH_KEY_MID_RE = re.compile(r"^[a-z][0-9a-f]{32}$", re.IGNORECASE)


def looks_like_auth_key(value: str) -> bool:
    colon = value.find(":")
    if colon == -1:
        return False
    mid = value[:colon]
    payload = value[colon + 1:]
    if not _AUTH_KEY_MID_RE.match(mid):
        return False
    try:
        return len(base64.b64decode(payload + "=" * (-len(payload) % 4))) > 0
    except Exception:
        return False


def create_primary_access_token(auth_key: str, now_ms: Optional[int] = None) -> str:
    colon = auth_key.find(":")
    if colon == -1:
        return auth_key
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    mid = auth_key[:colon]
    key = base64.b64decode(auth_key[colon + 1:])
    iat_raw = f"iat: {(now_ms // 1000) * 60}\n".encode("utf-8")
    iat = base64.b64encode(iat_raw).decode("ascii") + "."
    digest = base64.b64encode(
        _hmac.new(key, iat.encode("utf-8"), hashlib.sha1).digest()
    ).decode("ascii")
    return f"{mid}:{iat}.{digest}"


def resolve_line_access_token(token: str) -> str:
    value = token.strip()
    colon = value.find(":")
    if colon == -1:
        return value
    payload = value[colon + 1:]
    if is_jwt(payload):
        return payload
    if is_primary_access_token(value):
        return value
    if looks_like_auth_key(value):
        return create_primary_access_token(value)
    return value


def should_use_legy_encrypted_access(token: Optional[str]) -> bool:
    if not token:
        return False
    value = token.strip()
    if is_jwt(value):
        return True
    colon = value.find(":")
    if colon == -1:
        return False
    payload = value[colon + 1:]
    return is_jwt(payload) or is_primary_access_token(value) or looks_like_auth_key(value)


def is_legy_talk_path(path: str) -> bool:
    # Only the pathname (without query string) participates in the match.
    return path.split("?", 1)[0] in LEGY_TALK_PATHS


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

class LegyEncryptedTransport:
    """AES-128-CBC encrypted transport for the LINE ``/enc`` endpoint."""

    def __init__(self, endpoint: str = LEGY_ENDPOINT):
        self.endpoint = endpoint
        self._aes_key = os.urandom(16)
        self._x_lcs: Optional[str] = None

    def _get_x_lcs(self) -> str:
        if self._x_lcs is None:
            rsa_key = RSA.import_key(LINE_PUBLIC_KEY)
            cipher = PKCS1_OAEP.new(rsa_key, hashAlgo=SHA1)
            encrypted = cipher.encrypt(self._aes_key)
            self._x_lcs = LEGY_LCS_PREFIX + base64.b64encode(encrypted).decode("ascii")
        return self._x_lcs

    def build_outer_headers(
        self,
        application: str,
        user_agent: str,
        source_headers: Dict[str, str],
        method: str = "POST",
    ) -> Dict[str, str]:
        sh = {k.lower(): v for k, v in source_headers.items()}
        return {
            "x-line-application": application,
            "x-le": LEGY_LE,
            "x-lap": LEGY_LAP,
            "x-lpv": sh.get("x-lpv", "1"),
            "x-lcs": self._get_x_lcs(),
            "user-agent": user_agent,
            "content-type": sh.get("content-type", "application/x-thrift"),
            "x-lal": sh.get("x-lal", "ja_JP"),
            "x-lhm": sh.get("x-lhm", method),
            "accept": sh.get("accept", "*/*"),
            "accept-encoding": "gzip, deflate",
            "connection": "keep-alive",
        }

    def _encrypt(self, plaintext: bytes) -> bytes:
        cipher = AES.new(self._aes_key, AES.MODE_CBC, LEGY_IV)
        return cipher.encrypt(_pkcs7_pad(plaintext, 16))

    def _decrypt(self, ciphertext: bytes) -> bytes:
        padded = _pkcs7_pad(ciphertext, 16)
        cipher = AES.new(self._aes_key, AES.MODE_CBC, LEGY_IV)
        decrypted = cipher.decrypt(padded)
        return _pkcs7_unpad(decrypted[: len(decrypted) - 16])

    def encode_request_body(self, path: str, body: bytes, access_token: Optional[str]) -> bytes:
        """Produce the encrypted request body destined for ``/enc``."""
        inner_headers: Dict[str, str] = {"x-lpqs": path}
        if access_token:
            inner_headers["x-lt"] = resolve_line_access_token(access_token)
        plaintext = encode_legy_headers(inner_headers) + body

        le_int = int(LEGY_LE, 10)
        payload = bytes([le_int]) + plaintext if (le_int & 4) == 4 else plaintext
        encrypted = self._encrypt(payload)
        if (le_int & 2) == 2:
            encrypted = encrypted + legy_hmac(self._aes_key, encrypted)
        return encrypted

    def decode_response_body(self, response_body: bytes) -> Tuple[Dict[str, str], bytes]:
        """Decrypt an ``/enc`` response into (inner headers, thrift body)."""
        if not response_body:
            return {}, b""
        decrypted = self._decrypt(response_body)
        le_int = int(LEGY_LE, 10)
        if (le_int & 4) == 4:
            decrypted = decrypted[1:]
        return decode_legy_headers(decrypted)
