# -*- coding: utf-8 -*-
"""Models for LINE Login API responses.

These are plain stdlib ``@dataclass``es built on ``linepy._model_base``
(see that module for why: pydantic-core has no iOS wheels and no
pure-Python fallback). They provide the same type-safe, dot-accessible,
alias-keyed structures as before -- just without the Rust dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

from .._model_base import ModelBase, model_field


@dataclass(kw_only=True)
class RSAKeyInfo(ModelBase):
    """RSA key info for credential encryption (getRSAKeyInfo thrift struct)."""

    keynm: str = model_field(alias="1", default="")
    nvalue: str = model_field(alias="2", default="")
    evalue: str = model_field(alias="3", default="")
    sessionKey: str = model_field(alias="4", default="")


@dataclass(kw_only=True)
class TokenInfo(ModelBase):
    """Token info from the raw loginV2 response (field 9 of the loginV2 result).

    Field layout confirmed from 本家's ``requestEmailLoginV2``:
    ``tokenInfo[1]``=accessToken, ``[2]``=refreshToken, ``[3]``=expiresIn
    (seconds, a *duration* not a timestamp), ``[6]``=iat (issued-at unix time).
    ``expire`` must be computed as ``iat + expires_in``.
    """

    auth_token: Optional[str] = model_field(alias="1", default=None)
    refresh_token: Optional[str] = model_field(alias="2", default=None)
    expires_in: Optional[int] = model_field(alias="3", default=None)
    iat: Optional[int] = model_field(alias="6", default=None)


@dataclass(kw_only=True)
class LoginResponse(ModelBase):
    """Response from email/password login (loginZ/loginV2)."""

    auth_token: Optional[str] = model_field(alias="1", default=None)
    certificate: Optional[str] = model_field(alias="2", default=None)
    verifier: Optional[str] = model_field(alias="3", default=None)
    pincode: Optional[str] = model_field(alias="4", default=None)
    # For loginV2 (v3 devices)
    token_info: Optional["TokenInfo"] = model_field(alias="9", default=None)


@dataclass(kw_only=True)
class QRSessionResponse(ModelBase):
    """Response from createSession (QR login)."""

    sqr: str = model_field(alias="1", default="")


@dataclass(kw_only=True)
class QRCodeResponse(ModelBase):
    """Response from createQrCode."""

    url: str = model_field(alias="1", default="")
    call_url: Optional[Union[str, int]] = model_field(alias="2", default=None)


@dataclass(kw_only=True)
class PinCodeResponse(ModelBase):
    """Response from createPinCode."""

    pincode: str = model_field(alias="1", default="")


@dataclass(kw_only=True)
class QRCodeLoginResponse(ModelBase):
    """Response from qrCodeLogin (legacy v1 QR).

    Field layout from 本家's ``requestSQR``:
    ``{ 1: pem, 2: authToken, 4: e2eeInfo, 5: mid }`` (field 3 is unused/gap).
    """

    certificate: Optional[str] = model_field(alias="1", default=None)
    auth_token: Optional[str] = model_field(alias="2", default=None)
    e2ee_info: Optional[Dict[str, Any]] = model_field(alias="4", default=None)
    mid: Optional[str] = model_field(alias="5", default=None)


@dataclass(kw_only=True)
class QRCodeLoginV2TokenInfo(ModelBase):
    """tokenV3IssueResult for qrCodeLoginV2 / qrCodeLoginV2ForSecure.

    Same field semantics as :class:`TokenInfo`: ``[3]``=expiresIn (duration),
    ``[6]``=iat (issued-at). ``expire`` must be computed as ``iat + expires_in``.
    """

    auth_token: str = model_field(alias="1", default="")
    refresh_token: Optional[str] = model_field(alias="2", default=None)
    expires_in: Optional[int] = model_field(alias="3", default=None)
    iat: Optional[int] = model_field(alias="6", default=None)


@dataclass(kw_only=True)
class QRCodeLoginV2Response(ModelBase):
    """Response from qrCodeLoginV2 / qrCodeLoginV2ForSecure.

    Field layout per 本家's comment (schema ``oc4.q``, reused by both V2 and
    V2ForSecure): ``1``=certificate, ``2``=accessTokenV2 (legacy str, unused),
    ``3``=tokenV3IssueResult, ``4``=mid, ``5``=lastBindTimestamp,
    ``6``=metaData (map<string,string>). ``e2eeInfo`` historically arrived at
    field ``10`` (non-ForSecure) or inside ``metaData["e2eeInfo"]``
    (ForSecure) — 本家 tries both, so both are exposed here.
    """

    certificate: Optional[str] = model_field(alias="1", default=None)
    legacy_access_token: Optional[str] = model_field(alias="2", default=None)
    token_info: Optional["QRCodeLoginV2TokenInfo"] = model_field(alias="3", default=None)
    mid: Optional[str] = model_field(alias="4", default=None)
    last_bound_time: Optional[int] = model_field(alias="5", default=None)
    metadata: Optional[Dict[str, Any]] = model_field(alias="6", default=None)
    e2ee_info: Optional[Any] = model_field(alias="10", default=None)


@dataclass(kw_only=True)
class E2EEKeyInfo(ModelBase):
    """E2EE key info from verification (thrift field ids)."""

    version: Optional[int] = model_field(alias="1", default=None)
    key_id: Optional[int] = model_field(alias="2", default=None)
    public_key: Optional[str] = model_field(alias="3", default=None)
    encrypted_key_chain: Optional[str] = model_field(alias="4", default=None)


@dataclass(kw_only=True)
class VerificationResponse(ModelBase):
    """Response from the /LF1 and /Q PIN-verification endpoints.

    Unlike the other models in this module, /LF1 and /Q return real JSON
    (``res.json()`` in 本家), not a Thrift-decoded struct — the key really is
    the literal string ``"result"``, not a Thrift field id.
    """

    result: Dict[str, Any] = model_field(alias="result", default_factory=dict)
