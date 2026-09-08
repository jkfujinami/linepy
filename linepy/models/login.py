# -*- coding: utf-8 -*-
"""Pydantic models for LINE Login API responses.

These models provide type-safe, dot-accessible structures for the data returned
by Login methods (QR code, email/password, etc.).
"""

from __future__ import annotations

from typing import Optional, Dict, Any, Union

from pydantic import BaseModel, Field


class RSAKeyInfo(BaseModel):
    """RSA key info for credential encryption (getRSAKeyInfo thrift struct)."""

    keynm: str = Field(alias="1")
    nvalue: str = Field(alias="2")
    evalue: str = Field(alias="3")
    sessionKey: str = Field(alias="4", default="")

    class Config:
        populate_by_name = True


class TokenInfo(BaseModel):
    """Token info from the raw loginV2 response (field 9 of the loginV2 result).

    Field layout confirmed from 本家's ``requestEmailLoginV2``:
    ``tokenInfo[1]``=accessToken, ``[2]``=refreshToken, ``[3]``=expiresIn
    (seconds, a *duration* not a timestamp), ``[6]``=iat (issued-at unix time).
    ``expire`` must be computed as ``iat + expires_in``.
    """

    auth_token: Optional[str] = Field(alias="1", default=None)
    refresh_token: Optional[str] = Field(alias="2", default=None)
    expires_in: Optional[int] = Field(alias="3", default=None)
    iat: Optional[int] = Field(alias="6", default=None)

    class Config:
        populate_by_name = True


class LoginResponse(BaseModel):
    """Response from email/password login (loginZ/loginV2)."""

    auth_token: Optional[str] = Field(alias="1", default=None)
    certificate: Optional[str] = Field(alias="2", default=None)
    verifier: Optional[str] = Field(alias="3", default=None)
    pincode: Optional[str] = Field(alias="4", default=None)
    # For loginV2 (v3 devices)
    token_info: Optional[TokenInfo] = Field(alias="9", default=None)

    class Config:
        populate_by_name = True


class QRSessionResponse(BaseModel):
    """Response from createSession (QR login)."""

    sqr: str = Field(alias="1")

    class Config:
        populate_by_name = True


class QRCodeResponse(BaseModel):
    """Response from createQrCode."""

    url: str = Field(alias="1")
    call_url: Optional[Union[str, int]] = Field(alias="2", default=None)

    class Config:
        populate_by_name = True


class PinCodeResponse(BaseModel):
    """Response from createPinCode."""

    pincode: str = Field(alias="1")

    class Config:
        populate_by_name = True


class QRCodeLoginResponse(BaseModel):
    """Response from qrCodeLogin (legacy v1 QR).

    Field layout from 本家's ``requestSQR``:
    ``{ 1: pem, 2: authToken, 4: e2eeInfo, 5: mid }`` (field 3 is unused/gap).
    """

    certificate: Optional[str] = Field(alias="1", default=None)
    auth_token: Optional[str] = Field(alias="2", default=None)
    e2ee_info: Optional[Dict[str, Any]] = Field(alias="4", default=None)
    mid: Optional[str] = Field(alias="5", default=None)

    class Config:
        populate_by_name = True


class QRCodeLoginV2TokenInfo(BaseModel):
    """tokenV3IssueResult for qrCodeLoginV2 / qrCodeLoginV2ForSecure.

    Same field semantics as :class:`TokenInfo`: ``[3]``=expiresIn (duration),
    ``[6]``=iat (issued-at). ``expire`` must be computed as ``iat + expires_in``.
    """

    auth_token: str = Field(alias="1")
    refresh_token: Optional[str] = Field(alias="2", default=None)
    expires_in: Optional[int] = Field(alias="3", default=None)
    iat: Optional[int] = Field(alias="6", default=None)

    class Config:
        populate_by_name = True


class QRCodeLoginV2Response(BaseModel):
    """Response from qrCodeLoginV2 / qrCodeLoginV2ForSecure.

    Field layout per 本家's comment (schema ``oc4.q``, reused by both V2 and
    V2ForSecure): ``1``=certificate, ``2``=accessTokenV2 (legacy str, unused),
    ``3``=tokenV3IssueResult, ``4``=mid, ``5``=lastBindTimestamp,
    ``6``=metaData (map<string,string>). ``e2eeInfo`` historically arrived at
    field ``10`` (non-ForSecure) or inside ``metaData["e2eeInfo"]``
    (ForSecure) — 本家 tries both, so both are exposed here.
    """

    certificate: Optional[str] = Field(alias="1", default=None)
    legacy_access_token: Optional[str] = Field(alias="2", default=None)
    token_info: Optional[QRCodeLoginV2TokenInfo] = Field(alias="3", default=None)
    mid: Optional[str] = Field(alias="4", default=None)
    last_bound_time: Optional[int] = Field(alias="5", default=None)
    metadata: Optional[Dict[str, Any]] = Field(alias="6", default=None)
    e2ee_info: Optional[Any] = Field(alias="10", default=None)

    class Config:
        populate_by_name = True


class E2EEKeyInfo(BaseModel):
    """E2EE key info from verification (thrift field ids)."""

    version: Optional[int] = Field(alias="1", default=None)
    key_id: Optional[int] = Field(alias="2", default=None)
    public_key: Optional[str] = Field(alias="3", default=None)
    encrypted_key_chain: Optional[str] = Field(alias="4", default=None)

    class Config:
        populate_by_name = True


class VerificationResponse(BaseModel):
    """Response from the /LF1 and /Q PIN-verification endpoints.

    Unlike the other models in this module, /LF1 and /Q return real JSON
    (``res.json()`` in 本家), not a Thrift-decoded struct — the key really is
    the literal string ``"result"``, not a Thrift field id.
    """

    result: Dict[str, Any] = Field(alias="result", default_factory=dict)

    class Config:
        populate_by_name = True
