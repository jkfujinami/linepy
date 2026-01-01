"""
HTTP Request Client for LINEPY

Handles all HTTP communication with LINE servers.
Uses httpx for HTTP/2 support.
"""

from typing import Optional, Dict, Any
import httpx

from .thrift import ThriftReader, ThriftWriter, CompactReader


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

    def close(self):
        """Close HTTP client"""
        self._http.close()

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
        headers = self._build_headers(
            host=target_host,
            access_token=access_token,
            method="POST",
            extra=extra_headers,
        )

        response = self._http.post(
            url,
            content=data,
            headers=headers,
            timeout=timeout or self.timeout,
        )
        response.raise_for_status()

        # Parse response based on protocol
        if protocol == 4:
            reader = CompactReader(response.content)
        else:
            reader = ThriftReader(response.content)

        return reader.parse_response()

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
