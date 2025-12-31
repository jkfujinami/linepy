"""
LINEPY - LINE SelfBot library for Python

A Python port of linejs (https://github.com/evex-dev/linejs)
"""

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
