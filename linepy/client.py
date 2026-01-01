"""
High-level Client for LINEPY

User-friendly API with event handling and convenient methods.
"""

from typing import Optional, Callable, Dict, List, Any
import threading
import time

from .base import BaseClient, LineException
from .config import Device
from .models.talk import Message, Contact, Profile, Chat


class Client:
    """
    High-level LINE Client.

    A lightweight wrapper around BaseClient services.
    """

    def __init__(
        self,
        device: Device = "DESKTOPWIN",
        version: Optional[str] = None,
        system_name: str = "LINEPY",
        storage: Any = None,
    ):
        self.base = BaseClient(
            device=device, version=version, system_name=system_name, storage=storage
        )
        self._polling = False

    def close(self):
        """Close client"""
        self.base.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @property
    def auth_token(self) -> Optional[str]:
        return self.base.auth_token

    @property
    def mid(self) -> Optional[str]:
        return self.base.mid

    @property
    def app_name(self) -> str:
        return self.base.app_name

    @property
    def talk(self):
        return self.base.talk

    @property
    def square(self):
        return self.base.square

    @property
    def channel(self):
        return self.base.channel

    @property
    def timeline(self):
        return self.base.timeline

    def login(
        self,
        auth_token: Optional[str] = None,
        email: Optional[str] = None,
        password: Optional[str] = None,
        qr: bool = False,
        keep_logged_in: bool = True,
    ):
        """
        Login to LINE.

        Args:
            auth_token: Login with auth token
            email: Login with email
            password: Login with password
            qr: Login with QR code
            keep_logged_in: Keep logged in (save token)
        """
        if auth_token:
            self.base.login_with_token(auth_token, save=keep_logged_in)
        elif email and password:
            self.base.login_with_email(email, password, save=keep_logged_in)
        elif qr:
            self.base.login_with_qr(save=keep_logged_in)
        else:
            if not self.base.auto_login():
                self.base.login_with_qr(save=keep_logged_in)

    # ========== Profile ==========

    def get_profile(self) -> Profile:
        """Get user profile"""
        return self.base.talk.get_profile()

    # ========== Contacts ==========

    def get_contact(self, mid: str) -> Contact:
        """Get contact info"""
        return self.base.talk.get_contact(mid)

    def get_contacts(self, mids: List[str]) -> List[Contact]:
        """Get contacts info"""
        return self.base.talk.get_contacts(mids)

    # ========== Chats (Group/Room) ==========

    def get_chat(self, mid: str) -> Chat:
        """Get chat (group/room) info"""
        chats = self.get_chats([mid])
        if chats:
            return chats[0]
        raise LineException(-1, "Chat not found")

    def get_chats(self, mids: List[str]) -> List[Chat]:
        """Get chats info"""
        resp = self.base.talk.get_chats(mids, with_members=True, with_invitees=True)
        return resp.chats if resp and resp.chats else []

    def get_group(self, mid: str) -> Chat:
        """Alias for get_chat"""
        return self.get_chat(mid)

    def get_room(self, mid: str) -> Chat:
        """Alias for get_chat"""
        return self.get_chat(mid)

    # ========== Messaging ==========

    def send_message(self, to: str, text: str) -> Message:
        """
        Send a text message.

        Args:
            to: Target mid (user/group/room)
            text: Message text

        Returns:
            Sent message object
        """
        return self.base.talk.send_message(to, text)
