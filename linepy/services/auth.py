from typing import Optional
from .base import ServiceBase
from ..models.sync_structs import (
    RefreshAccessTokenRequest,
    RefreshAccessTokenResponse,
    ReportRefreshedAccessTokenRequest
)

class AuthService(ServiceBase):
    """Auth Service for token management."""

    # 標準のエンドポイント (必要に応じて設定)
    ENDPOINT = "/EXT/auth/tokenrefresh/v1"
    PROTOCOL = 4  # TCompactProtocol (推定)

    def refresh(
        self,
        refresh_token: str
    ) -> RefreshAccessTokenResponse:
        """
        Refresh access token using refresh token.

        Args:
            refresh_token: The refresh token string

        Returns:
            RefreshAccessTokenResponse containing new access token
        """
        METHOD_NAME = "refresh"

        # Build request struct: [[12, 1, [[11, 1, refresh_token]]]]
        # Struct ID 12, Field ID 1: RefreshAccessTokenRequest
        # RefreshAccessTokenRequest Field ID 1: refresh_token (String)
        params = [
            [12, 1, [
                [11, 1, refresh_token]
            ]]
        ]

        return self._call(
            METHOD_NAME,
            params,
            response_model=RefreshAccessTokenResponse,
            endpoint="/EXT/auth/tokenrefresh/v1"
        )

    def reportRefreshedAccessToken(
        self,
        access_token: str
    ) -> None:
        """
        Report that access token was refreshed (if required).
        """
        METHOD_NAME = "reportRefreshedAccessToken"

        # ReportRefreshedAccessTokenRequest
        # Field 1: access_token
        params = [
            [12, 1, [
                [11, 1, access_token]
            ]]
        ]

        return self._call(
            METHOD_NAME,
            params,
            endpoint="/EXT/auth/tokenrefresh/v1"
        )
