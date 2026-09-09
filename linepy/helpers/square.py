# -*- coding: utf-8 -*-
"""
Square Helper for LINEPY

Provides high-level APIs for Square (OpenChat) operations.
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from ..base import BaseClient

from linepy.models import SquareEvent as PydanticSquareEvent
from linepy.models import SquareEventType, SquareJoinMethodType

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
        data.square_event_type = int(event.type_) if event.type_ is not None else None
        data.sync_token = event.sync_token

        payload = event.payload
        if not payload:
            return data

        # Handle ReceiveMessage (Type 0)
        if event.type_ == SquareEventType.RECEIVE_MESSAGE and payload.receive_message:
            recv = payload.receive_message
            data.square_mid = recv.square_mid
            data.square_chat_mid = recv.square_chat_mid
            data.sender_name = recv.sender_display_name

            sq_msg = recv.square_message
            if sq_msg and sq_msg.message:
                msg = sq_msg.message
                data.member_mid = msg.from_
                data.message_id = msg.id_
                data.message_text = msg.text
                data.content_type = int(msg.content_type) if msg.content_type is not None else 0
                data.reply_message_id = msg.related_message_id

                # Mentions
                if msg.content_metadata and 'MENTION' in msg.content_metadata:
                    import json
                    try:
                        mentions = json.loads(msg.content_metadata['MENTION'])
                        data.mention_data = mentions
                        data.mention_mids = mentions.get('MENTIONEES', [])
                    except Exception:
                        pass

        # Handle NotifiedMarkAsRead (Type 6)
        elif event.type_ == SquareEventType.NOTIFIED_MARK_AS_READ and payload.notified_mark_as_read:
            read = payload.notified_mark_as_read
            data.square_chat_mid = read.square_chat_mid
            data.member_mid = read.s_member_mid
            data.message_id = read.message_id

        return data


class SquareHelper:
    """
    High-level helper for Square (OpenChat) operations.

    Provides convenient methods for:
    - Joining/leaving squares
    - Sending messages
    - Event handlers keyed by Square event type

    Reception itself belongs to :mod:`linepy.realtime`: this helper drives
    :class:`~linepy.realtime.polling.PollingManager` and adds the
    ``@helper.event(<type>)`` dispatch on top. Sync tokens are persisted by
    the client's TokenManager, so a restart resumes where it left off.

    Example:
        helper = SquareHelper(client)

        # Register event handler
        @helper.event(1)  # 1 = receiveMessage
        def on_message(event, helper):
            msg = event.get_message()
            logger.info("New message: %s", msg)

        # Start polling
        helper.start_polling(["mXXXXX", "mYYYYY"])
    """

    def __init__(self, client: "BaseClient"):
        self.client = client
        self.square = client.square

        # Handlers registered through @helper.event(<type>)
        self._type_handlers: Dict[int, List[Callable]] = {}

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

    def start_polling(self, chat_mids: List[str], fetch_type: int = 2) -> None:
        """
        Start polling for events on the given square chats.

        Delegates to the client's PollingManager (one worker thread per chat,
        one dispatch thread) and routes what it yields into the handlers
        registered with :meth:`event`.

        Args:
            chat_mids: Square chat MIDs to monitor
            fetch_type: 1=Default, 2=Prefetch By Server (recommended)
        """
        self.client.start_polling(
            chat_mids, on_event=self._on_polled_event, fetch_type=fetch_type
        )

    def stop_polling(self) -> None:
        """Stop polling."""
        self.client.stop_polling()

    def _on_polled_event(self, service_type: int, raw_event: Any) -> None:
        """PollingManager callback: wrap, dispatch, and emit on the client bus."""
        try:
            event = SquareEvent(raw_event)
        except Exception as exc:
            logger.warning("Could not read square event: %s", exc)
            return

        for handler in self._type_handlers.get(event.event_type, []):
            try:
                handler(event, self)
            except Exception as exc:
                logger.warning(
                    "Handler error (type %s): %s", event.event_type, exc
                )

        self.client.emit("square:event", event)

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
        return self.square.findSquareByInvitationTicketV2(InvitationTicket).chat.square_chat_mid

    def getSquareMidbyInvitationTicket(self, InvitationTicket: str) -> Any:
        """
        Get Square MID from invitation ticket.

        Args:
            InvitationTicket: Invitation ticket string

        Returns:
            Square MID string
        """
        return self.square.findSquareByInvitationTicketV2(InvitationTicket).chat.square_mid

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
            chat_mid = response.chat.square_chat_mid
            square_name = response.square.name
            chat_name = response.chat.name
            join_method = response.square.join_method.type_
            membership = response.my_membership
            logger.debug("findSquareByInvitationTicket: %s", response)
            result["square_mid"] = square_mid
            result["chat_mid"] = chat_mid
            result["square_name"] = square_name
            result["chat_name"] = chat_name

            # 2. Check membership status
            if membership is not None:
                # Already a member of the Square
                state = membership.membership_state

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
                    logger.debug("joinSquare: %s", join_result)
                    try:
                        member_mid = join_result.square_member.square_member_mid
                        self.client.obs.upload_obj_square_member_image(member_mid=member_mid,path_or_bytes=profileImagePath,filename="Image.jpg")
                    except Exception as e:
                        logger.warning("Profile image upload failed: %s", e)
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
                    logger.debug("joinSquare: %s", join_result)
                    try:
                        member_mid = join_result.square_chat_member.square_member_mid
                        self.client.obs.upload_obj_square_member_image(member_mid=member_mid,path_or_bytes=profileImagePath,filename="Image.jpg")
                    except Exception as e:
                        logger.warning("Profile image upload failed: %s", e)
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
                        member_mid = join_result.square_chat_member.square_member_mid
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
            already_member = (
                "[410]" in error_str
                or "既に" in error_str
                or "already" in error_str.lower()
                or "メンバー" in error_str
            )
            if already_member:
                result["status"] = "ALREADY_MEMBER"
                result["message"] = f"既に参加済み: {chat_name}"
            else:
                result["message"] = f"チャット参加失敗: {e}"
        return result
