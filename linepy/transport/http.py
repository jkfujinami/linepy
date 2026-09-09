"""
HTTP Request Client for LINEPY

Handles all HTTP communication with LINE servers.
Uses httpx for HTTP/2 support.
"""

from typing import Any, Callable, Dict, Optional

import httpx

from ..protocol.legy import (
    LegyEncryptedTransport,
    is_legy_talk_path,
    should_use_legy_encrypted_access,
)
from ..protocol.thrift import CompactReader, ThriftReader


class RequestClient:
    """
    HTTP client for LINE API requests.

    Handles:
    - Request signing/encryption
    - Thrift serialization
    - HTTP/2 communication
    """

    # LINE Endpoints (from linejs)
    HOST = "legy.line-apps.com"

    # Endpoints
    TALK_ENDPOINT = "/S4"  # Compact protocol
    AUTH_ENDPOINT = "/RS4"
    SQUARE_ENDPOINT = "/SQ1"
    CHANNEL_ENDPOINT = "/CH4"
    LIFF_ENDPOINT = "/LIFF1"
    SECONDARY_QR_ENDPOINT = "/acct/lgn/sq/v1"
    SECONDARY_QR_LP_ENDPOINT = "/acct/lp/lgn/sq/v1"

    def __init__(
        self,
        device_name: str,
        system_name: str = "LINEPY",
        timeout: float = 30.0,
        long_timeout: float = 180.0,
    ):
        self.device_name = device_name
        self.system_name = system_name
        self.timeout = timeout
        self.long_timeout = long_timeout

        self.auth_token: Optional[str] = None
        self._http = httpx.Client(http2=True, timeout=timeout)

        # Request sequence numbers
        self._reqseq: Dict[str, int] = {}

        # LEGY encrypted transport (Phase 1 Step 2)
        #   None  -> auto (path + token based)
        #   True  -> always encrypt
        #   False -> never encrypt
        self.legy_encrypted: Optional[bool] = None
        self._legy_transport: Optional[LegyEncryptedTransport] = None
        self.legy_endpoint: str = "https://gf.line.naver.jp/enc"

        # Hooks wired by BaseClient for token lifecycle (Phase 1 Step 2.3)
        #   on_next_access(token): called when server returns x-line-next-access
        #   refresh_hook() -> bool: refresh access token, return True on success
        self.on_next_access: Optional[Callable[[str], None]] = None
        self.refresh_hook: Optional[Callable[[], bool]] = None

    def close(self):
        """Close HTTP client"""
        self._http.close()

    # ---- Plain HTTP -------------------------------------------------------
    # OBS, LIFF, VOOM and QR long-polling talk to ordinary HTTP endpoints
    # rather than Thrift ones. They go through these rather than reaching into
    # ``_http``, so the underlying client stays this module's business.

    @property
    def http(self) -> httpx.Client:
        """The underlying httpx client, for calls these helpers do not cover."""
        return self._http

    def get(self, url: str, **kwargs) -> httpx.Response:
        """Plain HTTP GET (no Thrift framing, no LEGY envelope)."""
        return self._http.get(url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        """Plain HTTP POST (no Thrift framing, no LEGY envelope)."""
        return self._http.post(url, **kwargs)

    @property
    def user_agent(self) -> str:
        """Get User-Agent header"""
        return self._get_user_agent()

    def _get_user_agent(self) -> str:
        """Build User-Agent header"""
        tab = "\t"
        if tab in self.device_name:
            version = self.device_name.split(tab)[1]
        else:
            version = "1.0.0"
        return f"Line/{version}"

    def _build_headers(
        self,
        host: Optional[str] = None,
        access_token: Optional[str] = None,
        method: str = "POST",
        extra: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Build request headers (matching linejs format)"""
        headers = {
            "Host": host or self.HOST,
            "accept": "application/x-thrift",
            "user-agent": self._get_user_agent(),
            "x-line-application": self.device_name,
            "content-type": "application/x-thrift",
            "x-lal": "ja_JP",
            "x-lpv": "1",
            "x-lhm": method,
            "accept-encoding": "gzip",
        }

        token = access_token or self.auth_token
        if token:
            headers["x-line-access"] = token

        if extra:
            headers.update(extra)

        return headers

    def get_reqseq(self, name: str = "talk") -> int:
        """Get and increment request sequence number"""
        seq = self._reqseq.get(name, 0)
        self._reqseq[name] = seq + 1
        return seq

    def request(
        self,
        path: str,
        data: bytes,
        host: Optional[str] = None,
        access_token: Optional[str] = None,
        timeout: Optional[float] = None,
        protocol: int = 4,  # 3=binary, 4=compact
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """
        Send a Thrift request and parse response.

        Args:
            path: API endpoint path
            data: Thrift-encoded request data
            host: Override host
            access_token: Override auth token
            timeout: Request timeout
            protocol: Thrift protocol (3=binary, 4=compact)
            extra_headers: Additional headers

        Returns:
            Parsed response data
        """
        target_host = host or self.HOST
        url = f"https://{target_host}{path}"
        token = access_token or self.auth_token

        did_refresh = False
        while True:
            headers = self._build_headers(
                host=target_host,
                access_token=token,
                method="POST",
                extra=extra_headers,
            )

            if self._should_use_legy(path, token):
                raw = self._legy_request(
                    path=path,
                    data=data,
                    token=token,
                    base_headers=headers,
                    timeout=timeout or self.timeout,
                )
            else:
                response = self._http.post(
                    url,
                    content=data,
                    headers=headers,
                    timeout=timeout or self.timeout,
                )
                self._handle_next_access(response.headers)
                response.raise_for_status()
                raw = response.content

            # Auto token refresh + single retry (Phase 1 Step 2.3)
            if (
                not did_refresh
                and self.refresh_hook is not None
                and b"MUST_REFRESH_V3_TOKEN" in raw
            ):
                did_refresh = True
                try:
                    if self.refresh_hook():
                        token = self.auth_token
                        # A refreshed session key must be renegotiated.
                        self._legy_transport = None
                        continue
                except Exception:
                    pass

            reader = CompactReader(raw) if protocol == 4 else ThriftReader(raw)
            return reader.parse_response()

    # ---- LEGY helpers -----------------------------------------------------

    def _should_use_legy(self, path: str, token: Optional[str]) -> bool:
        if self.legy_encrypted is False:
            return False
        if not token:
            return False
        if self.legy_encrypted is True:
            return True
        return is_legy_talk_path(path) and should_use_legy_encrypted_access(token)

    def _get_legy_transport(self) -> LegyEncryptedTransport:
        if self._legy_transport is None:
            self._legy_transport = LegyEncryptedTransport(self.legy_endpoint)
        return self._legy_transport

    def _handle_next_access(self, response_headers) -> None:
        try:
            next_token = response_headers.get("x-line-next-access")
        except Exception:
            next_token = None
        if next_token and self.on_next_access is not None:
            try:
                self.on_next_access(next_token)
            except Exception:
                pass

    def _legy_request(
        self,
        path: str,
        data: bytes,
        token: Optional[str],
        base_headers: Dict[str, str],
        timeout: float,
    ) -> bytes:
        transport = self._get_legy_transport()
        body = transport.encode_request_body(path, data, token)
        outer = transport.build_outer_headers(
            application=self.device_name,
            user_agent=self._get_user_agent(),
            source_headers=base_headers,
            method="POST",
        )
        response = self._http.post(
            transport.endpoint,
            content=body,
            headers=outer,
            timeout=timeout,
        )
        self._handle_next_access(response.headers)
        response.raise_for_status()
        _headers, thrift_body = transport.decode_response_body(response.content)
        return thrift_body

    def compact_request(
        self,
        path: str,
        seq_id: int,
        body: bytes,
        host: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> bytes:
        """POST a compact message frame (/CA5 or /ECA5).

        Mirrors 本家 ``#requestCompactMessage``: a direct POST (not LEGY) with
        the standard headers plus ``x-lai: <seqId>``. Returns raw response bytes.
        """
        target_host = host or self.HOST
        url = f"https://{target_host}{path}"
        headers = self._build_headers(host=target_host, method="POST")
        headers["x-lai"] = str(seq_id)
        response = self._http.post(
            url, content=body, headers=headers, timeout=timeout or self.timeout
        )
        self._handle_next_access(response.headers)
        response.raise_for_status()
        return response.content

    def request_raw(
        self,
        path: str,
        data: bytes = b"",
        method: str = "POST",
        host: Optional[str] = None,
        access_token: Optional[str] = None,
        timeout: Optional[float] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> bytes:
        """
        Send a raw HTTP request.

        Returns:
            Raw response bytes
        """
        url = f"https://{host or self.HOST}{path}"
        headers = self._build_headers(access_token=access_token, extra=extra_headers)

        if method == "GET":
            headers["x-lhm"] = "GET"
            response = self._http.get(
                url, headers=headers, timeout=timeout or self.timeout
            )
        else:
            response = self._http.post(
                url,
                content=data,
                headers=headers,
                timeout=timeout or self.timeout,
            )

        response.raise_for_status()
        return response.content

    def request_json(
        self,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        method: str = "POST",
        host: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a JSON request.

        Returns:
            JSON response
        """
        url = f"https://{host or self.HOST}{path}"
        headers = self._build_headers(
            access_token=access_token,
            extra={"content-type": "application/json"},
        )

        if method == "GET":
            headers["x-lhm"] = "GET"
            response = self._http.get(url, headers=headers)
        else:
            response = self._http.post(url, json=data or {}, headers=headers)

        response.raise_for_status()
        return response.json()
