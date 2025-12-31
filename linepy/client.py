"""
High-level Client for LINEPY

User-friendly API with event handling and convenient methods.
"""

from typing import Optional, Callable, Dict, List, Any
import threading
import time

from .base import BaseClient, LineException
from .config import Device


class Message:
    """Message wrapper class"""

    def __init__(self, raw: Dict, client: "Client"):
        self._raw = raw
        self._client = client

    @property
    def id(self) -> str:
        return self._raw.get(4, "")  # id field

    @property
    def from_(self) -> str:
        """Sender mid"""
        return self._raw.get(1, "")  # from field

    @property
    def to(self) -> str:
        """Target mid"""
        return self._raw.get(2, "")  # to field

    @property
    def text(self) -> Optional[str]:
        """Message text"""
        return self._raw.get(10)  # text field

    @property
    def content_type(self) -> int:
        """Content type (0=text, 1=image, etc.)"""
        return self._raw.get(15, 0)

    @property
    def raw(self) -> Dict:
        """Raw message data"""
        return self._raw

    def reply(self, text: str) -> Dict:
        """Reply to this message"""
        # Determine reply target
        target = self.to if self.from_ == self._client.mid else self.to
        if target.startswith('c') or target.startswith('r'):
            # Group/Room - reply to the group
            target = self.to
        else:
            # 1:1 - reply to sender
            target = self.from_

        return self._client.send_message(target, text)


class User:
    """User wrapper class"""

    def __init__(self, raw: Dict, client: Optional["Client"] = None):
        self._raw = raw
        self._client = client

    @property
    def mid(self) -> str:
        return self._raw.get(1, "")

    @property
    def display_name(self) -> str:
        return self._raw.get(20, "")

    @property
    def status_message(self) -> Optional[str]:
        return self._raw.get(22)

    @property
    def picture_path(self) -> Optional[str]:
        return self._raw.get(23)

    @property
    def raw(self) -> Dict:
        return self._raw


class Chat:
    """Chat (Group/Room) wrapper class"""

    def __init__(self, raw: Dict, client: "Client"):
        self._raw = raw
        self._client = client

    @property
    def mid(self) -> str:
        return self._raw.get(1, "")

    @property
    def name(self) -> Optional[str]:
        return self._raw.get(2)

    @property
    def members(self) -> List[str]:
        return self._raw.get(4, [])

    @property
    def raw(self) -> Dict:
        return self._raw

    def send(self, text: str) -> Dict:
        """Send message to this chat"""
        return self._client.send_message(self.mid, text)


class Client:
    """
    High-level LINE Client.

    Provides:
    - Easy login (QR code, token)
    - Event-driven message handling
    - Convenient wrapper classes

    Example:
        client = Client(device="DESKTOPWIN")

        # Login with auth token
        client.login(auth_token="your_token")

        # Or login with QR code
        client.login_with_qr()

        @client.on("message")
        def on_message(msg):
            print(f"Received: {msg.text}")
            if msg.text == "!ping":
                msg.reply("pong!")

        client.poll()  # Start listening
    """

    def __init__(
        self,
        device: Device = "DESKTOPWIN",
        version: Optional[str] = None,
        system_name: str = "LINEPY",
    ):
        """
        Initialize client.

        Args:
            device: Device type
            version: Optional custom app version
            system_name: Device name shown in LINE
        """
        self.base = BaseClient(device=device, version=version, system_name=system_name)
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._polling = False
        self._poll_thread: Optional[threading.Thread] = None

    def close(self):
        """Close client"""
        self._polling = False
        if self._poll_thread:
            self._poll_thread.join(timeout=5)
        self.base.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ========== Login ==========

    @property
    def is_logged_in(self) -> bool:
        return self.base.is_logged_in

    @property
    def auth_token(self) -> Optional[str]:
        return self.base.auth_token

    @property
    def mid(self) -> Optional[str]:
        return self.base.mid

    def login(self, auth_token: str):
        """
        Login with authentication token.

        Args:
            auth_token: LINE auth token
        """
        self.base.login_with_token(auth_token)

    def login_with_email(
        self,
        email: str,
        password: str,
        pincode: str = "114514",
        e2ee: bool = True,
    ):
        """
        Login with email and password.

        Args:
            email: LINE account email
            password: Account password
            pincode: 6-digit PIN code for verification
            e2ee: Enable E2EE login
        """
        self.base.login_with_email(
            email=email,
            password=password,
            pincode=pincode,
            e2ee=e2ee,
        )

    def login_with_qr(self, v3: Optional[bool] = None):
        """
        Login with QR code.

        Displays QR code URL for scanning.

        Args:
            v3: Use v3 login (auto-detected if None)
        """
        self.base.login_with_qr(v3=v3)

    # ========== Events ==========

    def on(self, event: str):
        """
        Decorator for event handlers.

        Args:
            event: Event name ("message", "event", etc.)

        Example:
            @client.on("message")
            def handle_message(msg):
                print(msg.text)
        """
        def decorator(func: Callable):
            if event not in self._event_handlers:
                self._event_handlers[event] = []
            self._event_handlers[event].append(func)
            return func
        return decorator

    def emit(self, event: str, *args, **kwargs):
        """Emit event to handlers"""
        for handler in self._event_handlers.get(event, []):
            try:
                handler(*args, **kwargs)
            except Exception as e:
                print(f"Error in event handler: {e}")

    # ========== Polling ==========

    def poll(self, background: bool = False):
        """
        Start polling for events.

        Args:
            background: If True, poll in background thread
        """
        if background:
            self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._poll_thread.start()
        else:
            self._poll_loop()

    def _poll_loop(self):
        """Main polling loop"""
        self._polling = True
        revision = 0

        print("Starting event polling...")

        while self._polling:
            try:
                # TODO: Implement fetchOperations
                # operations = self.base.fetch_operations(revision)
                # for op in operations:
                #     self._handle_operation(op)
                #     revision = max(revision, op.get("revision", 0))

                time.sleep(1)  # Placeholder

            except KeyboardInterrupt:
                print("\nStopping...")
                break
            except Exception as e:
                print(f"Polling error: {e}")
                time.sleep(5)

        self._polling = False

    def stop_polling(self):
        """Stop polling"""
        self._polling = False

    # ========== Messaging ==========

    def send_message(self, to: str, text: str) -> Dict:
        """
        Send a text message.

        Args:
            to: Target mid (user/group/room)
            text: Message text

        Returns:
            Message response
        """
        return self.base.send_message(to, text)

    # ========== Contacts ==========

    def get_profile(self) -> User:
        """Get own profile"""
        raw = self.base.get_profile()
        return User(raw, self)

    def get_contact(self, mid: str) -> User:
        """Get a contact by mid"""
        raw = self.base.get_contact(mid)
        return User(raw, self)

    def get_all_friends(self) -> List[User]:
        """Get all friends"""
        mids = self.base.get_all_contact_ids()
        contacts = self.base.get_contacts(mids)
        return [User(c, self) for c in contacts]

    # ========== Chats ==========

    def get_chat(self, chat_mid: str) -> Chat:
        """Get a chat by mid"""
        result = self.base.get_chats([chat_mid])
        chats = result.get(1, [])  # chats field
        if chats:
            return Chat(chats[0], self)
        raise ValueError(f"Chat not found: {chat_mid}")

    def get_all_chats(self) -> List[Chat]:
        """Get all joined chats"""
        mids_result = self.base.get_all_chat_mids()
        member_mids = mids_result.get(1, [])  # memberChatMids

        if not member_mids:
            return []

        result = self.base.get_chats(member_mids)
        chats = result.get(1, [])
        return [Chat(c, self) for c in chats]
