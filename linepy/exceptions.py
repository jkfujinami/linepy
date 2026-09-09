# -*- coding: utf-8 -*-
"""Exception types raised by LINEPY.

Collected in one dependency-free module so that every layer -- transport,
protocol, services, login -- can raise them without importing (and circling
back into) ``linepy.base``.
"""

from typing import Dict, Optional

__all__ = [
    "LineException",
    "LoginError",
    "CompactMessageProtocolError",
]


class LineException(Exception):
    """LINE API Exception.

    Raised for both Thrift-level errors (``code``/``message`` from the
    server's error struct) and HTTP failures, with any extra server data in
    ``metadata``.
    """

    def __init__(self, code: int, message: str, metadata: Optional[Dict] = None):
        self.code = code
        self.message = message
        self.metadata = metadata or {}

        # Build detailed message
        msg = f"[{code}] {message}"
        if self.metadata:
            msg += f"\nMetadata: {self.metadata}"
        super().__init__(msg)


class LoginError(Exception):
    """Login specific error"""


class CompactMessageProtocolError(Exception):
    """Malformed or unsupported payload on the compact (/CA5, /ECA5) protocol."""

    def __init__(self, message: str, code: Optional[int] = None):
        super().__init__(message)
        self.code = code
