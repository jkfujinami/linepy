# -*- coding: utf-8 -*-
"""Pydantic models for LINE Timeline API responses.
These models provide type-safe, dot-accessible structures for the data returned
by `Timeline.list_post`, `create_post`, `get_post`, etc.
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field


class UserInfo(BaseModel):
    """Post author information."""

    mid: str
    nickname: str
    userValid: bool = True
    role: str = ""
    writerMid: Optional[str] = None


class ReadPermission(BaseModel):
    """Read permission settings."""

    type: str = "ALL"
    gids: List[str] = Field(default_factory=list)
    count: Optional[int] = None
    homeID: Optional[str] = None


class GroupHome(BaseModel):
    """Group/Square home info."""

    groupId: str
    name: str
    pictureUrl: Optional[str] = None
    groupType: Optional[str] = None


class UrlInfo(BaseModel):
    """URL info for post."""

    type: str = "INTERNAL"
    targetUrl: str = ""


class PostInfo(BaseModel):
    """Post metadata."""

    appSn: int = 0
    homeId: str = ""
    postId: str
    status: str = "NORMAL"
    likeCount: int = 0
    commentCount: int = 0
    liked: bool = False
    url: Optional[UrlInfo] = None
    readPermission: ReadPermission = Field(default_factory=ReadPermission)
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
    groupHome: Optional[GroupHome] = None
    editableContents: List[str] = Field(default_factory=list)
    allowEdit: bool = True
    createdTime: int = 0
    updatedTime: int = 0


class TextStyle(BaseModel):
    """Text styling options."""

    textSizeMode: str = "NORMAL"
    backgroundColor: str = "#FFFFFF"
    textAnimation: str = "NONE"


class MediaStyle(BaseModel):
    """Media display options."""

    displayType: str = "GRID_1_A"


class ContentsStyle(BaseModel):
    """Content styling container."""

    textStyle: Optional[TextStyle] = Field(default_factory=TextStyle)
    stickerStyle: Dict[str, Any] = Field(default_factory=dict)
    mediaStyle: Optional[MediaStyle] = Field(default_factory=MediaStyle)


class Sticker(BaseModel):
    """Sticker in post."""

    id: str
    packageId: str
    packageVersion: int = 1
    hasAnimation: bool = True
    hasSound: bool = True
    stickerResourceType: str = "ANIMATION"


class Location(BaseModel):
    """Location in post."""

    latitude: float
    longitude: float
    name: str


class Media(BaseModel):
    """Media item in post."""

    objectId: str
    type: str
    obsFace: str = "[]"


class Contents(BaseModel):
    """Post contents."""

    contentsStyle: Optional[ContentsStyle] = Field(default_factory=ContentsStyle)
    stickers: List[Sticker] = Field(default_factory=list)
    locations: List[Location] = Field(default_factory=list)
    media: List[Media] = Field(default_factory=list)
    text: Optional[str] = None
    textMeta: List[Any] = Field(default_factory=list)
    sharedPostId: Optional[str] = None


class CpInfo(BaseModel):
    """Content provider info (line-square, etc.)."""

    # line-square specific
    isOwner: bool = False
    ableToDelete: bool = False
    ableToAnnounce: bool = False
    announced: bool = False


class Post(BaseModel):
    """A timeline/note post."""

    userInfo: UserInfo
    postInfo: PostInfo
    contents: Contents
    cpInfo: Dict[str, Any] = Field(default_factory=dict)
    statisticInfo: Dict[str, Any] = Field(default_factory=dict)


class FeedInfo(BaseModel):
    """Feed entry info."""

    type: str
    id: str
    status: str
    score: Optional[int] = None


class Feed(BaseModel):
    """A single feed entry containing post."""

    feedInfo: FeedInfo
    post: Post


class FeedPost(BaseModel):
    """Feed container for single post (create/get response)."""

    post: Post


class ListResult(BaseModel):
    """Result for list_post."""

    feeds: List[Feed] = Field(default_factory=list)


class CreateResult(BaseModel):
    """Result for create_post."""

    feed: FeedPost


class GetResult(BaseModel):
    """Result for get_post."""

    feed: FeedPost


class DeleteResult(BaseModel):
    """Result for delete_post."""

    pass


class ShareResult(BaseModel):
    """Result for share_post."""

    pass


class ListPostResponse(BaseModel):
    """Response from list_post."""

    code: int
    message: str
    result: ListResult


class CreatePostResponse(BaseModel):
    """Response from create_post."""

    code: int
    message: str
    result: CreateResult


class GetPostResponse(BaseModel):
    """Response from get_post."""

    code: int
    message: str
    result: GetResult


class DeletePostResponse(BaseModel):
    """Response from delete_post."""

    code: int
    message: str
    result: Optional[DeleteResult] = None


class SharePostResponse(BaseModel):
    """Response from share_post."""

    code: int
    message: str
    result: Optional[ShareResult] = None


# Backwards compatibility alias
TimelineResponse = ListPostResponse
