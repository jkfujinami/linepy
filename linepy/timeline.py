"""
Timeline Service for LINEPY

Handles LINE Timeline and Square Note posts.
Based on linejs Timeline implementation.
"""

import json
import urllib.parse
from typing import Optional, Dict, List, Any, Union, Type, TypeVar

from pydantic import BaseModel

from .models.timeline import (
    ListPostResponse,
    CreatePostResponse,
    GetPostResponse,
    DeletePostResponse,
    SharePostResponse,
)

T = TypeVar("T", bound=BaseModel)


class Timeline:
    """
    Timeline (and Square Note) Service.

    This service uses REST API, not Thrift.
    Requires Channel Token.
    """

    def __init__(self, client):
        self.client = client
        self.timeline_token: Optional[str] = None
        self.timeline_headers: Dict[str, str] = {}

    def _get_channel_id(self) -> str:
        """Get Channel ID based on device type"""
        # CHROMEOS uses different channel ID
        if self.client.device == "CHROMEOS":
            return "1341209850"
        else:
            return "1341209950"

    def _init_timeline(self):
        """Initialize timeline token and headers if not ready"""
        if self.timeline_token:
            return

        channel_id = self._get_channel_id()

        # Get channel token from ChannelService
        resp = self.client.channel.approve_channel_and_issue_channel_token(channel_id)
        print(f"[Timeline] Channel response: {resp}")

        # CHRLINE-Patch: checkAndGetValue(resp, "channelAccessToken", 5)
        # Field ID 5 is channelAccessToken
        token = None
        if isinstance(resp, dict):
            # Try field ID 5 first (CHRLINE-Patch uses this)
            token = resp.get(5)
            if not token:
                # Fallback to field ID 1
                token = resp.get(1)
            if not token and isinstance(resp.get("channelAccessToken"), str):
                token = resp["channelAccessToken"]
        else:
            raise Exception("Failed to get channel token")

        if not token:
            raise Exception(f"No channel access token found in response: {resp}")

        self.timeline_token = token
        print(f"[Timeline] Got channel token: {token[:50]}...")

        self.timeline_headers = {
            "x-line-application": self.client.app_name,
            "User-Agent": self.client.request.user_agent,
            "X-Line-Mid": self.client.mid,
            "X-Line-Access": self.client.auth_token,
            "X-Line-ChannelToken": self.timeline_token,
            "x-lal": "ja_JP",
            "X-LAP": "5",
            "X-LPV": "1",
            "X-LSR": "JP",
            "x-line-bdbtemplateversion": "v1",
            "x-line-global-config": "discover.enable=true; follow.enable=true",
        }

        # CHROMEOS specific header
        if self.client.device == "CHROMEOS":
            self.timeline_headers["origin"] = "chrome-extension://linepy"

    def _request(
        self,
        endpoint: str,  # 'mh' (timeline) or 'sn' (square note)
        path: str,
        params: Dict[str, str] = None,
        data: Dict = None,
        method: str = "GET",
        response_model: Optional[Type[T]] = None,
    ) -> Union[T, Dict]:
        """Make request to Timeline API

        Args:
            endpoint: 'mh' (timeline) or 'sn' (square note)
            path: API path (e.g. 'list.json')
            params: Query parameters
            data: Request body data
            method: HTTP method for x-lhm header
            response_model: Pydantic model to parse response into

        Returns:
            Parsed Pydantic model or dict if no response_model
        """
        self._init_timeline()

        domain = "legy.line-apps.com"
        if endpoint == "sn":
            domain = "legy-jp.line-apps.com"

        url = f"https://{domain}/{endpoint}/api/v57/post/{path}"
        if params:
            query = urllib.parse.urlencode(params)
            url += f"?{query}"
        print(url)

        headers = self.timeline_headers.copy()

        # linejs uses x-lhm header for method
        headers["x-lhm"] = method

        # But real HTTP method is POST for create/delete even if logical method is different?
        # linejs: create -> POST, delete -> POST, get -> GET(implied), list -> GET(implied)
        # Actually in deletePost linejs uses POST method but x-lhm GET ??
        # Let's follow linejs implementation closely.

        http_method = method
        # 実際の通信傍受結果: list.json も POST (content-length: 0)
        if path == "delete.json":
            http_method = "POST"
        elif path == "create.json":
            http_method = "POST"
        elif path == "sendPostToTalk.json":
            http_method = "POST"
        elif path == "list.json":
            http_method = "POST"

        if http_method == "GET":
            # httpx handles GET
            body = None
        else:
            body = json.dumps(data) if data else None

        import httpx

        # We need to verify if we should use BaseClient's request or direct httpx
        # BaseClient.request handles Thrift mostly.
        # Let's use httpx directly but share client config if possible.
        # For simplicity, using httpx.Client here

        # Add Host header
        headers["Host"] = domain

        # Add Content-Type for POST requests
        if http_method == "POST":
            headers["Content-type"] = "application/json"

        print(headers)

        with httpx.Client(http2=True) as client:
            resp = client.request(
                method=http_method, url=url, headers=headers, content=body
            )

            if resp.status_code != 200:
                raise Exception(
                    f"Timeline request failed: {resp.status_code} {resp.text}"
                )

            json_data = resp.json()

            if response_model:
                return response_model.model_validate(json_data)
            return json_data

    def create_post(
        self,
        home_id: str,
        text: Optional[str] = None,
        shared_post_id: Optional[str] = None,
        text_size_mode: str = "NORMAL",
        background_color: str = "#FFFFFF",
        text_animation: str = "NONE",
        read_permission_type: str = "ALL",
        read_permission_gids: Optional[List[str]] = None,
        holding_time: Optional[int] = None,
        sticker_ids: Optional[List[str]] = None,
        sticker_package_ids: Optional[List[str]] = None,
        location_latitudes: Optional[List[float]] = None,
        location_longitudes: Optional[List[float]] = None,
        location_names: Optional[List[str]] = None,
        media_object_ids: Optional[List[str]] = None,
        media_object_types: Optional[List[str]] = None,
        source_type: str = "TIMELINE",
    ) -> CreatePostResponse:
        """
        Create a new post (Timeline or Square Note).

        Based on linejs implementation.

        Args:
            home_id: User MID (mh) or Square MID (sn)
            text: Post text content
            shared_post_id: Post ID to share
            text_size_mode: AUTO, NORMAL
            background_color: Hex color (e.g. #FFFFFF)
            text_animation: NONE, SLIDE, ZOOM, BUZZ, BOUNCE, BLINK
            read_permission_type: ALL, FRIEND, GROUP, EVENT, NONE
            read_permission_gids: Group IDs for permission
            holding_time: Auto delete time in seconds
            sticker_ids: List of sticker IDs
            sticker_package_ids: List of sticker package IDs
            location_latitudes: List of location latitudes
            location_longitudes: List of location longitudes
            location_names: List of location names
            media_object_ids: List of media object IDs
            media_object_types: List of media types
            source_type: TIMELINE
        """
        # Default empty lists
        if read_permission_gids is None:
            read_permission_gids = []
        if sticker_ids is None:
            sticker_ids = []
        if sticker_package_ids is None:
            sticker_package_ids = []
        if location_latitudes is None:
            location_latitudes = []
        if location_longitudes is None:
            location_longitudes = []
        if location_names is None:
            location_names = []
        if media_object_ids is None:
            media_object_ids = []
        if media_object_types is None:
            media_object_types = []

        if home_id.startswith("u"):
            raise ValueError("Not support oto (user timeline)")

        endpoint = "sn" if home_id.startswith("s") else "mh"

        params = {"homeId": home_id, "sourceType": source_type}

        post_info: Dict[str, Any] = {
            "readPermission": {
                "type": read_permission_type,
                "gids": read_permission_gids,
            }
        }
        if holding_time is not None:
            post_info["holdingTime"] = holding_time

        # Build stickers
        stickers = []
        for i, sticker_id in enumerate(sticker_ids):
            stickers.append(
                {
                    "id": sticker_id,
                    "packageId": (
                        sticker_package_ids[i] if i < len(sticker_package_ids) else ""
                    ),
                    "packageVersion": 1,
                    "hasAnimation": True,
                    "hasSound": True,
                    "stickerResourceType": "ANIMATION",
                }
            )

        # Build locations
        locations = []
        for i, lat in enumerate(location_latitudes):
            locations.append(
                {
                    "latitude": lat,
                    "longitude": (
                        location_longitudes[i] if i < len(location_longitudes) else 0
                    ),
                    "name": location_names[i] if i < len(location_names) else "",
                }
            )

        # Build media
        medias = []
        for i, obj_id in enumerate(media_object_ids):
            medias.append(
                {
                    "objectId": obj_id,
                    "type": (
                        media_object_types[i]
                        if i < len(media_object_types)
                        else "IMAGE"
                    ),
                    "obsFace": "[]",
                }
            )

        contents: Dict[str, Any] = {
            "contentsStyle": {
                "textStyle": {
                    "textSizeMode": text_size_mode,
                    "backgroundColor": background_color,
                    "textAnimation": text_animation,
                },
                "mediaStyle": {"displayType": "GRID_1_A"},
            },
            "stickers": stickers,
            "locations": locations,
            "media": medias,
        }
        if text is not None:
            contents["text"] = text
        if shared_post_id is not None:
            contents["sharedPostId"] = shared_post_id

        data = {"postInfo": post_info, "contents": contents}

        return self._request(
            endpoint,
            "create.json",
            params,
            data,
            method="POST",
            response_model=CreatePostResponse,
        )

    def get_post(self, home_id: str, post_id: str) -> GetPostResponse:
        """Get a post"""
        endpoint = "sn" if home_id.startswith("s") else "mh"
        params = {"homeId": home_id, "postId": post_id}
        return self._request(
            endpoint, "get.json", params, method="GET", response_model=GetPostResponse
        )

    def list_post(
        self,
        home_id: str,
        post_id: Optional[str] = None,
        updated_time: Optional[int] = None,
        source_type: str = "TALKROOM",
        like_limit: int = 0,
        comment_limit: int = 0,
    ) -> ListPostResponse:
        """
        List posts.

        Based on linejs implementation.
        Use post_id and updated_time for pagination.

        Args:
            home_id: User MID (mh) or Square MID (sn)
            post_id: Post ID for pagination offset
            updated_time: Updated time for pagination
            source_type: TALKROOM
            like_limit: Number of likes to fetch per post
            comment_limit: Number of comments to fetch per post
        """
        endpoint = "sn" if home_id.startswith("s") else "mh"

        params: Dict[str, Any] = {
            "homeId": home_id,
            "sourceType": source_type,
            "likeLimit": str(like_limit),
            "commentLimit": str(comment_limit),
        }
        if post_id is not None:
            params["postId"] = post_id
        if updated_time is not None:
            params["updatedTime"] = str(updated_time)

        return self._request(
            endpoint, "list.json", params, method="GET", response_model=ListPostResponse
        )

    def delete_post(self, home_id: str, post_id: str) -> DeletePostResponse:
        """Delete a post"""
        endpoint = "sn" if home_id.startswith("s") else "mh"
        params = {"homeId": home_id, "postId": post_id}
        # linejs: x-lhm = GET, HTTP method = POST
        return self._request(
            endpoint,
            "delete.json",
            params,
            method="GET",
            response_model=DeletePostResponse,
        )

    def share_post(
        self, home_id: str, post_id: str, chat_mid: str
    ) -> SharePostResponse:
        """
        Share a post to talk.

        Based on linejs implementation.

        Args:
            home_id: Home ID where the post belongs
            post_id: Post ID to share
            chat_mid: Chat MID to send the post to
        """
        endpoint = "sn" if home_id.startswith("s") else "mh"

        data = {
            "postId": post_id,
            "receiveMids": [chat_mid],
        }

        return self._request(
            endpoint,
            "sendPostToTalk.json",
            {},
            data,
            method="POST",
            response_model=SharePostResponse,
        )
