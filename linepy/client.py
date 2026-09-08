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

    @property
    def liff(self):
        return self.base.liff

    @property
    def voom(self):
        return self.base.voom

    @property
    def obs(self):
        return self.base.obs

    @property
    def e2ee(self):
        return self.base.e2ee

    def on(self, event: str, callback: Optional[Callable] = None):
        """Register an event handler (delegates to the base client)."""
        return self.base.on(event, callback)

    def emit(self, event: str, *args, **kwargs):
        return self.base.emit(event, *args, **kwargs)

    def listen(self, talk: bool = True, square: bool = True):
        """Start the PUSH listen loop (see BaseClient.listen)."""
        return self.base.listen(talk=talk, square=square)

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
            return self.base.login_with_token(auth_token, save=keep_logged_in)
        elif email and password:
            return self.base.login_with_email(email, password)
        elif qr:
            return self.base.login_with_qr(save=keep_logged_in)
        else:
            if not self.base.auto_login():
                return self.base.login_with_qr(save=keep_logged_in)

    def login_with_email(
        self,
        email: str,
        password: str,
        pincode: str = "114514",
        e2ee: bool = True,
    ) -> str:
        """Login with email/password (delegates to the base client)."""
        return self.base.login_with_email(email, password, pincode=pincode, e2ee=e2ee)

    def login_with_qr(self, v3: Optional[bool] = None, save: bool = True) -> str:
        """Login with a QR code (delegates to the base client)."""
        return self.base.login_with_qr(v3=v3, save=save)

    def login_with_token(self, auth_token: str, save: bool = True):
        """Login with an existing auth token (delegates to the base client)."""
        return self.base.login_with_token(auth_token, save=save)

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
        return self.base.send_message(to, text)

    def send_image(self, to: str, path: str) -> str:
        """
        Send an image.

        Args:
            to: Target mid (Square Chat)
            path: Path to image file

        Returns:
            Object ID
        """
        return self._send_media(to, path, "image")

    def start_push(self, chat_mids: List[str], on_event: Callable = None, fetch_type: int = 1):
        """
        Start LEGY Push for realtime event reception.

        Args:
            chat_mids: Square chat MIDs to watch
            on_event: Callback function(service_type, event_data)
            fetch_type: 1=Default (Sync), 2=Prefetch By Server
        """
        from .push import PushManager

        if self.push is None:
            self.push = PushManager(self)

        for mid in chat_mids:
            self.push.add_watched_chat(mid)

        if on_event:
            self.push.on_event = on_event

        self.push.start(services=[3], fetch_type=fetch_type)  # Square only

    def send_video(self, to: str, path: str) -> str:
        """
        Send a video.

        Args:
            to: Target mid (Square Chat)
            path: Path to video file

        Returns:
            Object ID
        """
        return self._send_media(to, path, "video")

    def send_audio(self, to: str, path: str) -> str:
        """
        Send an audio.

        Args:
            to: Target mid (Square Chat)
            path: Path to audio file

        Returns:
            Object ID
        """
        return self._send_media(to, path, "audio")

    def send_file(self, to: str, path: str, filename: Optional[str] = None) -> str:
        """
        Send a file.

        Args:
            to: Target mid (Square Chat)
            path: Path to file
            filename: Optional filename override

        Returns:
            Object ID
        """
        return self._send_media(to, path, "file", filename=filename)

    def _send_media(
        self,
        to: str,
        path: str,
        content_type: str,
        filename: Optional[str] = None
    ) -> str:
        """Internal media sender.

        Square chats (``m...``) upload plain to OBS; Talk targets (``u...`` /
        ``c...``) go through E2EE media upload (Phase 2 Step 6).
        """
        if to.startswith("m"):
            return self.base.obs.upload_obj_square_chat(
                square_chat_mid=to,
                path_or_bytes=path,
                content_type=content_type,
                filename=filename,
            )
        if to[:1] in ("u", "c"):
            if isinstance(path, (bytes, bytearray)):
                data = bytes(path)
            else:
                with open(path, "rb") as f:
                    data = f.read()
                if not filename:
                    import os as _os
                    filename = _os.path.basename(path)
            return self.base.obs.upload_media_by_e2ee(
                data=data, o_type=content_type, to=to, filename=filename
            )
        raise NotImplementedError(
            "Media sending supports Square chats (m...) and Talk (u.../c...) only"
        )
