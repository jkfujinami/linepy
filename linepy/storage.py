"""
Storage Module for LINEPY

Handles persistent storage of authentication tokens and session data.
Based on linejs storage implementation.
"""

import json
import os
from typing import Any, Dict, Optional
from abc import ABC, abstractmethod


class BaseStorage(ABC):
    """Abstract base class for storage backends"""

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Get value by key"""
        pass

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """Set value by key"""
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete value by key"""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all data"""
        pass

    @abstractmethod
    def get_all(self) -> Dict[str, Any]:
        """Get all data"""
        pass


class MemoryStorage(BaseStorage):
    """In-memory storage (data is lost when process exits)"""

    def __init__(self):
        self._data: Dict[str, Any] = {}

    def get(self, key: str) -> Optional[Any]:
        return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()

    def get_all(self) -> Dict[str, Any]:
        return self._data.copy()


class FileStorage(BaseStorage):
    """
    File-based JSON storage.

    Persists data to a JSON file, allowing token reuse across sessions.
    """

    def __init__(self, path: str = ".linepy_storage.json"):
        """
        Initialize file storage.

        Args:
            path: Path to the storage file
        """
        self.path = path
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Ensure storage file exists"""
        if not os.path.exists(self.path):
            with open(self.path, "w") as f:
                json.dump({}, f)

    def _read(self) -> Dict[str, Any]:
        """Read data from file"""
        try:
            with open(self.path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _write(self, data: Dict[str, Any]) -> None:
        """Write data to file"""
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get(self, key: str) -> Optional[Any]:
        data = self._read()
        return data.get(key)

    def set(self, key: str, value: Any) -> None:
        data = self._read()
        data[key] = value
        self._write(data)

    def delete(self, key: str) -> None:
        data = self._read()
        data.pop(key, None)
        self._write(data)

    def clear(self) -> None:
        self._write({})

    def get_all(self) -> Dict[str, Any]:
        return self._read()


class TokenManager:
    """
    Manages authentication tokens with automatic persistence.

    Stores:
    - Access token (JWT)
    - Refresh token
    - Expiration time
    - QR certificate
    - E2EE keys
    """

    def __init__(self, storage: Optional[BaseStorage] = None):
        """
        Initialize token manager.

        Args:
            storage: Storage backend (default: FileStorage)
        """
        self.storage = storage or FileStorage()

    @property
    def auth_token(self) -> Optional[str]:
        """Get stored access token"""
        return self.storage.get("auth_token")

    @auth_token.setter
    def auth_token(self, value: str) -> None:
        """Store access token"""
        self.storage.set("auth_token", value)

    @property
    def refresh_token(self) -> Optional[str]:
        """Get stored refresh token"""
        return self.storage.get("refresh_token")

    @refresh_token.setter
    def refresh_token(self, value: str) -> None:
        """Store refresh token"""
        self.storage.set("refresh_token", value)

    @property
    def expire(self) -> Optional[int]:
        """Get token expiration timestamp"""
        return self.storage.get("expire")

    @expire.setter
    def expire(self, value: int) -> None:
        """Store token expiration timestamp"""
        self.storage.set("expire", value)

    @property
    def qr_cert(self) -> Optional[str]:
        """Get QR login certificate"""
        return self.storage.get("qr_cert")

    @qr_cert.setter
    def qr_cert(self, value: str) -> None:
        """Store QR login certificate"""
        self.storage.set("qr_cert", value)

    @property
    def mid(self) -> Optional[str]:
        """Get user MID"""
        return self.storage.get("mid")

    @mid.setter
    def mid(self, value: str) -> None:
        """Store user MID"""
        self.storage.set("mid", value)

    def is_token_valid(self) -> bool:
        """
        Check if the stored token is still valid.

        Returns:
            True if token exists and hasn't expired
        """
        import time

        token = self.auth_token
        expire = self.expire

        if not token:
            return False

        if expire and time.time() > expire:
            return False

        return True

    def save_login_result(self, response: Dict) -> None:
        """
        Save login result to storage.

        Args:
            response: qrCodeLoginV2 or loginV2 response
        """
        import time

        # Extract token info (field 3)
        token_info = response.get(3, {})

        if token_info:
            # Access token (field 1)
            if token_info.get(1):
                self.auth_token = token_info[1]

            # Refresh token (field 2)
            if token_info.get(2):
                self.refresh_token = token_info[2]

            # Expiration (field 3 = expiresIn seconds, field 6 = iat timestamp)
            expires_in = token_info.get(3, 0)
            iat = token_info.get(6, int(time.time()))
            if expires_in:
                self.expire = iat + expires_in

        # Extract MID (field 4)
        if response.get(4):
            self.mid = response[4]

        # Extract QR certificate (field 1)
        if response.get(1):
            self.qr_cert = response[1]

    def clear(self) -> None:
        """Clear all stored tokens"""
        self.storage.clear()


# Convenient default storage path
DEFAULT_STORAGE_PATH = ".linepy_storage.json"
