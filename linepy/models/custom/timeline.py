# -*- coding: utf-8 -*-
"""Models for LINE Timeline API responses.

Plain stdlib ``@dataclass``es (see ``linepy.models.base``). These wrap real
JSON REST responses (VOOM API) rather than Thrift structs, so field names
match the JSON keys directly -- no ``alias`` mapping needed, just
``ModelBase.from_dict``/``to_dict`` for the same dot-accessible construction
LINEPY's ``Timeline.list_post``/``create_post``/``get_post`` etc. always had.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..base import ModelBase


@dataclass(kw_only=True)
class UserInfo(ModelBase):
    """Post author information."""

    mid: str
    nickname: str
    userValid: bool = True
    role: str = ""
    writerMid: Optional[str] = None


@dataclass(kw_only=True)
class ReadPermission(ModelBase):
    """Read permission settings."""

    type: str = "ALL"
    gids: List[str] = field(default_factory=list)
    count: Optional[int] = None
    homeID: Optional[str] = None


@dataclass(kw_only=True)
class GroupHome(ModelBase):
    """Group/Square home info."""

    groupId: str
    name: str
    pictureUrl: Optional[str] = None
    groupType: Optional[str] = None


@dataclass(kw_only=True)
class UrlInfo(ModelBase):
    """URL info for post."""

    type: str = "INTERNAL"
    targetUrl: str = ""


@dataclass(kw_only=True)
class PostInfo(ModelBase):
    """Post metadata."""

    appSn: int = 0
    homeId: str = ""
    postId: str
    status: str = "NORMAL"
    likeCount: int = 0
    commentCount: int = 0
    liked: bool = False
    url: Optional["UrlInfo"] = None
    readPermission: "ReadPermission" = field(default_factory=lambda: ReadPermission())
    allowShare: bool = True
    allowLikeShare: bool = False
    allowComment: bool = True
    allowPreviewComment: bool = True
    allowPhotoComment: bool = True
    allowLike: bool = True
    allowRecall: bool = True
    allowFriendRequest: bool = True
    allowCommentLike: bool = True
    allowLikeProfiles: bool = True
    enableCommentApproval: bool = False
    hasSharedToPost: bool = False
    commentLinkPermission: str = "ALL"
    likeLinkPermission: str = "ALL"
    groupHome: Optional["GroupHome"] = None
    editableContents: List[str] = field(default_factory=list)
    allowEdit: bool = True
    createdTime: int = 0
    updatedTime: int = 0


@dataclass(kw_only=True)
class TextStyle(ModelBase):
    """Text styling options."""

    textSizeMode: str = "NORMAL"
    backgroundColor: str = "#FFFFFF"
    textAnimation: str = "NONE"


@dataclass(kw_only=True)
class MediaStyle(ModelBase):
    """Media display options."""

    displayType: str = "GRID_1_A"


@dataclass(kw_only=True)
class ContentsStyle(ModelBase):
    """Content styling container."""

    textStyle: Optional["TextStyle"] = field(default_factory=lambda: TextStyle())
    stickerStyle: Dict[str, Any] = field(default_factory=dict)
    mediaStyle: Optional["MediaStyle"] = field(default_factory=lambda: MediaStyle())


@dataclass(kw_only=True)
class Sticker(ModelBase):
    """Sticker in post."""

    id: str
    packageId: str
    packageVersion: int = 1
    hasAnimation: bool = True
    hasSound: bool = True
    stickerResourceType: str = "ANIMATION"


@dataclass(kw_only=True)
class Location(ModelBase):
    """Location in post."""

    latitude: float
    longitude: float
    name: str


@dataclass(kw_only=True)
class Media(ModelBase):
    """Media item in post."""

    objectId: str
    type: str
    obsFace: str = "[]"


@dataclass(kw_only=True)
class Contents(ModelBase):
    """Post contents."""

    contentsStyle: Optional["ContentsStyle"] = field(default_factory=lambda: ContentsStyle())
    stickers: List["Sticker"] = field(default_factory=list)
    locations: List["Location"] = field(default_factory=list)
    media: List["Media"] = field(default_factory=list)
    text: Optional[str] = None
    textMeta: List[Any] = field(default_factory=list)
    sharedPostId: Optional[str] = None


@dataclass(kw_only=True)
class CpInfo(ModelBase):
    """Content provider info (line-square, etc.)."""

    # line-square specific
    isOwner: bool = False
    ableToDelete: bool = False
    ableToAnnounce: bool = False
    announced: bool = False


@dataclass(kw_only=True)
class Post(ModelBase):
    """A timeline/note post."""

    userInfo: "UserInfo"
    postInfo: "PostInfo"
    contents: "Contents"
    cpInfo: Dict[str, Any] = field(default_factory=dict)
    statisticInfo: Dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True)
class FeedInfo(ModelBase):
    """Feed entry info."""

    type: str
    id: str
    status: str
    score: Optional[int] = None


@dataclass(kw_only=True)
class Feed(ModelBase):
    """A single feed entry containing post."""

    feedInfo: "FeedInfo"
    post: "Post"


@dataclass(kw_only=True)
class FeedPost(ModelBase):
    """Feed container for single post (create/get response)."""

    post: "Post"


@dataclass(kw_only=True)
class ListResult(ModelBase):
    """Result for list_post."""

    feeds: List["Feed"] = field(default_factory=list)


@dataclass(kw_only=True)
class CreateResult(ModelBase):
    """Result for create_post."""

    feed: "FeedPost"


@dataclass(kw_only=True)
class GetResult(ModelBase):
    """Result for get_post."""

    feed: "FeedPost"


@dataclass(kw_only=True)
class DeleteResult(ModelBase):
    """Result for delete_post."""


@dataclass(kw_only=True)
class ShareResult(ModelBase):
    """Result for share_post."""


@dataclass(kw_only=True)
class ListPostResponse(ModelBase):
    """Response from list_post."""

    code: int
    message: str
    result: "ListResult"


@dataclass(kw_only=True)
class CreatePostResponse(ModelBase):
    """Response from create_post."""

    code: int
    message: str
    result: "CreateResult"


@dataclass(kw_only=True)
class GetPostResponse(ModelBase):
    """Response from get_post."""

    code: int
    message: str
    result: "GetResult"


@dataclass(kw_only=True)
class DeletePostResponse(ModelBase):
    """Response from delete_post."""

    code: int
    message: str
    result: Optional["DeleteResult"] = None


@dataclass(kw_only=True)
class SharePostResponse(ModelBase):
    """Response from share_post."""

    code: int
    message: str
    result: Optional["ShareResult"] = None


# Backwards compatibility alias
TimelineResponse = ListPostResponse
