# -*- coding: utf-8 -*-
"""
Square Helper for LINEPY

Provides high-level APIs for Square (OpenChat) operations.
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..base import BaseClient

from linepy.models.square_structs import SquareEvent as PydanticSquareEvent, SquareEventType

logger = logging.getLogger("linepy.square")


class SquareEvent:
    """Wrapper class for square chat events."""

    def __init__(self, raw_event: Dict[str, Any]):
        self.raw = raw_event

        # Event の field を取得 (Pydanticモデルの場合と辞書の場合で対応)
        if hasattr(raw_event, 'model_dump'):
            self._data = raw_event.model_dump(by_alias=True)
        elif isinstance(raw_event, dict):
            self._data = raw_event
        else:
            self._data = {}

    @property
    def event_type(self) -> int:
        """Get event type (payload key)."""
        payload = self._data.get('payload', {})
        if payload:
            # payload の中の最初のキーがイベントタイプ
            # 例: {"1": {...}} -> type 1 (receiveMessage)
            for key in payload:
                if key.isdigit():
                    return int(key)
        return 0

    @property
    def payload(self) -> Dict[str, Any]:
        """Get event payload."""
        return self._data.get('payload', {})

    @property
    def created_time(self) -> int:
        """Get event creation time."""
        return self._data.get('createdTime', 0)

    def get_message(self) -> Optional[Dict[str, Any]]:
        """Extract message if this is a message event."""
        # receiveMessage (type 1) の場合
        payload = self.payload
        if '1' in payload:
            return payload['1'].get('squareMessage', {}).get('message')
        return None

    def __repr__(self):
        return f"<SquareEvent type={self.event_type}>"


@dataclass
class SquareEventData:
    """Parsed Square Event Data."""
    square_event_type: Optional[int] = None
    sync_token: Optional[str] = None

    # Message / Member info
    member_mid: Optional[str] = None
    square_chat_mid: Optional[str] = None
    square_mid: Optional[str] = None
    sender_name: Optional[str] = None

    # Message content
    message_id: Optional[str] = None
    message_text: Optional[str] = None
    content_type: Optional[int] = None
    reply_message_id: Optional[str] = None

    # Metadata
    mention_data: Optional[Dict[str, Any]] = None
    mention_mids: Optional[List[str]] = None

    @classmethod
    def from_event(cls, event: PydanticSquareEvent) -> "SquareEventData":
        """Extract data from Pydantic SquareEvent object."""
        data = cls()

        # Basic info
        data.square_event_type = int(event.type) if event.type is not None else None
        data.sync_token = event.syncToken

        payload = event.payload
        if not payload:
            return data

        # Handle ReceiveMessage (Type 0)
        if event.type == SquareEventType.RECEIVE_MESSAGE and payload.receiveMessage:
            recv = payload.receiveMessage
            data.square_mid = recv.squareMid
            data.square_chat_mid = recv.squareChatMid
            data.sender_name = recv.senderDisplayName

            sq_msg = recv.squareMessage
            if sq_msg and sq_msg.message:
                msg = sq_msg.message
                data.member_mid = msg.from_
                data.message_id = msg.id_
                data.message_text = msg.text
                data.content_type = int(msg.contentType) if msg.contentType is not None else 0
                data.reply_message_id = msg.relatedMessageId

                # Mentions
                if msg.contentMetadata and 'MENTION' in msg.contentMetadata:
                    import json
                    try:
                        mentions = json.loads(msg.contentMetadata['MENTION'])
                        data.mention_data = mentions
                        data.mention_mids = mentions.get('MENTIONEES', [])
                    except Exception:
                        pass

        # Handle NotifiedMarkAsRead (Type 6)
        elif event.type == SquareEventType.NOTIFIED_MARK_AS_READ and payload.notifiedMarkAsRead:
            read = payload.notifiedMarkAsRead
            data.square_chat_mid = read.squareChatMid
            data.member_mid = read.sMemberMid
            data.message_id = read.messageId

        return data


class SquareHelper:
    """
    High-level helper for Square (OpenChat) operations.

    Provides convenient methods for:
    - Joining/leaving squares
    - Sending messages
    - Polling events with multi-threading
    - Event callbacks with decorators

    Example:
        helper = SquareHelper(client)

        # Register event handler
        @helper.event(1)  # 1 = receiveMessage
        def on_message(event, helper):
            msg = event.get_message()
            print(f"New message: {msg}")

        # Start polling
        helper.start_polling(["mXXXXX", "mYYYYY"])
    """

    def __init__(self, client: "BaseClient"):
        self.client = client
        self.square = client.square

        # Sync token for polling (managed per square chat)
        self._sync_tokens: Dict[str, str] = {}

        # Polling state
        self._polling = False
        self._threads: List[threading.Thread] = []

        # Event handlers by type
        self._type_handlers: Dict[int, List[Callable]] = {}

        # Generic event callbacks
        self._event_callbacks: Dict[str, List[Callable]] = {}

    # ========== Sync Token Management ==========

    def get_sync_token(self, square_chat_mid: str) -> Optional[str]:
        """Get stored sync token for a square chat."""
        return self._sync_tokens.get(square_chat_mid)

    def set_sync_token(self, square_chat_mid: str, token: str) -> None:
        """Store sync token for a square chat."""
        self._sync_tokens[square_chat_mid] = token

    # ========== Event Decorators ==========

    def event(self, event_type: int):
        """
        Decorator to register handler for specific event type.

        Event types:
            1: receiveMessage
            2: sendMessage
            3: notifiedJoinSquareChat
            4: notifiedLeaveSquareChat
            5: notifiedDestroyMessage
            6: notifiedMarkAsRead
            7: notifiedUpdateSquareMemberProfile
            ... (see SquareEventPayload for all types)

        Example:
            @helper.event(1)
            def on_message(event, helper):
                print(event.get_message())
        """
        def decorator(func: Callable):
            if event_type not in self._type_handlers:
                self._type_handlers[event_type] = []
            self._type_handlers[event_type].append(func)
            return func
        return decorator

    def on(self, event_name: str, callback: Callable) -> None:
        """
        Register a callback for a named event.

        Args:
            event_name: Event name (e.g., "message", "error", "started")
            callback: Function to call when event occurs
        """
        if event_name not in self._event_callbacks:
            self._event_callbacks[event_name] = []
        self._event_callbacks[event_name].append(callback)

    def emit(self, event_name: str, *args, **kwargs) -> None:
        """Emit a named event to registered callbacks."""
        if event_name in self._event_callbacks:
            for callback in self._event_callbacks[event_name]:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    logger.warning("Callback error (%s): %s", event_name, e)

    # ========== Polling ==========

    def start_polling(self, chat_mids: List[str]) -> None:
        """
        Start polling for events on specified square chats.

        Each chat MID gets its own thread.

        Args:
            chat_mids: List of square chat MIDs to monitor
        """
        if self._polling:
            logger.debug("Polling already running")
            return

        self._polling = True
        self._threads = []

        logger.info("Starting polling for %d chats", len(chat_mids))

        for mid in chat_mids:
            thread = threading.Thread(
                target=self._poll_chat,
                args=(mid,),
                daemon=True
            )
            thread.start()
            self._threads.append(thread)

        self.emit("started", chat_mids)

    def stop_polling(self) -> None:
        """Stop all polling threads."""
        logger.info("Stopping polling...")
        self._polling = False

        # Wait for threads to finish
        for thread in self._threads:
            thread.join(timeout=5)

        self._threads = []
        self.emit("stopped")

    def _poll_chat(self, chat_mid: str) -> None:
        """
        Polling loop for a single chat.

        Args:
            chat_mid: Square chat MID to poll
        """
        logger.debug("Polling started for %s", chat_mid[:12])

        # Initial fetch to get sync token
        try:
            response = self.square.fetchSquareChatEvents(
                squareChatMid=chat_mid,
                limit=1  # Just to get initial sync token
            )
            sync_token = response.syncToken if hasattr(response, 'syncToken') else response.get('syncToken')
            self.set_sync_token(chat_mid, sync_token)
        except Exception as e:
            logger.warning("Initial fetch failed for %s: %s", chat_mid[:12], e)
            return

        # Main polling loop
        while self._polling:
            try:
                sync_token = self.get_sync_token(chat_mid)

                response = self.square.fetchSquareChatEvents(
                    squareChatMid=chat_mid,
                    syncToken=sync_token,
                    limit=100
                )

                # Update sync token
                new_sync_token = response.syncToken if hasattr(response, 'syncToken') else response.get('syncToken')
                if new_sync_token:
                    self.set_sync_token(chat_mid, new_sync_token)

                # Process events
                events = response.events if hasattr(response, 'events') else response.get('events', [])

                for raw_event in events:
                    self._handle_event(raw_event, chat_mid)

            except Exception as e:
                logger.warning("Polling error for %s: %s", chat_mid[:12], e)
                self.emit("error", chat_mid, e)
                time.sleep(3)  # Pause before retry on error
                continue

            # Small delay to prevent hammering the server
            time.sleep(0.1)

        logger.debug("Polling stopped for %s", chat_mid[:12])

    def _handle_event(self, raw_event: Any, chat_mid: str) -> None:
        """
        Handle a single event by dispatching to registered handlers.

        Args:
            raw_event: Raw event data
            chat_mid: Source chat MID
        """
        event = SquareEvent(raw_event)
        event_type = event.event_type

        # Dispatch to type-specific handlers
        if event_type in self._type_handlers:
            for handler in self._type_handlers[event_type]:
                try:
                    # Run handler in separate thread to avoid blocking
                    threading.Thread(
                        target=handler,
                        args=(event, self),
                        daemon=True
                    ).start()
                except Exception as e:
                    logger.warning("Handler error (type %d): %s", event_type, e)

        # Emit generic event
        self.emit("event", event, chat_mid)

    # ========== High-Level APIs ==========

    def send_message(self, chat_mid: str, text: str) -> Any:
        """
        Send a text message to a square chat.

        Args:
            chat_mid: Square chat MID
            text: Message text

        Returns:
            API response
        """
        return self.square.sendSquareMessage(chat_mid, text)

    def join_by_ticket(self, ticket: str) -> Any:
        """
        Join a square by invitation ticket.

        Args:
            ticket: Invitation ticket string

        Returns:
            FindSquareByInvitationTicketResponse
        """
        return self.square.findSquareByInvitationTicketV2(ticket)

    def leave_square(self, square_mid: str) -> Any:
        """
        Leave a square.

        Args:
            square_mid: Square MID

        Returns:
            API response
        """
        return self.square.leaveSquare(squareMid=square_mid)

    def get_my_squares(self, limit: int = 100) -> Any:
        """
        Get list of squares the user has joined.

        Args:
            limit: Maximum number of squares to fetch

        Returns:
            GetJoinedSquaresResponse
        """
        return self.square.getJoinedSquares(limit=limit)

    def get_member_info(self, member_mid: str) -> Any:
        """
        Get information about a square member.

        Args:
            member_mid: Square member MID

        Returns:
            GetSquareMemberResponse
        """
        return self.square.getSquareMember(squareMemberMid=member_mid)

    def fetch_chat_events(
        self,
        chat_mid: str,
        sync_token: Optional[str] = None,
        limit: int = 100
    ) -> Any:
        """
        Fetch events for a specific square chat (low-level).

        Args:
            chat_mid: Square chat MID
            sync_token: Sync token from previous fetch
            limit: Maximum events to fetch

        Returns:
            FetchSquareChatEventsResponse
        """
        return self.square.fetchSquareChatEvents(
            squareChatMid=chat_mid,
            syncToken=sync_token,
            limit=limit
        )

    def getSquareChatMidbyInvitationTicket(self, InvitationTicket: str) -> Any:
        """
        Get Square Chat MID from invitation ticket.

        Args:
            InvitationTicket: Invitation ticket string

        Returns:
            Square Chat MID string
        """
        return self.square.findSquareByInvitationTicketV2(InvitationTicket).chat.squareChatMid

    def getSquareMidbyInvitationTicket(self, InvitationTicket: str) -> Any:
        """
        Get Square MID from invitation ticket.

        Args:
            InvitationTicket: Invitation ticket string

        Returns:
            Square MID string
        """
        return self.square.findSquareByInvitationTicketV2(InvitationTicket).chat.squareMid

    def joinSquareByInvitationTicket(self, InvitationTicket: str,displayName:str,displayImagePath:str) -> Any:
        squareMid=self.getSquareMidbyInvitationTicket(InvitationTicket)

        return self.square.joinSquare(squareMid=squareMid,displayName=displayName)
