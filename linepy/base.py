"""
Base Client for LINEPY

Low-level API client that handles authentication and service calls.
"""

from typing import Optional, Dict, Any, Callable, List, Union

from .config import Device, get_device_details, build_app_name, is_v3_support
from .request import RequestClient
from .storage import BaseStorage, FileStorage, TokenManager


class LineException(Exception):
    """LINE API Exception"""

    def __init__(self, code: int, message: str, metadata: Optional[Dict] = None):
        self.code = code
        self.message = message
        self.metadata = metadata or {}

        # Build detailed message
        msg = f"[{code}] {message}"
        if self.metadata:
            msg += f"\nMetadata: {self.metadata}"
        super().__init__(msg)


class BaseClient:
    """
    Low-level LINE API Client.

    Handles:
    - Device configuration
    - Authentication
    - Thrift RPC calls
    - Token persistence

    Example:
        # Create client with auto-login from saved token
        client = BaseClient(device="DESKTOPWIN", storage_path=".linepy.json")

        if not client.auto_login():
            client.login_with_qr()  # QRコードでログイン

        profile = client.get_profile()
    """

    def __init__(
        self,
        device: Device = "DESKTOPWIN",
        version: Optional[str] = None,
        system_name: str = "LINEPY",
        storage: Optional[Union[BaseStorage, str]] = None,
    ):
        """
        Initialize LINE client.

        Args:
            device: Device type (DESKTOPWIN, DESKTOPMAC, ANDROID, IOS, etc.)
            version: Optional custom app version
            system_name: Device name shown in LINE
            storage: Storage backend or path to storage file
                     - None: Use default FileStorage (.linepy_storage.json)
                     - str: Path to storage file
                     - BaseStorage: Custom storage backend
        """
        details = get_device_details(device, version)
        if not details:
            raise ValueError(f"Unsupported device: {device}")

        self.device = device
        self.device_details = details
        self.app_name = build_app_name(details)
        self.system_name = system_name

        self.request = RequestClient(
            device_name=self.app_name,
            system_name=system_name,
        )

        # Initialize storage
        if storage is None:
            self.storage = FileStorage()
        elif isinstance(storage, str):
            self.storage = FileStorage(storage)
        else:
            self.storage = storage

        self.token_manager = TokenManager(self.storage)

        # Wire LEGY transport token-lifecycle hooks (Phase 1 Step 2.3)
        self.request.on_next_access = self._on_next_access_token
        self.request.refresh_hook = self._legy_refresh_hook

        # Login handler
        from .login import Login

        self.login_handler = Login(self)

        # Talk service
        from .talk import TalkService

        self.talk = TalkService(self)

        # Sync service
        from .sync import SyncService

        self.sync = SyncService(self)

        # Square (OpenChat) service
        from .square import SquareService

        self.square = SquareService(self)

        # Channel & Timeline service
        from .channel import ChannelService
        from .timeline import Timeline

        self.channel = ChannelService(self)
        self.timeline = Timeline(self)

        # OBS Client (Object Storage)
        from .obs import ObsBase
        self.obs = ObsBase(self)

        # LIFF & VOOM (Phase 3)
        from .liff import LiffClient
        from .voom import VoomClient

        self.liff = LiffClient(self)
        self.voom = VoomClient(self)

        # Auth service
        from .services.auth import AuthService
        self.auth_service = AuthService(self)

        # Square helper (high-level APIs)
        from .helpers.square import SquareHelper
        self.square_helper = SquareHelper(self)

        # Push manager (LEGY Push for realtime events)
        self.push: Optional["PushManager"] = None  # Lazy init

        # User state
        self.auth_token: Optional[str] = None
        self.mid: Optional[str] = None
        self.profile: Optional[Dict] = None

        # E2EE handler
        from .e2ee import E2EE

        self.e2ee = E2EE(self)

        # Event callbacks
        self._callbacks: Dict[str, List[Callable]] = {}

    # ========== Login Methods ==========

    def login_with_email(
        self,
        email: str,
        password: str,
        pincode: str = "114514",
        e2ee: bool = True,
    ) -> str:
        """
        Login with email and password.

        Args:
            email: LINE account email
            password: Account password
            pincode: 6-digit PIN code for verification
            e2ee: Enable E2EE login

        Returns:
            Auth token
        """
        auth_token = self.login_handler.login_with_email(
            email=email,
            password=password,
            pincode=pincode,
            e2ee=e2ee,
        )
        self.set_auth_token(auth_token)

        # Persist refresh_token/expire captured during the E2EE handshake
        # (loginV2 path) or via the outer login_result plumbing.
        last_response = getattr(self.login_handler, "_last_login_response", None)
        if last_response:
            self.token_manager.save_login_result(last_response)

        # 本家's withPassword() unconditionally verifies the just-installed
        # E2EE login key against the server after every successful login.
        try:
            self.e2ee.verify_login_key()
        except Exception as exc:
            print(f"[Login] verify_login_key failed: {exc}")

        # Get profile
        self.profile = self.get_profile()
        self.mid = self.profile.mid

        print(f"Logged in as: {self.profile.display_name}")
        return auth_token

    def login_with_qr(self, v3: Optional[bool] = None, save: bool = True) -> str:
        """
        Login with QR code.

        Args:
            v3: Use v3 login (auto-detected if None)
            save: Save token to storage

        Returns:
            Auth token
        """
        auth_token = self.login_handler.login_with_qr(v3=v3)
        self.set_auth_token(auth_token)

        # Save auth token explicitly
        if save:
            self.token_manager.auth_token = auth_token

        # Save login result (for refresh token etc.)
        last_response = getattr(self.login_handler, "_last_login_response", None)
        if save and last_response:
            self.token_manager.save_login_result(last_response)

        # 本家's withQrCode() unconditionally verifies the just-installed
        # E2EE login key against the server after every successful login.
        try:
            self.e2ee.verify_login_key()
        except Exception as exc:
            print(f"[Login] verify_login_key failed: {exc}")

        # Get profile
        self.profile = self.get_profile()
        self.mid = self.profile.mid

        # Save MID
        if save:
            self.token_manager.mid = self.mid

        print(f"Logged in as: {self.profile.display_name}")
        return auth_token

    def login_with_token(self, auth_token: str, save: bool = True):
        """
        Login with existing auth token.

        Args:
            auth_token: LINE auth token
            save: Save token to storage
        """
        self.set_auth_token(auth_token)

        # Save token
        if save:
            self.token_manager.auth_token = auth_token

        # Get profile
        self.profile = self.get_profile()
        self.mid = self.profile.mid

        # Save MID
        if save:
            self.token_manager.mid = self.mid

        print(f"Logged in as: {self.profile.display_name}")

    def auto_login(self) -> bool:
        """
        Automatically login using saved token.

        Returns:
            True if login was successful, False if no valid token
        """
        if not self.token_manager.is_token_valid():
            return False

        token = self.token_manager.auth_token
        if not token:
            return False

        try:
            self.set_auth_token(token)

            # Verify token by getting profile
            self.profile = self.get_profile()
            self.mid = self.profile.mid

            print(f"Auto-logged in as: {self.profile.display_name}")
            return True
        except Exception as e:
            print(f"Auto-login failed: {e}")
            return False

    def logout(self, clear_storage: bool = True):
        """
        Logout and optionally clear stored credentials.

        Args:
            clear_storage: Clear stored tokens
        """
        self.auth_token = None
        self.mid = None
        self.profile = None
        self.request.auth_token = None

        if clear_storage:
            self.token_manager.clear()

    def close(self):
        """Close client connections"""
        self.request.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ========== Authentication ==========

    @property
    def is_logged_in(self) -> bool:
        """Check if client is logged in"""
        return self.auth_token is not None

    def set_auth_token(self, token: str):
        """Set authentication token for requests"""
        self.auth_token = token
        self.request.auth_token = token
        self.token_manager.auth_token = token

    def _on_next_access_token(self, token: str) -> None:
        """Handle server-issued ``x-line-next-access`` rotation."""
        if token and token != self.auth_token:
            self.set_auth_token(token)

    def _legy_refresh_hook(self) -> bool:
        """Refresh callback invoked when a request hits MUST_REFRESH_V3_TOKEN."""
        from .config import PRIMARY_DEVICES

        if self.device in PRIMARY_DEVICES:
            return False
        if not self.token_manager.refresh_token:
            return False
        try:
            old = self.auth_token
            new_token = self.refresh_access_token()
            return bool(new_token) and new_token != old
        except Exception:
            return False

    def refresh_access_token(self) -> str:
        """
        Refresh the current access token.

        Using the stored refresh token, it fetches a new access token
        and updates the client authentication state.

        NOTE: Disabled for Primary Devices (ANDROID, IOS) to avoid
        session conflicts with the actual physical device.

        Returns:
            New access token string
        """
        from .config import PRIMARY_DEVICES

        if self.device in PRIMARY_DEVICES:
            print(f"[WARN] Token refresh is DISABLED for Primary Device ({self.device})")
            print("       Refreshing would invalidate the session on your physical phone.")
            print("       If the token is expired, please extract a new one via ADB.")
            # Return current token as is (effectively doing nothing)
            return self.auth_token if self.auth_token else ""

        refresh_token = self.token_manager.refresh_token
        if not refresh_token:
            # 抽出したトークン(JWT)からリフレッシュトークンを取り出すロジックが必要だが
            # 現状はrefresh_tokenとして保存されていることを前提とする
            raise LineException(0, "No refresh token available")

        try:
            response = self.auth_service.refresh(refresh_token)

            new_access_token = response.access_token
            new_refresh_token = response.refresh_token

            if new_access_token:
                print("[Auth] Access token refreshed")
                self.set_auth_token(new_access_token)

            if new_refresh_token:
                print("[Auth] Refresh token updated")
                self.token_manager.refresh_token = new_refresh_token
            else:
                # リフレッシュトークンが変わらない場合もあるが、Durationだけ更新されるかも
                pass

            return new_access_token

        except Exception as e:
            raise LineException(0, f"Failed to refresh token: {e}")

    # ========== Push (Realtime Events) ==========

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
        pass

    def stop_push(self):
        """Stop LEGY Push."""
        if self.push:
            self.push.stop()

    # ========== Polling (High-frequency alternative) ==========

    def start_polling(self, chat_mids: List[str], on_event: Callable = None, fetch_type: int = 2):
        """
        Start high-frequency polling for Square events.

        Alternative to Push connection. Creates one thread per chat
        for maximum throughput.

        Args:
            chat_mids: Square chat MIDs to watch
            on_event: Callback function(service_type, event_data)
            fetch_type: 1=Default, 2=Prefetch By Server (recommended)
        """
        from .polling import PollingManager

        if not hasattr(self, 'polling') or self.polling is None:
            self.polling = PollingManager(self)

        self.polling.start(
            watched_chats=chat_mids,
            on_event=on_event,
            fetch_type=fetch_type,
        )

    def stop_polling(self):
        """Stop polling."""
        if hasattr(self, 'polling') and self.polling:
            self.polling.stop()

    # ========== Service Calls ==========

    def _call_service(
        self,
        path: str,
        method: str,
        params: List = None,
        protocol: int = 4,
        timeout: Optional[float] = None,
    ) -> Any:
        """
        Make a Thrift RPC call using linejs-style params.

        Args:
            path: API endpoint
            method: Method name
            params: Parameters in [[type, field_id, value], ...] format
            protocol: Thrift protocol (3=binary, 4=compact)
            timeout: Request timeout

        Returns:
            Response data
        """
        from .thrift import write_thrift

        if params is None:
            params = []

        # Generate Thrift request data
        data = write_thrift(params, method, protocol)

        # Send request
        response = self.request.request(
            path=path,
            data=data,
            protocol=protocol,
            timeout=timeout,
        )

        # Check for error
        if isinstance(response, dict) and "error" in response:
            err = response["error"]
            raise LineException(
                code=err.get("code", -1),
                message=err.get("message", "Unknown error"),
                metadata=err.get("metadata"),
            )

        return response

    # ========== Talk Service ==========

    def get_profile(self) -> Any:
        """Get user profile"""
        return self.talk.get_profile()

    def get_contact(self, mid: str) -> Dict:
        """Get contact by mid"""
        # getContact_args: [[11, 2, mid]]
        return self._call_service(
            path="/S4",
            method="getContact",
            params=[[11, 2, mid]],
        )

    def get_contacts(self, mids: List[str]) -> List[Dict]:
        """Get multiple contacts by mids"""
        # getContacts_args: [[15, 2, [11, mids]]]
        return self._call_service(
            path="/S4",
            method="getContacts",
            params=[[15, 2, [11, mids]]],
        )

    def get_all_contact_ids(self) -> List[str]:
        """Get all friend mids"""
        # getAllContactIds_args: [[8, 1, syncReason]]
        return self._call_service(
            path="/S4",
            method="getAllContactIds",
            params=[[8, 1, 0]],  # syncReason = 0
        )

    def get_chats(
        self,
        chat_mids: List[str],
        with_members: bool = True,
        with_invitees: bool = True,
    ) -> Dict:
        """Get chats by mids"""
        # getChats_args: [[12, 1, request]]
        return self._call_service(
            path="/S4",
            method="getChats",
            params=[
                [
                    12,
                    1,
                    [
                        [15, 1, [11, chat_mids]],
                        [2, 2, with_members],
                        [2, 3, with_invitees],
                    ],
                ]
            ],
        )

    def get_all_chat_mids(
        self, with_member_chats: bool = True, with_invited_chats: bool = True
    ) -> Dict:
        """Get all chat mids"""
        # getAllChatMids_args: [[12, 1, request], [8, 2, syncReason]]
        return self._call_service(
            path="/S4",
            method="getAllChatMids",
            params=[
                [
                    12,
                    1,
                    [
                        [2, 1, with_member_chats],
                        [2, 2, with_invited_chats],
                    ],
                ],
                [8, 2, 0],  # syncReason
            ],
        )

    def get_reqseq(self) -> int:
        """Next request sequence number (persisted)."""
        return self.token_manager.get_next_reqseq("talk")

    # Message relation / service codes for replies (Phase 2 Step 5.2)
    _REPLY_RELATION_TYPE = 3   # MessageRelationType.REPLY
    _TALK_SERVICE_CODE = 1     # ServiceCode.TALK

    def send_message(
        self,
        to: str,
        text: Optional[str] = None,
        content_type: int = 0,
        content_metadata: Optional[Dict[str, str]] = None,
        related_message_id: Optional[str] = None,
        location=None,
        chunks: Optional[List[bytes]] = None,
        e2ee: Optional[bool] = None,
    ) -> Any:
        """
        Send a message with automatic E2EE encryption and failover.

        Faithful port of 本家 ``TalkService.sendMessage``:
        * When ``e2ee`` is requested for text/location and no chunks are given,
          the payload is encrypted via the E2EE engine and re-sent as chunks.
        * A plain send that fails with an ``E2EE`` error automatically retries
          with ``e2ee=True`` (only when ``e2ee`` was left unspecified).
        * ``related_message_id`` adds REPLY relation metadata.
        """
        content_metadata = dict(content_metadata or {})

        # Encrypt-and-resend pass.
        if e2ee and not chunks and (location is not None or text is not None):
            enc_chunks = self.e2ee.encrypt_e2ee_message(
                to, text if text is not None else location, content_type
            )
            meta = dict(content_metadata)
            meta.update({
                "e2eeVersion": "2",
                "contentType": str(content_type or 0),
                "e2eeMark": "2",
            })
            return self.send_message(
                to=to,
                content_type=content_type,
                content_metadata=meta,
                related_message_id=related_message_id,
                chunks=enc_chunks,
                e2ee=e2ee,
            )

        message_fields = [
            [11, 2, to],
            [8, 15, content_type or 0],
        ]
        if text is not None:
            message_fields.append([11, 10, text])
        if content_metadata:
            message_fields.append([13, 18, content_metadata])
        if chunks:
            message_fields.append([15, 20, [11, list(chunks)]])
        if related_message_id is not None:
            message_fields.append([11, 21, related_message_id])
            message_fields.append([8, 22, self._REPLY_RELATION_TYPE])
            message_fields.append([8, 24, self._TALK_SERVICE_CODE])

        params = [[8, 1, self.get_reqseq()], [12, 2, message_fields]]

        try:
            return self._call_service(path="/S4", method="sendMessage", params=params)
        except Exception as error:
            if e2ee is None and "E2EE" in str(getattr(error, "message", error)):
                return self.send_message(
                    to=to,
                    text=text,
                    content_type=content_type,
                    content_metadata=content_metadata,
                    related_message_id=related_message_id,
                    location=location,
                    chunks=chunks,
                    e2ee=True,
                )
            raise

    # ========== Compact message protocol (/CA5, /ECA5) ==========

    def send_compact_message(
        self,
        to: str,
        text: Optional[str] = None,
        chunks: Optional[List[bytes]] = None,
        e2ee: Optional[bool] = None,
    ):
        """Send via the fast compact protocol, with E2EE failover (codes 82/99)."""
        if chunks or e2ee is True:
            return self.send_compact_e2ee_message(to=to, text=text, chunks=chunks)
        if text is None:
            raise ValueError("send_compact_message requires text or chunks")
        try:
            return self.send_compact_plain_message(to, text)
        except Exception as error:
            code = getattr(error, "code", None)
            if e2ee is None and code in (82, 99):
                return self.send_compact_e2ee_message(to=to, text=text)
            raise

    def send_compact_plain_message(self, to: str, text: str):
        from .compact import pack_compact_plain_message, decode_compact_message_response, \
            COMPACT_PLAIN_MESSAGE_ENDPOINT

        seq_id = self.get_reqseq()
        body = pack_compact_plain_message(seq_id, to, text)
        raw = self.request.compact_request(COMPACT_PLAIN_MESSAGE_ENDPOINT, seq_id, body)
        return decode_compact_message_response(raw)

    def send_compact_e2ee_message(
        self, to: str, text: Optional[str] = None, chunks: Optional[List[bytes]] = None
    ):
        from .compact import pack_compact_e2ee_message, decode_compact_message_response, \
            COMPACT_E2EE_MESSAGE_ENDPOINT

        if not chunks:
            if text is None:
                raise ValueError("send_compact_e2ee_message requires text or chunks")
            chunks = self.e2ee.encrypt_e2ee_message(to, text)
        seq_id = self.get_reqseq()
        body = pack_compact_e2ee_message(seq_id, to, chunks)
        raw = self.request.compact_request(COMPACT_E2EE_MESSAGE_ENDPOINT, seq_id, body)
        return decode_compact_message_response(raw)

    # ========== Events ==========

    def get_dispatcher(self):
        """Lazily create the PUSH event dispatcher (Phase 3 Step 10)."""
        dispatcher = getattr(self, "_dispatcher", None)
        if dispatcher is None:
            from .listener import EventDispatcher

            dispatcher = EventDispatcher(self)
            self._dispatcher = dispatcher
        return dispatcher

    def listen(self, talk: bool = True, square: bool = True) -> None:
        """Start the PUSH stream and dispatch decrypted events.

        Talk operations are auto-decrypted and emitted as ``message`` events
        (``TalkMessage``); Square notifications as ``square:message``
        (``SquareMessage``). Register handlers via :meth:`on`.
        """
        dispatcher = self.get_dispatcher()

        def _on_event(op):
            dispatcher.dispatch_talk_operation(op)

        # Reuse the existing PUSH machinery; each operation flows through the
        # dispatcher so E2EE decryption and event fan-out happen centrally.
        chat_mids = list(getattr(self, "_watch_chat_mids", []) or [])
        return self.start_push(chat_mids, on_event=_on_event)

    def on(self, event: str, callback: Optional[Callable] = None):
        """
        Register event callback.
        Can be used as a method or decorator.

        Args:
            event: Event name
            callback: Callback function (optional if used as decorator)
        """

        def decorator(func: Callable):
            if event not in self._callbacks:
                self._callbacks[event] = []
            self._callbacks[event].append(func)
            return func

        if callback:
            return decorator(callback)
        return decorator

    def emit(self, event: str, *args, **kwargs):
        """Emit event to callbacks"""
        for callback in self._callbacks.get(event, []):
            callback(*args, **kwargs)

    # ========== Utilities ==========

    def get_to_type(self, mid: str) -> Optional[int]:
        """Get target type from mid prefix"""
        type_map = {
            "u": 0,  # USER
            "r": 1,  # ROOM
            "c": 2,  # GROUP
            "s": 3,  # SQUARE
            "m": 4,  # SQUARE_CHAT
            "p": 5,  # SQUARE_MEMBER
            "v": 6,  # BOT
            "t": 7,  # ?
        }
        if mid and len(mid) > 0:
            return type_map.get(mid[0])
        return None
