"""
Storage Module for LINEPY

Handles persistent storage of authentication tokens and session data.
Based on linejs storage implementation.
"""

import json
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


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
    Thread-safe via internal lock.
    """

    def __init__(self, path: str = ".linepy_storage.json"):
        """
        Initialize file storage.

        Args:
            path: Path to the storage file
        """
        import threading
        self.path = path
        self._lock = threading.Lock()  # Thread safety
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
                content = f.read()
                if not content.strip():
                    return {}
                return json.loads(content)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as e:
            # Log error but don't silently return empty - this could cause data loss
            import logging
            logging.getLogger("linepy.storage").error(
                "JSON decode error in %s: %s. NOT overwriting file.", self.path, e
            )
            raise  # Re-raise to prevent set() from overwriting with partial data

    def _write(self, data: Dict[str, Any]) -> None:
        """Write data to file"""
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            data = self._read()
            return data.get(key)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            data = self._read()
            data[key] = value
            self._write(data)

    def delete(self, key: str) -> None:
        with self._lock:
            data = self._read()
            data.pop(key, None)
            self._write(data)

    def clear(self) -> None:
        with self._lock:
            self._write({})

    def get_all(self) -> Dict[str, Any]:
        with self._lock:
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
            response: A qrCodeLoginV2/qrCodeLoginV2ForSecure response, as
                either a raw Thrift field-id dict (int keys, e.g. from a
                `parse=false` RPC) or a ModelBase dataclass's
                ``model_dump(by_alias=True)`` (string keys, e.g. "3"). Both
                are accepted since both shapes occur across the login flows.
        """
        import time

        def field(d, fid: int):
            """Read a field id from either an int-keyed or str-keyed dict."""
            if not isinstance(d, dict):
                return None
            return d.get(fid) if fid in d else d.get(str(fid))

        # Extract token info (field 3: tokenV3IssueResult / TokenInfo)
        token_info = field(response, 3) or {}

        if token_info:
            # Access token (field 1)
            access_token = field(token_info, 1)
            if access_token:
                self.auth_token = access_token

            # Refresh token (field 2)
            refresh_token = field(token_info, 2)
            if refresh_token:
                self.refresh_token = refresh_token

            # Expiration (field 3 = expiresIn seconds, field 6 = iat timestamp)
            expires_in = field(token_info, 3) or 0
            iat = field(token_info, 6)
            if iat is None:
                iat = int(time.time())
            if expires_in:
                self.expire = iat + expires_in

        # Extract MID (field 4)
        mid = field(response, 4)
        if mid:
            self.mid = mid

        # Extract QR certificate (field 1)
        if response.get(1):
            self.qr_cert = response[1]

    def clear(self) -> None:
        """Clear all stored tokens"""
        self.storage.clear()

    def get_next_reqseq(self, key: str = "reqseq") -> int:
        """
        Get and increment the next request sequence number.

        Args:
            key: Key identifier for the sequence (default: "reqseq")

        Returns:
            The new sequence number (int)
        """
        key_name = f"{key}_seq"
        current = self.storage.get(key_name)
        if current is None:
            current = 0
        else:
            current = int(current)

        next_val = current + 1
        self.storage.set(key_name, next_val)
        return next_val

    def get_square_sync_token(self, chat_mid: str) -> Optional[str]:
        """Get stored sync token for a square chat"""
        tokens = self.storage.get("square_sync_tokens") or {}
        return tokens.get(chat_mid)

    def set_square_sync_token(self, chat_mid: str, token: str) -> None:
        """Store sync token for a square chat"""
        tokens = self.storage.get("square_sync_tokens") or {}
        tokens[chat_mid] = token
        self.storage.set("square_sync_tokens", tokens)

    def get_square_continuation_token(self, chat_mid: str) -> Optional[str]:
        """Get stored continuation token for a square chat"""
        tokens = self.storage.get("square_cont_tokens") or {}
        return tokens.get(chat_mid)

    def set_square_continuation_token(self, chat_mid: str, token: str) -> None:
        """Store continuation token for a square chat"""
        tokens = self.storage.get("square_cont_tokens") or {}
        tokens[chat_mid] = token
        self.storage.set("square_cont_tokens", tokens)

    # ========== E2EE Key Persistence (Phase 1 Step 1.2) ==========

    def get_e2ee_key(self, key_id: int) -> Optional[Dict[str, Any]]:
        """Get own E2EE keypair by key id (private/public/version)."""
        keys = self.storage.get("e2ee_keys") or {}
        return keys.get(f"e2ee_key_{key_id}")

    def save_e2ee_key(self, key_id: int, key_data: Dict[str, Any]) -> None:
        """Persist own E2EE keypair under its key id."""
        keys = self.storage.get("e2ee_keys") or {}
        keys[f"e2ee_key_{key_id}"] = key_data
        self.storage.set("e2ee_keys", keys)

    def get_all_e2ee_keys(self) -> Dict[str, Any]:
        """Return the full mapping of persisted own E2EE keypairs."""
        return self.storage.get("e2ee_keys") or {}

    def get_user_public_key(self, mid: str) -> Optional[Dict[str, Any]]:
        """Get a cached public key for another user/entity."""
        keys = self.storage.get("e2ee_public_keys") or {}
        return keys.get(f"e2ee_pub_{mid}")

    def save_user_public_key(self, mid: str, pub_key: Dict[str, Any]) -> None:
        """Cache another user's/entity's public key."""
        keys = self.storage.get("e2ee_public_keys") or {}
        keys[f"e2ee_pub_{mid}"] = pub_key
        self.storage.set("e2ee_public_keys", keys)

    def get_group_key(self, chat_mid: str) -> Optional[Dict[str, Any]]:
        """Get the cached shared group key for a group/room chat."""
        keys = self.storage.get("e2ee_group_keys") or {}
        return keys.get(f"e2ee_group_{chat_mid}")

    def save_group_key(self, chat_mid: str, group_key: Dict[str, Any]) -> None:
        """Cache the shared group key for a group/room chat."""
        keys = self.storage.get("e2ee_group_keys") or {}
        keys[f"e2ee_group_{chat_mid}"] = group_key
        self.storage.set("e2ee_group_keys", keys)

    def clear_square_tokens(self, chat_mid: str) -> None:
        """Clear tokens for a square chat"""
        sync_tokens = self.storage.get("square_sync_tokens") or {}
        cont_tokens = self.storage.get("square_cont_tokens") or {}

        if chat_mid in sync_tokens:
            del sync_tokens[chat_mid]
            self.storage.set("square_sync_tokens", sync_tokens)

        if chat_mid in cont_tokens:
            del cont_tokens[chat_mid]
            self.storage.set("square_cont_tokens", cont_tokens)
# Convenient default storage path
DEFAULT_STORAGE_PATH = ".linepy_storage.json"
