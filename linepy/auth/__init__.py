# -*- coding: utf-8 -*-
"""Authentication and credential persistence.

:mod:`~linepy.auth.login` performs the QR, email/password and token login
flows; :mod:`~linepy.auth.storage` persists what they return (auth token,
refresh token, MID, E2EE keys, sync tokens) behind a pluggable backend.
"""

from .login import Login, registration_auth_endpoint
from .storage import BaseStorage, FileStorage, MemoryStorage, TokenManager

__all__ = [
    "Login",
    "registration_auth_endpoint",
    "BaseStorage",
    "FileStorage",
    "MemoryStorage",
    "TokenManager",
]
