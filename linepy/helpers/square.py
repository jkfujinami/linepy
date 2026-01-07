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
from linepy.models.square import SquareJoinMethodType

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

    def sendMessage(
        self,
        squareChatMid: str,
        text: str,
        relatedMessageId: Optional[str] = None,
        appendRandomId: bool = True,
    ) -> Any:
        """
        Send a message to a Square chat with optional random ID suffix.

        Appends an 8-character random ID to the message to avoid
        duplicate message detection (BAN evasion).

        Args:
            squareChatMid: Target chat MID
            text: Message text
            relatedMessageId: Optional message ID to reply to
            appendRandomId: If True, append random ID (default: True)

        Returns:
            SendMessageResponse
        """
        import random
        import string

        if appendRandomId:
            random_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
            text = f"{text}\n\nid:[{random_id}]"

        return self.square.sendSquareMessage(
            squareChatMid=squareChatMid,
            text=text,
            relatedMessageId=relatedMessageId,
        )

    def joinSquareByInvitationTicket(
        self,
        InvitationTicket: str,
        displayName: str,
        profileImagePath: str = None,
        defaultApprovalMessage: str = "I'm Mira!よろしくお願いします！",
        defaultJoinCode: str = "",
    ) -> Dict[str, Any]:
        """
        Join a Square (OC) and its chat using an invitation ticket.

        Automatically handles:
        - Join method detection (FREE/APPROVAL/CODE)
        - Square joining or request submission
        - Chat (subtalk) joining

        Args:
            InvitationTicket: Invitation ticket string
            displayName: Display name for the Square
            profileImagePath: Profile image path (optional)
            defaultApprovalMessage: Message for approval requests
            defaultJoinCode: Code for CODE-protected Squares

        Returns:
            Dict with status and details:
            {
                "status": "JOINED" | "PENDING" | "ALREADY_MEMBER" | "CODE_REQUIRED" | "ERROR",
                "square_mid": str,
                "chat_mid": str,
                "square_name": str,
                "chat_name": str,
                "message": str,
            }
        """
        result = {
            "status": "ERROR",
            "square_mid": None,
            "chat_mid": None,
            "square_name": None,
            "chat_name": None,
            "message": "",
        }

        try:
            # 1. Get Square/Chat info from ticket
            response = self.square.findSquareByInvitationTicketV2(InvitationTicket)

            square_mid = response.square.mid
            chat_mid = response.chat.squareChatMid
            square_name = response.square.name
            chat_name = response.chat.name
            join_method = response.square.joinMethod.type_
            membership = response.myMembership
            print(response.model_dump_json(indent=2))
            result["square_mid"] = square_mid
            result["chat_mid"] = chat_mid
            result["square_name"] = square_name
            result["chat_name"] = chat_name

            # 2. Check membership status
            if membership is not None:
                # Already a member of the Square
                state = membership.membershipState

                if state == 1:  # PENDING
                    result["status"] = "PENDING"
                    result["message"] = "承認待ち中です"
                    return result

                elif state == 2:  # JOINED
                    # Already in Square, try to join the chat
                    return self._join_chat_only(result, chat_mid, chat_name)
                else:
                    result["message"] = f"不明な状態: state={state}"
                    return result

            # 3. Not a member - join based on join method
            if join_method == SquareJoinMethodType.NONE:
                # FREE - direct join
                try:
                    join_result = self.square.joinSquare(
                        squareMid=square_mid,
                        displayName=displayName,
                        squareChatMid=chat_mid,
                    )
                    print(join_result.model_dump_json(indent=2))
                    try:
                        member_mid = join_result.squareMember.squareMemberMid
                        self.client.obs.upload_obj_square_member_image(member_mid=member_mid,path_or_bytes=profileImagePath,filename="Image.jpg")
                    except Exception as e:
                        print(f"画像のアップロードに失敗しました: {e}")
                    result["status"] = "JOINED"
                    result["message"] = f"Squareに参加しました: {square_name}"

                except Exception as e:
                    result["message"] = f"参加失敗: {e}"

            elif join_method == SquareJoinMethodType.APPROVAL:
                # APPROVAL - send request with joinMessage
                try:
                    join_result = self.square.joinSquare(
                        squareMid=square_mid,
                        displayName=displayName,
                        squareChatMid=chat_mid,
                        joinMessage=defaultApprovalMessage,
                    )
                    print(join_result.model_dump_json(indent=2))
                    try:
                        member_mid = join_result.squareChatMember.squareMemberMid
                        self.client.obs.upload_obj_square_member_image(member_mid=member_mid,path_or_bytes=profileImagePath,filename="Image.jpg")
                    except Exception as e:
                        print(f"画像のアップロードに失敗しました: {e}")
                    result["status"] = "PENDING"
                    result["message"] = f"参加リクエストを送信しました: {square_name}"

                except Exception as e:
                    error_str = str(e)
                    if "既に" in error_str or "already" in error_str.lower():
                        result["status"] = "PENDING"
                        result["message"] = "既にリクエスト済みです"
                    else:
                        result["message"] = f"リクエスト失敗: {e}"

            elif join_method == SquareJoinMethodType.CODE:
                # CODE - need passcode
                if defaultJoinCode:
                    try:
                        join_result = self.square.joinSquare(
                            squareMid=square_mid,
                            displayName=displayName,
                            squareChatMid=chat_mid,
                            passCode=defaultJoinCode,
                        )
                        member_mid = join_result.squareChatMember.squareMemberMid
                        self.client.obs.upload_obj_square_member_image(member_mid=member_mid,path_or_bytes=profileImagePath,filename="Image.jpg")
                        result["status"] = "JOINED"
                        result["message"] = f"Squareに参加しました: {square_name}"

                    except Exception as e:
                        result["message"] = f"参加失敗 (コード不正?): {e}"
                else:
                    result["status"] = "CODE_REQUIRED"
                    result["message"] = "パスコードが必要です"

            else:
                result["message"] = f"不明な参加方法: {join_method}"

        except Exception as e:
            result["message"] = f"エラー: {e}"

        return result

    def _join_chat_only(self, result: Dict, chat_mid: str, chat_name: str) -> Dict:
        """Join only the chat (when already a Square member)"""
        try:
            self.square.joinSquareChat(chat_mid)
            result["status"] = "JOINED"
            result["message"] = f"チャットに参加しました: {chat_name}"
        except Exception as e:
            error_str = str(e)
            # 410 = Already member / 既に参加済み
            if "[410]" in error_str or "既に" in error_str or "already" in error_str.lower() or "メンバー" in error_str:
                result["status"] = "ALREADY_MEMBER"
                result["message"] = f"既に参加済み: {chat_name}"
            else:
                result["message"] = f"チャット参加失敗: {e}"
        return result
