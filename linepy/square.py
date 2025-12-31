"""
Square (OpenChat) Service for LINEPY

Provides OpenChat/Square related API endpoints.
Based on linejs SquareService implementation.
"""

from typing import Optional, Dict, List, Any


class SquareService:
    """
    Square (OpenChat) Service

    Endpoint: /SQ1
    Protocol: Compact (4)

    Example:
        client = BaseClient(...)
        client.auto_login()

        # Get joined squares (OpenChats)
        squares = client.square.get_joined_squares()

        # Send message to OpenChat
        client.square.send_message(
            square_chat_mid="c...",
            text="Hello OpenChat!"
        )
    """

    ENDPOINT = "/SQ1"
    PROTOCOL = 4

    def __init__(self, client):
        """
        Initialize Square Service.

        Args:
            client: BaseClient instance
        """
        self.client = client

    def _call(self, method: str, params: List = None) -> Any:
        """Make a Square API call"""
        from .thrift import write_thrift

        if params is None:
            params = []

        data = write_thrift(params, method, self.PROTOCOL)

        response = self.client.request.request(
            path=self.ENDPOINT,
            data=data,
            protocol=self.PROTOCOL,
        )

        # Check for error
        if isinstance(response, dict) and "error" in response:
            err = response["error"]
            from .base import LineException
            raise LineException(
                code=err.get("code", -1),
                message=err.get("message", "Unknown error"),
                metadata=err.get("metadata"),
            )

        return response

    # ========== Square Info ==========

    def get_joined_squares(
        self,
        limit: int = 100,
        continuation_token: Optional[str] = None
    ) -> Dict:
        """
        Get list of joined squares (OpenChats).

        Args:
            limit: Maximum number of results
            continuation_token: Token for pagination

        Returns:
            Dict with squares list and continuation token
        """
        # GetJoinedSquaresRequest: [[11, 2, continuationToken], [8, 3, limit]]
        request = []
        if continuation_token:
            request.append([11, 2, continuation_token])
        request.append([8, 3, limit])

        return self._call("getJoinedSquares", [[12, 1, request]])

    def get_square(self, square_mid: str) -> Dict:
        """
        Get square details.

        Args:
            square_mid: Square MID (starts with 's')

        Returns:
            Square details
        """
        # GetSquareRequest: [[11, 2, mid]]
        return self._call("getSquare", [[12, 1, [[11, 2, square_mid]]]])

    def get_square_status(self, square_mid: str) -> Dict:
        """
        Get square status.

        Args:
            square_mid: Square MID

        Returns:
            Square status
        """
        return self._call("getSquareStatus", [[12, 1, [[11, 2, square_mid]]]])

    def search_squares(
        self,
        query: str,
        limit: int = 100,
        continuation_token: Optional[str] = None
    ) -> Dict:
        """
        Search for squares.

        Args:
            query: Search query
            limit: Maximum results
            continuation_token: Pagination token

        Returns:
            Search results
        """
        # SearchSquaresRequest
        request = [
            [11, 2, query],
        ]
        if continuation_token:
            request.append([11, 4, continuation_token])
        request.append([8, 5, limit])

        return self._call("searchSquares", [[12, 1, request]])

    # ========== Square Chat ==========

    def get_square_chat(self, square_chat_mid: str) -> Dict:
        """
        Get square chat details.

        Args:
            square_chat_mid: Square chat MID (starts with 'm' or 'c')

        Returns:
            Square chat details
        """
        return self._call("getSquareChat", [[12, 1, [[11, 1, square_chat_mid]]]])

    def get_square_chat_members(
        self,
        square_chat_mid: str,
        limit: int = 100,
        continuation_token: Optional[str] = None
    ) -> Dict:
        """
        Get members of a square chat.

        Args:
            square_chat_mid: Square chat MID
            limit: Maximum results
            continuation_token: Pagination token

        Returns:
            Members list
        """
        request = [[11, 1, square_chat_mid]]
        if continuation_token:
            request.append([11, 2, continuation_token])
        request.append([8, 3, limit])

        return self._call("getSquareChatMembers", [[12, 1, request]])

    def get_joinable_square_chats(self, square_mid: str) -> Dict:
        """
        Get joinable chats in a square.

        Args:
            square_mid: Square MID

        Returns:
            Joinable chats
        """
        return self._call("getJoinableSquareChats", [[12, 1, [[11, 1, square_mid]]]])

    # ========== Messaging ==========

    def send_message(
        self,
        square_chat_mid: str,
        text: str,
        content_type: int = 0,
        content_metadata: Optional[Dict[str, str]] = None,
        related_message_id: Optional[str] = None,
    ) -> Dict:
        """
        Send a message to a square chat.

        Args:
            square_chat_mid: Square chat MID
            text: Message text
            content_type: 0=text, 1=image, etc.
            content_metadata: Optional metadata
            related_message_id: For replies

        Returns:
            Sent message info
        """
        # Build message struct
        message = [
            [11, 2, square_chat_mid],  # to
            [11, 10, text],  # text
            [8, 15, content_type],  # contentType
        ]

        if content_metadata:
            # Map<string, string>
            message.append([13, 18, [11, 11, content_metadata]])

        if related_message_id:
            message.extend([
                [11, 21, related_message_id],  # relatedMessageId
                [8, 22, 3],  # relatedMessageServiceCode = SQUARE
                [8, 24, 3],  # messageRelationType = REPLY
            ])

        # SquareMessage struct
        square_message = [
            [10, 3, 4],  # squareMessageRevision
            [12, 1, message],  # message
        ]

        # SendMessageRequest
        request = [
            [8, 1, 0],  # reqSeq
            [11, 2, square_chat_mid],  # squareChatMid
            [12, 3, square_message],  # squareMessage
        ]

        return self._call("sendMessage", [[12, 1, request]])

    def unsend_message(
        self,
        square_chat_mid: str,
        message_id: str,
        thread_mid: Optional[str] = None
    ) -> Dict:
        """
        Unsend (retract) a message.

        Args:
            square_chat_mid: Square chat MID
            message_id: Message ID to unsend
            thread_mid: Thread MID (for thread messages)

        Returns:
            Result
        """
        request = [
            [11, 2, square_chat_mid],
            [11, 3, message_id],
        ]
        if thread_mid:
            request.append([11, 4, thread_mid])

        return self._call("unsendMessage", [[12, 1, request]])

    def fetch_square_chat_events(
        self,
        square_chat_mid: str,
        sync_token: Optional[str] = None,
        limit: int = 100,
        direction: int = 1,  # 1=FORWARD, 2=BACKWARD
        thread_mid: Optional[str] = None,
    ) -> Dict:
        """
        Fetch events (messages) from a square chat.

        Args:
            square_chat_mid: Square chat MID
            sync_token: Token for incremental sync
            limit: Maximum events
            direction: 1=FORWARD, 2=BACKWARD
            thread_mid: For thread events

        Returns:
            Events and sync token
        """
        request = [[11, 1, square_chat_mid]]

        if sync_token:
            request.append([11, 2, sync_token])

        request.append([8, 3, limit])
        request.append([8, 4, direction])

        if thread_mid:
            request.append([11, 5, thread_mid])

        return self._call("fetchSquareChatEvents", [[12, 1, request]])

    def mark_as_read(
        self,
        square_chat_mid: str,
        message_id: str
    ) -> Dict:
        """
        Mark messages as read.

        Args:
            square_chat_mid: Square chat MID
            message_id: Last read message ID

        Returns:
            Result
        """
        request = [
            [11, 2, square_chat_mid],
            [11, 4, message_id],
        ]
        return self._call("markAsRead", [[12, 1, request]])

    # ========== Reactions ==========

    def react_to_message(
        self,
        square_chat_mid: str,
        message_id: str,
        reaction_type: int,  # 1=LIKE, 2=LOVE, 3=HAHA, 4=WOW, 5=SAD, 6=ANGRY
        thread_mid: Optional[str] = None
    ) -> Dict:
        """
        React to a message.

        Args:
            square_chat_mid: Square chat MID
            message_id: Message ID to react to
            reaction_type: Reaction type (1-6)
            thread_mid: For thread messages

        Returns:
            Result
        """
        request = [
            [8, 1, 0],  # reqSeq
            [11, 2, square_chat_mid],
            [11, 3, message_id],
            [8, 4, reaction_type],
        ]
        if thread_mid:
            request.append([11, 5, thread_mid])

        return self._call("reactToMessage", [[12, 1, request]])

    # ========== Join/Leave ==========

    def join_square(
        self,
        square_mid: str,
        display_name: str,
        able_to_receive_message: bool = True,
        pass_code: Optional[str] = None,
        join_message: Optional[str] = None
    ) -> Dict:
        """
        Join a square.

        Args:
            square_mid: Square MID
            display_name: Display name in the square
            able_to_receive_message: Enable notifications
            pass_code: Pass code for protected squares
            join_message: Message for approval-required squares

        Returns:
            Join result
        """
        # Member struct
        member = [
            [11, 2, square_mid],  # squareMid
            [11, 3, display_name],  # displayName
            [2, 5, able_to_receive_message],  # ableToReceiveMessage
            [10, 9, 0],  # revision
        ]

        # JoinValue struct
        join_value = []
        if pass_code:
            join_value.append([12, 2, [[11, 1, pass_code]]])  # codeValue
        if join_message:
            join_value.append([12, 1, [[11, 1, join_message]]])  # approvalValue

        request = [
            [11, 2, square_mid],  # squareMid
            [12, 3, member],  # member
        ]
        if join_value:
            request.append([12, 4, join_value])  # joinValue

        return self._call("joinSquare", [[12, 1, request]])

    def leave_square(self, square_mid: str) -> Dict:
        """
        Leave a square.

        Args:
            square_mid: Square MID

        Returns:
            Result
        """
        return self._call("leaveSquare", [[12, 1, [[11, 2, square_mid]]]])

    def join_square_chat(
        self,
        square_chat_mid: str
    ) -> Dict:
        """
        Join a square chat room.

        Args:
            square_chat_mid: Square chat MID

        Returns:
            Result
        """
        return self._call("joinSquareChat", [[12, 1, [[11, 1, square_chat_mid]]]])

    def leave_square_chat(
        self,
        square_chat_mid: str,
        say_goodbye: bool = False,
        square_mid: Optional[str] = None
    ) -> Dict:
        """
        Leave a square chat room.

        Args:
            square_chat_mid: Square chat MID
            say_goodbye: Post goodbye message
            square_mid: Square MID

        Returns:
            Result
        """
        request = [
            [11, 2, square_chat_mid],
            [2, 3, say_goodbye],
        ]
        if square_mid:
            request.append([11, 1, square_mid])

        return self._call("leaveSquareChat", [[12, 1, request]])

    # ========== My Events (Polling) ==========

    def fetch_my_events(
        self,
        subscription_id: Optional[int] = None,
        sync_token: Optional[str] = None,
        continuation_token: Optional[str] = None,
        limit: int = 100
    ) -> Dict:
        """
        Fetch events for the current user across all squares.

        Used for polling new messages.

        Args:
            subscription_id: Subscription ID
            sync_token: Sync token for incremental updates
            continuation_token: For pagination
            limit: Maximum events

        Returns:
            Events and tokens
        """
        request = []

        if subscription_id is not None:
            request.append([10, 1, subscription_id])
        if sync_token:
            request.append([11, 2, sync_token])
        if continuation_token:
            request.append([11, 3, continuation_token])

        request.append([8, 4, limit])

        return self._call("fetchMyEvents", [[12, 1, request]])

    # ========== Invitations ==========

    def find_square_by_invitation_ticket(self, ticket: str) -> Dict:
        """
        Find a square by invitation ticket.

        Args:
            ticket: Invitation ticket code

        Returns:
            Square info
        """
        return self._call("findSquareByInvitationTicket", [[12, 1, [[11, 2, ticket]]]])

    def get_invitation_ticket_url(self, square_mid: str) -> Dict:
        """
        Get invitation ticket URL for a square.

        Args:
            square_mid: Square MID

        Returns:
            Invitation URL
        """
        return self._call("getInvitationTicketUrl", [[12, 1, [[11, 2, square_mid]]]])

    def invite_into_square_chat(
        self,
        square_chat_mid: str,
        invite_mids: List[str]
    ) -> Dict:
        """
        Invite members into a square chat.

        Args:
            square_chat_mid: Square chat MID
            invite_mids: List of member MIDs to invite

        Returns:
            Result
        """
        request = [
            [11, 1, square_chat_mid],
            [15, 2, [11, invite_mids]],
        ]
        return self._call("inviteIntoSquareChat", [[12, 1, request]])

    # ========== Announcements ==========

    def get_square_chat_announcements(self, square_chat_mid: str) -> Dict:
        """
        Get announcements in a square chat.

        Args:
            square_chat_mid: Square chat MID

        Returns:
            Announcements list
        """
        return self._call("getSquareChatAnnouncements", [[12, 1, [[11, 2, square_chat_mid]]]])

    def create_square_chat_announcement(
        self,
        square_chat_mid: str,
        message_id: str,
        text: str
    ) -> Dict:
        """
        Create an announcement in a square chat.

        Args:
            square_chat_mid: Square chat MID
            message_id: Message ID to announce
            text: Announcement text

        Returns:
            Created announcement
        """
        announcement = [
            [8, 2, 0],  # type
            [12, 3, [  # contents
                [12, 1, [  # textMessageAnnouncementContents
                    [11, 1, message_id],
                    [11, 2, text],
                ]],
            ]],
        ]

        request = [
            [8, 1, 0],  # reqSeq
            [11, 2, square_chat_mid],
            [12, 3, announcement],
        ]

        return self._call("createSquareChatAnnouncement", [[12, 1, request]])

    def delete_square_chat_announcement(
        self,
        square_chat_mid: str,
        announcement_id: int
    ) -> Dict:
        """
        Delete an announcement.

        Args:
            square_chat_mid: Square chat MID
            announcement_id: Announcement ID

        Returns:
            Result
        """
        request = [
            [11, 2, square_chat_mid],
            [10, 3, announcement_id],
        ]
        return self._call("deleteSquareChatAnnouncement", [[12, 1, request]])

    # ========== Popular ==========

    def get_popular_keywords(self) -> Dict:
        """
        Get popular search keywords.

        Returns:
            Popular keywords
        """
        return self._call("getPopularKeywords", [[12, 1, []]])
