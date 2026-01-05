# -*- coding: utf-8 -*-
from linepy.models.square_structs import *
from typing import Optional, List, Dict, Any, Union
from .services.base import ServiceBase
from .models.square import *


class SquareService(ServiceBase):
    ENDPOINT = "/SQS1"

    def inviteIntoSquareChat(
        self, inviteeMids: list, squareChatMid: str
    ) -> "InviteIntoSquareChatResponse":
        """Invite into square chat."""
        METHOD_NAME = "inviteIntoSquareChat"
        params = [
            [15, 1, [11, inviteeMids]],
            [11, 2, squareChatMid],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=InviteIntoSquareChatResponse
        )

    def inviteToSquare(
        self, squareMid: str, invitees: list, squareChatMid: str
    ) -> "InviteToSquareResponse":
        """Invite to square."""
        METHOD_NAME = "inviteToSquare"
        params = [
            [11, 2, squareMid],
            [15, 3, [11, invitees]],
            [11, 4, squareChatMid],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=InviteToSquareResponse
        )

    def getJoinedSquares(
        self, continuationToken: Optional[str] = None, limit: int = 50
    ) -> "GetJoinedSquaresResponse":
        """Get joined squares."""
        METHOD_NAME = "getJoinedSquares"
        params = [
            [11, 2, continuationToken],
            [8, 3, limit],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetJoinedSquaresResponse
        )

    def markAsRead(
        self, squareChatMid: str, messageId: str, threadMid: Optional[str] = None
    ) -> "MarkAsReadResponse":
        """Mark as read for square chat."""
        METHOD_NAME = "markAsRead"
        params = [
            [11, 2, squareChatMid],
            [11, 4, messageId],
        ]
        if threadMid is not None:
            params.append([11, 5, threadMid])
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=MarkAsReadResponse
        )

    def reactToMessage(
        self,
        squareChatMid: str,
        messageId: str,
        reactionType: int = 2,
        threadMid: Optional[str] = None,
    ) -> "ReactToMessageResponse":
        """React to message for square chat message.

        - reactionType:
            ALL     = 0,
            UNDO    = 1,
            NICE    = 2,
            LOVE    = 3,
            FUN     = 4,
            AMAZING = 5,
            SAD     = 6,
            OMG     = 7,"""
        METHOD_NAME = "reactToMessage"
        params = [
            [8, 1, 0],  # reqSeq
            [11, 2, squareChatMid],
            [11, 3, messageId],
            [8, 4, reactionType],
        ]
        if threadMid is not None:
            params.append([11, 5, threadMid])
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=ReactToMessageResponse
        )

    def findSquareByInvitationTicket(
        self, invitationTicket: str
    ) -> "FindSquareByInvitationTicketResponse":
        """Find square by invitation ticket."""
        METHOD_NAME = "findSquareByInvitationTicket"
        params = [[11, 2, invitationTicket]]
        return self._call(
            METHOD_NAME,
            [[12, 1, params]],
            response_model=FindSquareByInvitationTicketResponse,
        )

    def fetchMyEvents(
        self,
        subscriptionId: Optional[int] = 0,
        syncToken: Optional[str] = None,
        continuationToken: Optional[str] = None,
        limit: int = 100,
    ) -> "FetchMyEventsResponse":
        """Fetch square events."""
        METHOD_NAME = "fetchMyEvents"
        params = [
            [10, 1, subscriptionId],
            [11, 2, syncToken],
            [8, 3, limit],
            [11, 4, continuationToken],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=FetchMyEventsResponse
        )

    def fetchSquareChatEvents(
        self,
        squareChatMid: str,
        syncToken: Optional[str] = None,
        continuationToken: Optional[str] = None,
        subscriptionId: int = 0,
        limit: int = 100,
        threadMid: Optional[str] = None,
        fetchType: int = 1,
    ) -> "FetchSquareChatEventsResponse":
        """Fetch square chat events."""
        METHOD_NAME = "fetchSquareChatEvents"
        params = [
            [10, 1, subscriptionId],
            [11, 2, squareChatMid],
            [11, 3, syncToken],
            [8, 4, limit],
            [8, 5, 1],  # direction
            [8, 6, 1],  # inclusive
            [11, 7, continuationToken],
            [8, 8, fetchType],
            [11, 9, threadMid],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=FetchSquareChatEventsResponse
        )

    def sendSquareMessage(
        self,
        squareChatMid: str,
        text: str,
        contentType: int = 0,
        contentMetadata: dict = {},
        relatedMessageId: Optional[str] = None,
    ) -> "SendSquareMessageResponse":
        """Send message for square chat (OLD)."""
        METHOD_NAME = "sendMessage"
        message = [
            # [11, 1, _from],
            [11, 2, squareChatMid],
            [11, 10, text],
            [8, 15, contentType],  # contentType
            [13, 18, [11, 11, contentMetadata]],
        ]
        if relatedMessageId is not None:
            message.append([11, 21, relatedMessageId])
            message.append(
                [
                    8,
                    22,
                    3,
                ]
            )
            message.append([8, 24, 2])
        params = [
            [8, 1, 0],
            [11, 2, squareChatMid],
            [
                12,
                3,
                [
                    [12, 1, message],
                    [8, 3, 4],
                ],
            ],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=SendMessageResponse
        )

    def sendSquareTextMessage(
        self,
        squareChatMid: str,
        text: str,
        contentMetadata: dict = {},
        relatedMessageId: Optional[str] = None,
    ) -> "SendSquareTextMessageResponse":
        return self.sendSquareMessage(
            squareChatMid, text, 0, contentMetadata, relatedMessageId
        )

    def getSquare(self, squareMid: str) -> "GetSquareResponse":
        """Get square."""
        METHOD_NAME = "getSquare"
        params = [
            [11, 2, squareMid],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetSquareResponse
        )

    def getJoinableSquareChats(
        self, squareMid: str, continuationToken: Optional[str] = None, limit: int = 100
    ) -> "GetJoinableSquareChatsResponse":
        """Get joinable square chats."""
        METHOD_NAME = "getJoinableSquareChats"
        params = [[11, 1, squareMid], [11, 10, continuationToken], [8, 11, limit]]
        return self._call(
            METHOD_NAME,
            [[12, 1, params]],
            response_model=GetJoinableSquareChatsResponse,
        )

    def createSquare(
        self,
        name: str,
        displayName: str,
        profileImageObsHash: str = "0h6tJf0hQsaVt3H0eLAsAWDFheczgHd3wTCTx2eApNKSoefHNVGRdwfgxbdgUMLi8MSngnPFMeNmpbLi8MSngnPFMeNmpbLi8MSngnOA",
        desc: str = "test with CHRLINE API",
        searchable: bool = True,
        SquareJoinMethodType: int = 0,
    ) -> "CreateSquareResponse":
        """Create square.

        - SquareJoinMethodType
            NONE(0),
            APPROVAL(1),
            CODE(2);"""
        METHOD_NAME = "createSquare"
        params = [
            [8, 2, 0],
            [
                12,
                2,
                [
                    [11, 2, name],
                    [11, 4, profileImageObsHash],
                    [11, 5, desc],
                    [2, 6, searchable],
                    [8, 7, 1],  # type
                    [8, 8, 1],  # categoryId
                    [10, 10, 0],  # revision
                    [2, 11, True],  # ableToUseInvitationTicket
                    [12, 14, [[8, 1, SquareJoinMethodType]]],
                    [2, 15, False],  # adultOnly
                    [15, 16, [11, []]],  # svcTags
                ],
            ],
            [
                12,
                3,
                [
                    [11, 3, displayName],
                    # [11, 4, profileImageObsHash],
                    [2, 5, True],  # ableToReceiveMessage
                    [10, 9, 0],  # revision
                ],
            ],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=CreateSquareResponse
        )

    def getSquareChatAnnouncements(
        self, squareMid: str
    ) -> "GetSquareChatAnnouncementsResponse":
        """Get square chat announcements."""
        METHOD_NAME = "getSquareChatAnnouncements"
        params = [
            [11, 2, squareMid],
        ]
        return self._call(
            METHOD_NAME,
            [[12, 1, params]],
            response_model=GetSquareChatAnnouncementsResponse,
        )

    def leaveSquareChat(self) -> "LeaveSquareChatResponse":
        """AUTO_GENERATED_CODE! DONT_USE_THIS_FUNC!!"""
        raise Exception("leaveSquareChat is not implemented")
        params = []
        sqrd = self.generateDummyProtocol(
            "leaveSquareChat", params, self.SquareService_REQ_TYPE
        )
        return self.postPackDataAndGetUnpackRespData(
            self.SquareService_API_PATH,
            sqrd,
            self.SquareService_RES_TYPE,
            baseException=SquareService.SQUARE_EXCEPTION,
        )

    def getSquareChatMember(
        self, squareMemberMid: str, squareChatMid: str
    ) -> "GetSquareChatMemberResponse":
        """Get square chat member."""
        METHOD_NAME = "getSquareChatMember"
        params = [
            [11, 2, squareMemberMid],
            [11, 3, squareChatMid],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetSquareChatMemberResponse
        )

    def searchSquares(
        self, query: str, continuationToken: str, limit: int
    ) -> "SearchSquaresResponse":
        """Search squares."""
        METHOD_NAME = "searchSquares"
        params = [
            [11, 2, query],
            [11, 3, continuationToken],
            [8, 4, limit],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=SearchSquaresResponse
        )

    def updateSquareFeatureSet(
        self,
        updateAttributes: List[int],
        squareMid: str,
        revision: int,
        creatingSecretSquareChat: Optional[int] = None,
        invitingIntoOpenSquareChat: Optional[int] = None,
        creatingSquareChat: Optional[int] = None,
        readonlyDefaultChat: Optional[int] = None,
        showingAdvertisement: Optional[int] = None,
        delegateJoinToPlug: Optional[int] = None,
        delegateKickOutToPlug: Optional[int] = None,
        disableUpdateJoinMethod: Optional[int] = None,
        disableTransferAdmin: Optional[int] = None,
        creatingLiveTalk: Optional[int] = None,
        disableUpdateSearchable: Optional[int] = None,
        summarizingMessages: Optional[int] = None,
        creatingSquareThread: Optional[int] = None,
        enableSquareThread: Optional[int] = None,
    ) -> "UpdateSquareFeatureSetResponse":
        """Update square feature set.

        - updateAttributes:
            CREATING_SECRET_SQUARE_CHAT(1),
            INVITING_INTO_OPEN_SQUARE_CHAT(2),
            CREATING_SQUARE_CHAT(3),
            READONLY_DEFAULT_CHAT(4),
            SHOWING_ADVERTISEMENT(5),
            DELEGATE_JOIN_TO_PLUG(6),
            DELEGATE_KICK_OUT_TO_PLUG(7),
            DISABLE_UPDATE_JOIN_METHOD(8),
            DISABLE_TRANSFER_ADMIN(9),
            CREATING_LIVE_TALK(10),
            DISABLE_UPDATE_SEARCHABLE(11),
            SUMMARIZING_MESSAGES(12),
            CREATING_SQUARE_THREAD(13),
            ENABLE_SQUARE_THREAD(14);"""
        METHOD_NAME = "updateSquareFeatureSet"
        SquareFeatureSet = [
            [11, 1, squareMid],
            [10, 2, revision],
        ]
        features = {
            11: creatingSecretSquareChat,
            12: invitingIntoOpenSquareChat,
            13: creatingSquareChat,
            14: readonlyDefaultChat,
            15: showingAdvertisement,
            16: delegateJoinToPlug,
            17: delegateKickOutToPlug,
            18: disableUpdateJoinMethod,
            19: disableTransferAdmin,
            20: creatingLiveTalk,
            21: disableUpdateSearchable,
            22: summarizingMessages,
            23: creatingSquareThread,
            24: enableSquareThread,
        }
        for fid, fbt in features.items():
            if fbt is not None:
                squareFeature = [
                    [8, 1, 1],
                    [8, 2, fbt],
                ]
                SquareFeatureSet.append([12, fid, squareFeature])
        params = [
            [14, 2, [8, updateAttributes]],
            [12, 3, SquareFeatureSet],
        ]
        return self._call(
            METHOD_NAME,
            [[12, 1, params]],
            response_model=UpdateSquareFeatureSetResponse,
        )

    def joinSquare(
        self,
        squareMid: Any,
        displayName: Any,
        ableToReceiveMessage: bool = False,
        passCode: Optional[str] = None,
        squareChatMid: Optional[str] = None,
        claimAdult: Optional[int] = None,
    ) -> "JoinSquareResponse":
        METHOD_NAME = "joinSquare"
        member = [
            [11, 2, squareMid],
            [11, 3, displayName],
            [2, 5, ableToReceiveMessage],
        ]
        params = [
            [11, 2, squareMid],
            [12, 3, member],
        ]
        if squareChatMid is not None:
            params.append([11, 4, squareChatMid])
        if passCode is not None:
            codeValue = [
                [11, 1, passCode],
            ]
            squareJoinMethodValue = [
                [12, 2, codeValue],
            ]
            params.append([12, 5, squareJoinMethodValue])
        if claimAdult is not None:
            params.append([8, 6, claimAdult])
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=JoinSquareResponse
        )

    def getSquarePopularKeywords(self) -> "GetSquarePopularKeywordsResponse":
        """Get popular keywords."""
        METHOD_NAME = "getPopularKeywords"
        params = []
        return self._call(
            METHOD_NAME,
            [[12, 1, params]],
            response_model=GetSquarePopularKeywordsResponse,
        )

    def reportSquareMessage(
        self,
        squareMid: str,
        squareChatMid: str,
        squareMessageId: str,
        reportType: int,
        otherReason: Optional[str] = None,
        threadMid: Optional[str] = None,
    ) -> "ReportSquareMessageResponse":
        """Report square message."""
        METHOD_NAME = "reportSquareMessage"
        params = [
            [11, 2, squareMid],
            [11, 3, squareChatMid],
            [11, 4, squareMessageId],
            [8, 5, reportType],
        ]
        if otherReason is not None:
            params.append([11, 6, otherReason])
        if threadMid is not None:
            params.append([11, 7, threadMid])
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=ReportSquareMessageResponse
        )

    def updateSquareMemberRelation(
        self,
        squareMid: str,
        targetSquareMemberMid: str,
        updatedAttrs: List[int],
        state: int,
        revision: int,
    ) -> "UpdateSquareMemberRelationResponse":
        """Update square member relation."""
        METHOD_NAME = "updateSquareMemberRelation"
        relation = [
            [8, 1, state],
            [10, 2, revision],
        ]
        params = [
            [11, 2, squareMid],
            [11, 3, targetSquareMemberMid],
            [14, 4, [8, updatedAttrs]],
            [12, 5, relation],
        ]
        return self._call(
            METHOD_NAME,
            [[12, 1, params]],
            response_model=UpdateSquareMemberRelationResponse,
        )

    def leaveSquare(self, squareMid: str) -> "LeaveSquareResponse":
        """Leave square."""
        METHOD_NAME = "leaveSquare"
        params = [
            [11, 2, squareMid],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=LeaveSquareResponse
        )

    def getSquareMemberRelations(
        self, state: int, continuationToken: Optional[str] = None, limit: int = 20
    ) -> "GetSquareMemberRelationsResponse":
        """Get square member relations."""
        METHOD_NAME = "getSquareMemberRelations"
        params = [[8, 2, state], [11, 3, continuationToken], [8, 4, limit]]
        return self._call(
            METHOD_NAME,
            [[12, 1, params]],
            response_model=GetSquareMemberRelationsResponse,
        )

    def removeSquareSubscriptions(
        self, subscriptionIds: list = []
    ) -> "RemoveSquareSubscriptionsResponse":
        METHOD_NAME = "removeSquareSubscriptions"
        params = [
            [
                12,
                1,
                [
                    [15, 2, [10, subscriptionIds]],
                ],
            ]
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=RemoveSubscriptionsResponse
        )

    def getSquareMembers(self, mids: List[str]) -> "GetSquareMembersResponse":
        """Get square members."""
        METHOD_NAME = "getSquareMembers"
        params = [
            [14, 2, [11, mids]],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetSquareMembersResponse
        )

    def updateSquareChat(
        self,
        updatedAttrs: List[int],
        squareChatMid: str,
        squareMid: str,
        _type: int,
        name: str,
        chatImageObsHash: str,
        squareChatRevision: int,
        maxMemberCount: int,
        showJoinMessage: bool,
        showLeaveMessage: bool,
        showKickoutMessage: bool,
        state: int,
        invitationUrl: Optional[str] = None,
        ableToSearchMessage: Optional[int] = None,
    ) -> "UpdateSquareChatResponse":
        """Update square chat."""
        METHOD_NAME = "updateSquareChat"
        messageVisibility = [
            [2, 1, showJoinMessage],
            [2, 2, showLeaveMessage],
            [2, 3, showKickoutMessage],
        ]
        squareChat = [
            [11, 1, squareChatMid],
            [11, 2, squareMid],
            [8, 3, _type],
            [11, 4, name],
            [11, 5, chatImageObsHash],
            [10, 6, squareChatRevision],
            [8, 7, maxMemberCount],
            [8, 8, state],
        ]
        if invitationUrl is not None:
            squareChat.append([11, 9, invitationUrl])
        if messageVisibility is not None:
            squareChat.append([12, 10, messageVisibility])
        if ableToSearchMessage is not None:
            squareChat.append([8, 11, ableToSearchMessage])
        params = [
            [14, 2, [8, updatedAttrs]],
            [12, 3, squareChat],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=UpdateSquareChatResponse
        )

    def getSquareMessageReactions(
        self,
        squareChatMid: str,
        messageId: str,
        _type: int,
        continuationToken: str,
        limit: int,
        threadMid: Optional[str] = None,
    ) -> "GetSquareMessageReactionsResponse":
        """Get square message reactions."""
        METHOD_NAME = "getSquareMessageReactions"
        params = [
            [11, 1, squareChatMid],
            [11, 2, messageId],
            [8, 3, _type],
            [11, 4, continuationToken],
            [8, 5, limit],
            [11, 6, threadMid],
        ]
        return self._call(METHOD_NAME, [[12, 1, params]], response_model=None)

    def destroySquareMessage(
        self, squareChatMid: str, messageId: str, threadMid: Optional[str] = None
    ) -> DestroyMessageResponse:
        """Destroy message for square."""
        METHOD_NAME = "destroyMessage"
        params = [[11, 2, squareChatMid], [11, 4, messageId], [11, 5, threadMid]]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=DestroyMessageResponse
        )

    def reportSquareChat(
        self,
        squareMid: str,
        squareChatMid: str,
        reportType: int,
        otherReason: Optional[str] = None,
    ) -> "ReportSquareChatResponse":
        """Report square chat."""
        METHOD_NAME = "reportSquareChat"
        params = [
            [11, 2, squareMid],
            [11, 3, squareChatMid],
            [8, 5, reportType],
        ]
        if otherReason is not None:
            params.append([11, 6, otherReason])
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=ReportSquareChatResponse
        )

    def unsendSquareMessage(
        self, squareChatMid: str, messageId: str
    ) -> "UnsendSquareMessageResponse":
        """Unsend message for square.

        2022/09/19: Added."""
        METHOD_NAME = "unsendMessage"
        params = SquareServiceStruct.UnsendMessageRequest(squareChatMid, messageId)
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=UnsendMessageResponse
        )

    def deleteSquareChatAnnouncement(
        self, squareChatMid: str, announcementSeq: int
    ) -> "DeleteSquareChatAnnouncementResponse":
        """Delete square chat announcement."""
        METHOD_NAME = "deleteSquareChatAnnouncement"
        params = [[11, 2, squareChatMid], [10, 3, announcementSeq]]
        return self._call(
            METHOD_NAME,
            [[12, 1, params]],
            response_model=DeleteSquareChatAnnouncementResponse,
        )

    def createSquareChat(
        self,
        squareChatMid: str,
        name: str,
        chatImageObsHash: str,
        squareChatType: int = 1,
        maxMemberCount: int = 5000,
        ableToSearchMessage: int = 1,
        squareMemberMids: list = [],
    ) -> "CreateSquareChatResponse":
        """- SquareChatType:
            OPEN(1),
            SECRET(2),
            ONE_ON_ONE(3),
            SQUARE_DEFAULT(4);
        - ableToSearchMessage:
            NONE(0),
            OFF(1),
            ON(2);"""
        METHOD_NAME = "createSquareChat"
        params = [
            [
                12,
                1,
                [
                    [8, 1, 0],
                    [
                        12,
                        2,
                        [
                            [11, 1, squareChatMid],
                            [8, 3, squareChatType],
                            [11, 4, name],
                            [11, 5, chatImageObsHash],
                            [8, 7, maxMemberCount],
                            [8, 11, ableToSearchMessage],
                        ],
                    ],
                    [15, 3, [11, squareMemberMids]],
                ],
            ]
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=CreateSquareChatResponse
        )

    def deleteSquareChat(
        self, squareChatMid: str, revision: int
    ) -> "DeleteSquareChatResponse":
        """Delete square chat."""
        METHOD_NAME = "deleteSquareChat"
        params = [[11, 2, squareChatMid], [10, 3, revision]]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=DeleteSquareChatResponse
        )

    def getSquareChatMembers(
        self,
        squareChatMid: str,
        continuationToken: Optional[str] = None,
        limit: int = 200,
    ) -> "GetSquareChatMembersResponse":
        METHOD_NAME = "getSquareChatMembers"
        GetSquareChatMembersRequest = [[11, 1, squareChatMid], [8, 3, limit]]
        if continuationToken is not None:
            GetSquareChatMembersRequest.append([11, 2, continuationToken])
        params = [[12, 1, GetSquareChatMembersRequest]]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetSquareChatMembersResponse
        )

    def getSquareFeatureSet(self, squareMid: str) -> "GetSquareFeatureSetResponse":
        """Get square feature set."""
        METHOD_NAME = "getSquareFeatureSet"
        params = [
            [11, 2, squareMid],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetSquareFeatureSetResponse
        )

    def updateSquareAuthority(
        self,
        updateAttributes: List[int],
        squareMid: str,
        updateSquareProfile: int,
        inviteNewMember: int,
        approveJoinRequest: int,
        createPost: int,
        createOpenSquareChat: int,
        deleteSquareChatOrPost: int,
        removeSquareMember: int,
        grantRole: int,
        enableInvitationTicket: int,
        revision: int,
        createSquareChatAnnouncement: int,
        updateMaxChatMemberCount: Optional[int] = None,
        useReadonlyDefaultChat: Optional[int] = None,
    ) -> "UpdateSquareAuthorityResponse":
        """Update square authority."""
        METHOD_NAME = "updateSquareAuthority"
        authority = [
            [11, 1, squareMid],
            [8, 2, updateSquareProfile],
            [8, 3, inviteNewMember],
            [8, 4, approveJoinRequest],
            [8, 5, createPost],
            [8, 6, createOpenSquareChat],
            [8, 7, deleteSquareChatOrPost],
            [8, 8, removeSquareMember],
            [8, 9, grantRole],
            [8, 10, enableInvitationTicket],
            [10, 11, revision],
            [8, 12, createSquareChatAnnouncement],
        ]
        if updateMaxChatMemberCount is not None:
            authority.append([8, 13, updateMaxChatMemberCount])
        if useReadonlyDefaultChat is not None:
            authority.append([8, 14, useReadonlyDefaultChat])
        params = [
            [14, 2, [8, updateAttributes]],
            [12, 3, authority],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=UpdateSquareAuthorityResponse
        )

    def rejectSquareMembers(
        self, squareMid: str, requestedMemberMids: List[str]
    ) -> "RejectSquareMembersResponse":
        """Reject square members."""
        METHOD_NAME = "rejectSquareMembers"
        params = [[11, 2, squareMid], [15, 3, [11, requestedMemberMids]]]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=RejectSquareMembersResponse
        )

    def deleteSquare(self, mid: str, revision: int) -> "DeleteSquareResponse":
        """Delete square."""
        METHOD_NAME = "deleteSquare"
        params = [[11, 2, mid], [10, 3, revision]]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=DeleteSquareResponse
        )

    def reportSquare(
        self, squareMid: str, reportType: int, otherReason: Optional[str] = None
    ) -> "ReportSquareResponse":
        """Report square."""
        METHOD_NAME = "reportSquare"
        params = [
            [11, 2, squareMid],
            [8, 3, reportType],
        ]
        if otherReason is not None:
            params.append([11, 4, otherReason])
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=ReportSquareResponse
        )

    def getSquareInvitationTicketUrl(
        self, mid: str
    ) -> "GetSquareInvitationTicketUrlResponse":
        """Get square invitation ticket url"""
        METHOD_NAME = "getInvitationTicketUrl"
        params = [
            [11, 2, mid],
        ]
        return self._call(
            METHOD_NAME,
            [[12, 1, params]],
            response_model=GetInvitationTicketUrlResponse,
        )

    def updateSquareChatMember(
        self,
        squareMemberMid: str,
        squareChatMid: str,
        notificationForMessage: bool = True,
        notificationForNewMember: bool = True,
        updatedAttrs: List[int] = [6],
    ) -> "UpdateSquareChatMemberResponse":
        """Update square chat member.

        - SquareChatMemberAttribute:
            MEMBERSHIP_STATE(4),
            NOTIFICATION_MESSAGE(6),
            NOTIFICATION_NEW_MEMBER(7);"""
        METHOD_NAME = "updateSquareChatMember"
        chatMember = [
            [11, 1, squareMemberMid],
            [11, 2, squareChatMid],
            [2, 5, notificationForMessage],
            [2, 6, notificationForNewMember],
        ]
        params = [
            [14, 2, [8, updatedAttrs]],
            [12, 3, chatMember],
        ]
        return self._call(
            METHOD_NAME,
            [[12, 1, params]],
            response_model=UpdateSquareChatMemberResponse,
        )

    def updateSquareMember(
        self,
        updatedAttrs: list,
        updatedPreferenceAttrs: list,
        squareMemberMid: str,
        squareMid: str,
        revision: int,
        displayName: Optional[str] = None,
        membershipState: Optional[int] = None,
        role: Optional[int] = None,
        profileImageObsHash: Optional[str] = None,
    ) -> "UpdateSquareMemberResponse":
        """Update square member.

        SquareMemberAttribute:
            DISPLAY_NAME(1),
            PROFILE_IMAGE(2),
            ABLE_TO_RECEIVE_MESSAGE(3),
            MEMBERSHIP_STATE(5),
            ROLE(6),
            PREFERENCE(7);
        SquareMembershipState:
            JOIN_REQUESTED(1),
            JOINED(2),
            REJECTED(3),
            LEFT(4),
            KICK_OUT(5),
            BANNED(6),
            DELETED(7);"""
        METHOD_NAME = "updateSquareMember"
        squareMember = [[11, 1, squareMemberMid], [11, 2, squareMid]]
        if 1 in updatedAttrs:
            if displayName is None:
                raise ValueError("displayName is None")
            squareMember.append([11, 3, displayName])
        if 2 in updatedAttrs:
            if profileImageObsHash is None:
                raise ValueError("profileImageObsHash is None")
            squareMember.append([11, 4, profileImageObsHash])
        if 5 in updatedAttrs:
            if membershipState is None:
                raise ValueError("membershipState is None")
            squareMember.append([8, 7, membershipState])
        if 6 in updatedAttrs:
            if role is None:
                raise ValueError("role is None")
            squareMember.append([8, 8, role])
        squareMember.append([10, 9, revision])
        params = [
            [14, 2, [8, updatedAttrs]],
            [14, 3, [8, updatedPreferenceAttrs]],
            [12, 4, squareMember],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=UpdateSquareMemberResponse
        )

    def deleteOtherFromSquare(
        self, sid: str, pid: str
    ) -> "DeleteOtherFromSquareResponse":
        """Kick out member for square."""
        UPDATE_PREF_ATTRS = []
        UPDATE_ATTRS = [5]
        MEMBERSHIP_STATE = 5
        getSquareMemberResp = self.getSquareMember(pid)
        squareMember = self.client.checkAndGetValue(
            getSquareMemberResp, "squareMember", 1
        )
        squareMemberRevision = self.client.checkAndGetValue(squareMember, "revision", 9)
        if isinstance(squareMemberRevision, int):
            revision = squareMemberRevision
            return self.updateSquareMember(
                UPDATE_ATTRS,
                UPDATE_PREF_ATTRS,
                pid,
                sid,
                revision,
                membershipState=MEMBERSHIP_STATE,
            )
        raise ValueError(
            f"squareMemberRevision is not a number: {squareMemberRevision}"
        )

    def updateProfileImage(
        self, squareMemberMid: str, profileImageObsHash: str
    ) -> "UpdateSquareMemberResponse":
        """Update profile image."""
        fresh_member_resp = self.getSquareMember(squareMemberMid)
        squareMid = fresh_member_resp.squareMember.squareMemberMid
        current_revision = fresh_member_resp.squareMember.revision

        updated_attrs = [2]  # PROFILE_IMAGE
        return self.updateSquareMember(
            updated_attrs,
            [],
            squareMemberMid,
            squareMid,
            revision=current_revision,
            profileImageObsHash=profileImageObsHash,
        )

    def updateSquare(
        self,
        updatedAttrs: List[int],
        mid: str,
        name: str,
        welcomeMessage: str,
        profileImageObsHash: str,
        desc: str,
        searchable: bool,
        _type: int,
        categoryId: int,
        invitationURL: str,
        revision: int,
        ableToUseInvitationTicket: bool,
        state: int,
        joinMethodType: int,
        emblems: Optional[List[int]] = None,
        joinMethodMessage: Optional[str] = None,
        joinMethodCode: Optional[str] = None,
        adultOnly: Optional[int] = None,
        svcTags: Optional[List[str]] = None,
        createdAt: Optional[int] = None,
    ) -> "UpdateSquareResponse":
        """Update square."""
        METHOD_NAME = "updateSquare"
        approvalValue = [
            [11, 1, joinMethodMessage],
        ]
        codeValue = [
            [11, 1, joinMethodCode],
        ]
        joinMethodValue = [
            [12, 1, approvalValue],
            [12, 2, codeValue],
        ]
        joinMethod = [
            [8, 1, joinMethodType],
            [12, 2, joinMethodValue],
        ]
        square = [
            [11, 1, mid],
            [11, 2, name],
            [11, 3, welcomeMessage],
            [11, 4, profileImageObsHash],
            [11, 5, desc],
            [2, 6, searchable],
            [8, 7, _type],
            [8, 8, categoryId],
            [11, 9, invitationURL],
            [10, 10, revision],
            [2, 11, ableToUseInvitationTicket],
            [8, 12, state],
            [12, 14, joinMethod],
        ]
        if emblems is not None:
            square.append([15, 13, [8, emblems]])
        if adultOnly is not None:
            square.append([8, 15, adultOnly])
        if svcTags is not None:
            square.append([15, 16, [11, svcTags]])
        if createdAt is not None:
            square.append([10, 17, createdAt])
        params = [
            [14, 2, [11, updatedAttrs]],
            [12, 3, square],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=UpdateSquareResponse
        )

    def getSquareAuthorities(
        self, squareMids: List[str]
    ) -> "GetSquareAuthoritiesResponse":
        """Get square authorities."""
        METHOD_NAME = "getSquareAuthorities"
        params = [[14, 2, [11, squareMids]]]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetSquareAuthoritiesResponse
        )

    def updateSquareMembers(self) -> "UpdateSquareMembersResponse":
        """AUTO_GENERATED_CODE! DONT_USE_THIS_FUNC!!"""
        raise Exception("updateSquareMembers is not implemented")
        params = []
        sqrd = self.generateDummyProtocol(
            "updateSquareMembers", params, self.SquareService_REQ_TYPE
        )
        return self.postPackDataAndGetUnpackRespData(
            self.SquareService_API_PATH,
            sqrd,
            self.SquareService_RES_TYPE,
            baseException=SquareService.SQUARE_EXCEPTION,
        )

    def getSquareChatStatus(self, squareChatMid: str) -> "GetSquareChatStatusResponse":
        """Get square chat status."""
        METHOD_NAME = "getSquareChatStatus"
        params = [[11, 2, squareChatMid]]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetSquareChatStatusResponse
        )

    def approveSquareMembers(self) -> "ApproveSquareMembersResponse":
        """AUTO_GENERATED_CODE! DONT_USE_THIS_FUNC!!"""
        raise Exception("approveSquareMembers is not implemented")
        params = []
        sqrd = self.generateDummyProtocol(
            "approveSquareMembers", params, self.SquareService_REQ_TYPE
        )
        return self.postPackDataAndGetUnpackRespData(
            self.SquareService_API_PATH,
            sqrd,
            self.SquareService_RES_TYPE,
            baseException=SquareService.SQUARE_EXCEPTION,
        )

    def getSquareStatus(self, squareMid: str) -> "GetSquareStatusResponse":
        """Get square status."""
        METHOD_NAME = "getSquareStatus"
        params = [
            [11, 2, squareMid],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetSquareStatusResponse
        )

    def searchSquareMembers(
        self,
        squareMid: str,
        membershipState: int,
        includingMe: bool,
        excludeBlockedMembers: bool,
        continuationToken: str,
        limit: int = 20,
        memberRoles: Optional[List[int]] = None,
        displayName: Optional[str] = None,
        ableToReceiveMessage: Optional[int] = None,
        ableToReceiveFriendRequest: Optional[int] = None,
        chatMidToExcludeMembers: Optional[str] = None,
        includingMeOnlyMatch: Optional[bool] = None,
    ) -> "SearchSquareMembersResponse":
        """Search square members."""
        METHOD_NAME = "searchSquareMembers"
        searchOption = [
            [8, 1, membershipState],
            [2, 7, includingMe],
            [2, 8, excludeBlockedMembers],
        ]
        if memberRoles is not None:
            searchOption.append([14, 2, [8, memberRoles]])
        if ableToReceiveMessage is not None:
            searchOption.append([11, 3, displayName])
        if ableToReceiveMessage is not None:
            searchOption.append([8, 4, ableToReceiveMessage])
        if ableToReceiveFriendRequest is not None:
            searchOption.append([8, 5, ableToReceiveFriendRequest])
        if chatMidToExcludeMembers is not None:
            searchOption.append([11, 6, chatMidToExcludeMembers])
        if includingMeOnlyMatch is not None:
            searchOption.append([2, 9, includingMeOnlyMatch])
        params = [
            [11, 2, squareMid],
            [12, 3, searchOption],
            [11, 4, continuationToken],
            [8, 5, limit],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=SearchSquareMembersResponse
        )

    def checkSquareJoinCode(
        self, squareMid: str, code: str
    ) -> "CheckSquareJoinCodeResponse":
        METHOD_NAME = "checkJoinCode"
        params = [
            [
                12,
                1,
                [
                    [11, 2, squareMid],
                    [11, 3, code],
                ],
            ]
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=CheckJoinCodeResponse
        )

    def createSquareChatAnnouncement(
        self,
        squareChatMid: str,
        messageId: str,
        text: str,
        senderSquareMemberMid: str,
        createdAt: int,
        announcementType: int = 0,
    ) -> "CreateSquareChatAnnouncementResponse":
        """- SquareChatAnnouncementType:
        TEXT_MESSAGE(0);"""
        METHOD_NAME = "createSquareChatAnnouncement"
        params = [
            [
                12,
                1,
                [
                    [8, 1, 0],
                    [11, 2, squareChatMid],
                    [
                        12,
                        3,
                        [
                            [8, 2, announcementType],
                            [
                                12,
                                3,
                                [
                                    [
                                        12,
                                        1,
                                        [
                                            [11, 1, messageId],
                                            [11, 2, text],
                                            [11, 3, senderSquareMemberMid],
                                            [10, 4, createdAt],
                                        ],
                                    ]
                                ],
                            ],
                        ],
                    ],
                ],
            ]
        ]
        return self._call(
            METHOD_NAME,
            [[12, 1, params]],
            response_model=CreateSquareChatAnnouncementResponse,
        )

    def getSquareAuthority(self, squareMid: str) -> "GetSquareAuthorityResponse":
        """Get square authority."""
        METHOD_NAME = "getSquareAuthority"
        params = [[11, 1, squareMid]]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetSquareAuthorityResponse
        )

    def getSquareChat(self, squareChatMid: str) -> "GetSquareChatResponse":
        """Get square chat."""
        METHOD_NAME = "getSquareChat"
        params = [[11, 1, squareChatMid]]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetSquareChatResponse
        )

    def refreshSquareSubscriptions(
        self, subscriptions: List[int]
    ) -> "RefreshSquareSubscriptionsResponse":
        """Refresh subscriptions."""
        METHOD_NAME = "refreshSubscriptions"
        params = [
            [15, 2, [10, subscriptions]],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=RefreshSubscriptionsResponse
        )

    def getJoinedSquareChats(
        self, continuationToken: str, limit: int
    ) -> "GetJoinedSquareChatsResponse":
        """Get joined square chats."""
        METHOD_NAME = "getJoinedSquareChats"
        params = [[11, 2, continuationToken], [8, 3, limit]]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetJoinedSquareChatsResponse
        )

    def joinSquareChat(self, squareChatMid: str) -> "JoinSquareChatResponse":
        """Join square chat."""
        METHOD_NAME = "joinSquareChat"
        params = [
            [11, 1, squareChatMid],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=JoinSquareChatResponse
        )

    def findSquareByEmid(self, emid: str) -> "FindSquareByEmidResponse":
        """Find square by emid."""
        METHOD_NAME = "findSquareByEmid"
        params = [
            [11, 1, emid],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=FindSquareByEmidResponse
        )

    def getSquareMemberRelation(
        self, squareMid: str, targetSquareMemberMid: str
    ) -> "GetSquareMemberRelationResponse":
        """Get square member relation."""
        METHOD_NAME = "getSquareMemberRelation"
        params = [
            [11, 2, squareMid],
            [11, 3, targetSquareMemberMid],
        ]
        return self._call(
            METHOD_NAME,
            [[12, 1, params]],
            response_model=GetSquareMemberRelationResponse,
        )

    def getSquareMember(self, squareMemberMid: str) -> "GetSquareMemberResponse":
        """Get square member."""
        METHOD_NAME = "getSquareMember"
        params = [
            [11, 2, squareMemberMid],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetSquareMemberResponse
        )

    def destroySquareMessages(
        self, squareChatMid: str, messageIds: list, threadMid: Optional[str] = None
    ) -> "DestroySquareMessagesResponse":
        """Destroy messages for Square."""
        METHOD_NAME = "destroyMessages"
        params = [
            [11, 2, squareChatMid],
            [14, 4, [11, messageIds]],
            [11, 5, threadMid],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=DestroyMessagesResponse
        )

    def getSquareCategories(self) -> "GetSquareCategoriesResponse":
        """Get categories"""
        METHOD_NAME = "getCategories"
        params = []
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetSquareCategoriesResponse
        )

    def reportSquareMember(
        self,
        squareMemberMid: str,
        reportType: int,
        otherReason: str,
        squareChatMid: str,
        threadMid: str,
    ) -> "ReportSquareMemberResponse":
        """Report square member"""
        METHOD_NAME = "reportSquareMember"
        params = [
            [11, 2, squareMemberMid],
            [8, 3, reportType],
        ]
        if otherReason is not None:
            params.append([11, 4, otherReason])
        if squareChatMid is not None:
            params.append([11, 5, squareChatMid])
        if threadMid is not None:
            params.append([11, 6, threadMid])
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=ReportSquareMemberResponse
        )

    def getSquareNoteStatus(self, squareMid: str) -> "GetSquareNoteStatusResponse":
        """Get note status."""
        METHOD_NAME = "getNoteStatus"
        params = [
            [11, 2, squareMid],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetNoteStatusResponse
        )

    def searchSquareChatMembers(
        self,
        squareChatMid: str,
        displayName: str,
        continuationToken: Optional[str] = None,
        limit: int = 20,
        includingMe: bool = True,
    ) -> "SearchSquareChatMembersResponse":
        METHOD_NAME = "searchSquareChatMembers"
        searchOption = [[11, 1, displayName], [2, 2, includingMe]]
        params = [
            [11, 1, squareChatMid],
            [12, 2, searchOption],
            [8, 4, limit],
        ]
        if continuationToken is not None:
            params.append([11, 3, continuationToken])
        return self._call(
            METHOD_NAME,
            [[12, 1, params]],
            response_model=SearchSquareChatMembersResponse,
        )

    def getSquareChatFeatureSet(
        self, squareChatMid: str
    ) -> "GetSquareChatFeatureSetResponse":
        """Get square chat feature set."""
        METHOD_NAME = "getSquareChatFeatureSet"
        params = [
            [11, 2, squareChatMid],
        ]
        return self._call(
            METHOD_NAME,
            [[12, 1, params]],
            response_model=GetSquareChatFeatureSetResponse,
        )

    def getSquareEmid(self, squareMid: str) -> "GetSquareEmidResponse":
        """Get square eMid.

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.5.py
        DATETIME: 02/03/2023, 23:02:07"""
        METHOD_NAME = "getSquareEmid"
        params = [[11, 1, squareMid]]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetSquareEmidResponse
        )

    def getSquareMembersBySquare(
        self, squareMid: str, squareMemberMids: List[str]
    ) -> "GetSquareMembersBySquareResponse":
        """Get square members by square.

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.5.py
        DATETIME: 02/03/2023, 23:02:07"""
        METHOD_NAME = "getSquareMembersBySquare"
        params = [
            [11, 2, squareMid],
            [14, 3, [11, squareMemberMids]],
        ]
        return self._call(
            METHOD_NAME,
            [[12, 1, params]],
            response_model=GetSquareMembersBySquareResponse,
        )

    def manualRepair(
        self, syncToken: str, limit: int, continuationToken: Optional[str] = None
    ) -> "ManualRepairResponse":
        """Manual repair.

        Example:
            `cl.manualRepair(limit=200)`

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.5.py
        DATETIME: 02/03/2023, 23:02:07"""
        METHOD_NAME = "manualRepair"
        params = [
            [11, 1, syncToken],
            [8, 2, limit],
            [11, 3, continuationToken],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=ManualRepairResponse
        )

    def getJoinedSquareChatThreads(
        self,
        squareChatMid: str,
        limit: int = 20,
        continuationToken: Optional[str] = None,
    ) -> "GetJoinedSquareChatThreadsResponse":
        """Get joined square chat threads.

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 04/24/2023, 18:07:51"""
        METHOD_NAME = "getJoinedSquareChatThreads"
        params = [
            [11, 1, squareChatMid],
            [8, 2, limit],
            [11, 3, continuationToken],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetJoinedThreadsResponse
        )

    def createSquareChatThread(
        self, squareChatMid: str, squareMid: str, messageId: str
    ) -> "CreateSquareChatThreadResponse":
        """Create square chat thread.

        Usages:
            `cl.createSquareChatThread(SQ_CHAT_MID, SQ_MID, MSG_ID)`

        Example:
            `cl.createSquareChatThread("mxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "sxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "123456")`

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 04/24/2023, 18:07:51"""
        METHOD_NAME = "createSquareThread"
        squareChatThread = [
            [11, 2, squareChatMid],
            [11, 3, squareMid],
            [11, 4, messageId],
        ]
        params = [
            [8, 1, self.client.getCurrReqId("sq")],
            [12, 2, squareChatThread],
        ]
        return self._call(
            METHOD_NAME,
            [[12, 1, params]],
            response_model=CreateSquareChatThreadResponse,
        )

    def getSquareChatThread(
        self, squareChatMid: str, squareChatThreadMid: str
    ) -> "GetSquareChatThreadResponse":
        """Get square chat thread.

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 04/24/2023, 18:07:51"""
        METHOD_NAME = "getSquareChatThread"
        params = [
            [11, 1, squareChatMid],
            [11, 2, squareChatThreadMid],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetSquareChatThreadResponse
        )

    def joinSquareChatThread(
        self, squareChatMid: str, squareChatThreadMid: str
    ) -> "JoinSquareChatThreadResponse":
        """Join square chat thread.

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 04/24/2023, 18:07:51"""
        METHOD_NAME = "joinSquareChatThread"
        params = [
            [11, 1, squareChatMid],
            [11, 2, squareChatThreadMid],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=JoinSquareChatThreadResponse
        )

    def syncSquareMembers(
        self, squareMid: str, squareMembers: Dict[str, int]
    ) -> "SyncSquareMembersResponse":
        """Sync square members.

        Usages:
            `cl.syncSquareMembers(SQ_MID, {MBER_MID: REV})`

        Example:
            `cl.syncSquareMembers("sxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", {'pxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx': 0})`

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 04/24/2023, 18:07:51"""
        METHOD_NAME = "syncSquareMembers"
        params = [
            [11, 1, squareMid],
            [13, 2, [11, 10, squareMembers]],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=SyncSquareMembersResponse
        )

    def hideSquareMemberContents(
        self, squareMemberMid: str
    ) -> "HideSquareMemberContentsResponse":
        """Hide square member contents.

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 05/29/2024, 19:02:42"""
        METHOD_NAME = "hideSquareMemberContents"
        params = [
            [11, 1, squareMemberMid],
        ]
        return self._call(
            METHOD_NAME,
            [[12, 1, params]],
            response_model=HideSquareMemberContentsResponse,
        )

    def markChatsAsRead(self, chatMids: List[str]) -> "MarkChatsAsReadResponse":
        """Mark chats as read.

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 05/29/2024, 19:02:42"""
        METHOD_NAME = "markChatsAsRead"
        params = [
            [14, 2, [11, chatMids]],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=MarkChatsAsReadResponse
        )

    def reportMessageSummary(
        self, chatEmid: str, messageSummaryRangeTo: int, reportType: int
    ) -> "ReportMessageSummaryResponse":
        """Report message summary.

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 05/29/2024, 19:02:42"""
        METHOD_NAME = "reportMessageSummary"
        params = [
            [11, 1, chatEmid],
            [10, 2, messageSummaryRangeTo],
            [8, 3, reportType],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=ReportMessageSummaryResponse
        )

    def getGoogleAdOptions(
        self, squareMid: str, chatMid: str, adScreen: int
    ) -> "GetGoogleAdOptionsResponse":
        """Get google ad options.

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 05/29/2024, 19:02:42"""
        METHOD_NAME = "getGoogleAdOptions"
        params = [
            [11, 1, squareMid],
            [11, 2, chatMid],
            [8, 3, adScreen],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetGoogleAdOptionsResponse
        )

    def unhideSquareMemberContents(
        self, squareMemberMid: str
    ) -> "UnhideSquareMemberContentsResponse":
        """Unhide square member contents.

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 05/29/2024, 19:02:42"""
        METHOD_NAME = "unhideSquareMemberContents"
        params = [
            [11, 1, squareMemberMid],
        ]
        return self._call(
            METHOD_NAME,
            [[12, 1, params]],
            response_model=UnhideSquareMemberContentsResponse,
        )

    def getSquareChatEmid(self, squareChatMid: str) -> "GetSquareChatEmidResponse":
        """Get square chat emid.

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 05/29/2024, 19:02:42"""
        METHOD_NAME = "getSquareChatEmid"
        params = [
            [11, 1, squareChatMid],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetSquareChatEmidResponse
        )

    def getSquareThread(
        self, threadMid: str, includeRootMessage: bool = True
    ) -> "GetSquareThreadResponse":
        """Get square thread.

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 05/29/2024, 19:02:42"""
        METHOD_NAME = "getSquareThread"
        params = [
            [11, 1, threadMid],
            [2, 2, includeRootMessage],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetSquareThreadResponse
        )

    def getSquareThreadMid(
        self, chatMid: str, messageId: str
    ) -> "GetSquareThreadMidResponse":
        """Get square thread mid.

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 05/29/2024, 19:02:42"""
        METHOD_NAME = "getSquareThreadMid"
        params = [
            [11, 1, chatMid],
            [11, 2, messageId],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetSquareThreadMidResponse
        )

    def getUserSettings(self, requestedAttrs: list = [1]) -> "GetUserSettingsResponse":
        """Get user settings.

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 05/29/2024, 19:02:42"""
        METHOD_NAME = "getUserSettings"
        params = [
            [14, 1, [8, requestedAttrs]],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=GetUserSettingsResponse
        )

    def markThreadsAsRead(self, chatMid: str) -> "MarkThreadsAsReadResponse":
        """Mark threads as read.

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 05/29/2024, 19:02:42"""
        METHOD_NAME = "markThreadsAsRead"
        params = [
            [11, 1, chatMid],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=MarkThreadsAsReadResponse
        )

    def sendSquareThreadMessage(
        self, chatMid: str, threadMid: str, text: str
    ) -> "SendSquareThreadMessageResponse":
        """Send square thread message.

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 05/29/2024, 19:02:42"""
        METHOD_NAME = "sendSquareThreadMessage"
        message = [
            [11, 2, threadMid],
            [11, 10, text],
            [8, 15, 0],
        ]
        threadMessage = [
            [12, 1, message],
            [8, 3, 5],
        ]
        params = [
            [8, 1, self.client.getCurrReqId("sq")],
            [11, 2, chatMid],
            [11, 3, threadMid],
            [12, 4, threadMessage],
        ]
        return self._call(
            METHOD_NAME,
            [[12, 1, params]],
            response_model=SendSquareThreadMessageResponse,
        )

    def findSquareByInvitationTicketV2(
        self, invitationTicket: str
    ) -> FindSquareByInvitationTicketV2Response:
        """Find square by invitation ticket v2.

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 05/29/2024, 19:02:42"""
        METHOD_NAME = "findSquareByInvitationTicketV2"
        params = [[11, 1, invitationTicket]]
        return self._call(
            METHOD_NAME,
            [[12, 1, params]],
            response_model=FindSquareByInvitationTicketV2Response,
        )

    def leaveSquareThread(
        self, chatMid: str, threadMid: str
    ) -> "LeaveSquareThreadResponse":
        """Remove the thread from my favorites.

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 05/29/2024, 19:02:42"""
        METHOD_NAME = "leaveSquareThread"
        params = [
            [11, 1, chatMid],
            [11, 2, threadMid],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=LeaveSquareThreadResponse
        )

    def joinSquareThread(
        self, chatMid: str, threadMid: str
    ) -> "JoinSquareThreadResponse":
        """Add the thread to my favorites.

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 05/29/2024, 19:02:42"""
        METHOD_NAME = "joinSquareThread"
        params = [
            [11, 1, chatMid],
            [11, 2, threadMid],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=JoinSquareThreadResponse
        )

    def updateUserSettings(
        self, updatedAttrs: List[int], liveTalkNotification: Optional[bool] = None
    ) -> "UpdateUserSettingsResponse":
        """Update user settings.

        ---
        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 05/29/2024, 19:02:42"""
        METHOD_NAME = "updateUserSettings"
        userSettings = []
        if liveTalkNotification is not None:
            userSettings.append([8, 1, liveTalkNotification])
        params = [
            [14, 1, [8, updatedAttrs]],
            [12, 2, userSettings],
        ]
        return self._call(
            METHOD_NAME, [[12, 1, params]], response_model=UpdateUserSettingsResponse
        )

    def searchMentionables(self) -> "SearchMentionablesResponse":
        """AUTO_GENERATED_CODE! DONT_USE_THIS_FUNC!!

        GENERATED BY YinMo0913_DeachSword-DearSakura_v1.0.6.py
        DATETIME: 10/31/2024, 14:52:45"""
        raise Exception("searchMentionables is not implemented")
        METHOD_NAME = "searchMentionables"
        params = []
        sqrd = self.generateDummyProtocol(
            METHOD_NAME, params, self.SquareService_REQ_TYPE
        )
        return self.postPackDataAndGetUnpackRespData(
            self.SquareService_API_PATH, sqrd, self.SquareService_RES_TYPE
        )
