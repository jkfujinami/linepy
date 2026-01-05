"""
LINEPY - LINE SelfBot library for Python

A Python port of linejs (https://github.com/evex-dev/linejs)
"""

import logging

# ライブラリとしてNullHandlerをデフォルトに設定
# 利用者は logging.getLogger("linepy").setLevel(logging.DEBUG) などで制御可能
logging.getLogger("linepy").addHandler(logging.NullHandler())

__version__ = "0.1.0"

from .client import Client
from .base import BaseClient, LineException
from .login import Login, LoginError

__all__ = [
    "Client",
    "BaseClient",
    "LineException",
    "Login",
    "LoginError",
    "__version__",
]
