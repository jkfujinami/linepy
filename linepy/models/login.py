# -*- coding: utf-8 -*-
"""Pydantic models for LINE Login API responses.

These models provide type-safe, dot-accessible structures for the data returned
by Login methods (QR code, email/password, etc.).
"""

from __future__ import annotations

from typing import Optional, Dict, Any, Union

from pydantic import BaseModel, Field


class RSAKeyInfo(BaseModel):
    """RSA key info for credential encryption."""

    keynm: str
    nvalue: str
    evalue: str
    sessionKey: str = Field(alias="session_key", default="")

    class Config:
        populate_by_name = True


class TokenInfo(BaseModel):
    """Token info from login response (v3 format)."""

    auth_token: Optional[str] = Field(alias="1", default=None)
    refresh_token: Optional[str] = Field(alias="2", default=None)
    token_issue_time: Optional[int] = Field(alias="3", default=None)
    token_expire_time: Optional[int] = Field(alias="4", default=None)

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
    """Response from qrCodeLogin (legacy)."""

    certificate: Optional[str] = Field(alias="1", default=None)
    auth_token: Optional[str] = Field(alias="2", default=None)
    mid: Optional[str] = Field(alias="3", default=None)

    class Config:
        populate_by_name = True


class QRCodeLoginV2TokenInfo(BaseModel):
    """Token info for qrCodeLoginV2."""

    auth_token: str = Field(alias="1")
    refresh_token: Optional[str] = Field(alias="2", default=None)
    token_issue_time: Optional[int] = Field(alias="3", default=None)
    token_expire_time: Optional[int] = Field(alias="4", default=None)
    app_type: Optional[str] = Field(alias="5", default=None)

    class Config:
        populate_by_name = True


class QRCodeLoginV2Response(BaseModel):
    """Response from qrCodeLoginV2."""

    certificate: Optional[str] = Field(alias="1", default=None)
    mid: Optional[str] = Field(alias="2", default=None)
    token_info: Optional[QRCodeLoginV2TokenInfo] = Field(alias="3", default=None)
    last_bound_time: Optional[int] = Field(alias="4", default=None)
    metadata: Optional[Dict[str, Any]] = Field(alias="5", default=None)

    class Config:
        populate_by_name = True


class E2EEKeyInfo(BaseModel):
    """E2EE key info from verification."""

    version: Optional[int] = None
    key_id: Optional[int] = None
    public_key: Optional[str] = None
    encrypted_key_chain: Optional[str] = None


class VerificationResponse(BaseModel):
    """Response from PIN verification endpoints."""

    result: Dict[str, Any] = Field(default_factory=dict)
