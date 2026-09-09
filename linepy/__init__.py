"""
LINEPY - LINE SelfBot library for Python

A Python port of linejs (https://github.com/evex-dev/linejs)
"""

import logging

from .base import BaseClient
from .client import Client
from .exceptions import CompactMessageProtocolError, LineException, LoginError
from .login import Login

# ライブラリとしてNullHandlerをデフォルトに設定
# 利用者は logging.getLogger("linepy").setLevel(logging.DEBUG) などで制御可能
logging.getLogger("linepy").addHandler(logging.NullHandler())

__version__ = "0.1.0"

__all__ = [
    "Client",
    "BaseClient",
    "Login",
    "LineException",
    "LoginError",
    "CompactMessageProtocolError",
    "__version__",
]
