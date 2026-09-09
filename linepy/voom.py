# -*- coding: utf-8 -*-
"""
VOOM / MyHome / Note / Album REST client (Phase 3 Step 12).

Faithful Python port of linejs
(resource/linejs/packages/linejs/client/features/voom.ts). Uses the MH-family
routing-prefix table and ``X-Line-ChannelToken`` auth against gw.line.naver.jp,
with automatic per-channel token caching.
"""

import json
from typing import Any, Dict, Optional

# Channel ids from smali t98.a$b.
VOOM_CHANNEL_ID = {
    "TIMELINE": "1341209950",
    "HOME": "1341209850",
    "HOME26": "2007835442",
    "NOTE": "1655599932",
    "SQUARE_NOTE": "1657618623",
    "ALBUM": "1375220249",
}

# Routing prefix per MH-family service, from smali ps5/j enum (11 prefixes).
VOOM_ROUTING_PREFIX = {
    "MYHOME": "/mh",
    "MYHOME_RENEWAL": "/hm",
    "TIMELINE": "/tl",
    "TIMELINE_GATEWAY": "/ext/timeline/tlgw",
    "NOTE": "/ext/note/nt",
    "HOMEAPI": "/ma",
    "SQUARE_NOTE": "/sn",
    "ALBUM": "/ext/album",
    "STORY": "/st",
    "SOCIAL_NOTIFICATION": "/eg",
    "TRANSLATION": "/ds",
}

# Curated MH-family REST paths from LINE Android 26.6.2 smali.
VOOM_ENDPOINTS = {
    "feed": "/api/v57/post/list.json",
    "createPost": "/api/v57/post/create.json",
    "updatePost": "/api/v57/post/update.json",
    "deletePost": "/api/v57/post/delete.json",
    "getPost": "/api/v57/post/get.json",
    "sharePost": "/api/v57/post/share.json",
    "sendPostToTalk": "/api/v57/post/sendPostToTalk.json",
    "getShareLink": "/api/v57/post/getShareLink.json",
    "reportPost": "/api/v57/post/report.json",
    "createComment": "/api/v57/comment/create.json",
    "deleteComment": "/api/v57/comment/delete.json",
    "getComment": "/api/v57/comment/get.json",
    "listComments": "/api/v57/comment/getList.json",
    "reportComment": "/api/v57/comment/report.json",
    "createLike": "/api/v57/like/create.json",
    "cancelLike": "/api/v57/like/cancel.json",
    "getLike": "/api/v57/like/get.json",
    "listLikes": "/api/v57/like/getList.json",
    "hashtagPosts": "/api/v57/hashtag/posts.json",
    "hashtagSearch": "/api/v57/hashtag/search.json",
    "hashtagSuggestPopular": "/api/v57/hashtag/suggest/popular.json",
    "groupHomeInit": "/api/v57/grouphome/init.json",
    "timelineStatus": "/api/v57/timeline/tab/status.json",
    "timelineContents": "/api/v57/timeline/tab/contents.json",
    "homeProfile": "/api/v1/home/profile.json",
    "homeCover": "/api/v1/home/cover.json",
}

DEFAULT_HOST = "gw.line.naver.jp"


class VoomClient:
    def __init__(self, client):
        self.client = client
        self._token_cache: Dict[str, str] = {}

    def get_token(self, channel: str) -> str:
        """Issue (and cache) a channel token for a named VOOM channel."""
        channel_id = VOOM_CHANNEL_ID.get(channel, channel)
        if channel_id in self._token_cache:
            return self._token_cache[channel_id]
        result = self.client.channel.issue_channel_token(channel_id)
        token = _extract_token(result)
        if not token:
            raise ValueError("issueChannelToken returned no token")
        self._token_cache[channel_id] = token
        return token

    def build_request(
        self,
        path: str,
        routing: str = "MYHOME",
        method: Optional[str] = None,
        body: Any = None,
        channel_token: Optional[str] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        host: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build the (url, method, headers, body) for a VOOM REST call.

        Split out from :meth:`rest` so the URL/header shaping is unit-testable
        without a live network.
        """
        host = host or DEFAULT_HOST
        prefix = VOOM_ROUTING_PREFIX[routing]
        method = method or ("POST" if body is not None else "GET")
        norm_path = path if path.startswith("/") else "/" + path
        url = f"https://{host}{prefix}{norm_path}"

        headers = {
            "accept": "application/json",
            "X-Line-Application": self.client.app_name,
            "user-agent": self.client.request.user_agent,
            "X-Line-Mid": getattr(self.client, "mid", "") or "",
            "x-lal": "ja-JP",
            "X-Line-BDBTemplateVersion": "v1",
        }
        if channel_token:
            headers["X-Line-ChannelToken"] = channel_token
        else:
            headers["X-Line-Access"] = self.client.auth_token
        if extra_headers:
            headers.update(extra_headers)
        encoded_body = None
        if body is not None:
            headers["content-type"] = "application/json"
            encoded_body = json.dumps(body)
        return {"url": url, "method": method, "headers": headers, "body": encoded_body}

    def rest(self, path: str, routing: str = "MYHOME", method: Optional[str] = None,
             body: Any = None, channel_token: Optional[str] = None,
             extra_headers: Optional[Dict[str, str]] = None,
             host: Optional[str] = None) -> Dict[str, Any]:
        req = self.build_request(path, routing, method, body, channel_token,
                                 extra_headers, host)
        http = self.client.request._http
        if req["method"] == "GET":
            resp = http.get(req["url"], headers=req["headers"])
        else:
            resp = http.request(req["method"], req["url"], headers=req["headers"],
                                 content=req["body"])
        text = resp.text
        if not text:
            return {"code": resp.status_code, "message": resp.reason_phrase, "result": None}
        return json.loads(text)

    # --- convenience endpoints -------------------------------------------

    def get_feed(self, **body) -> Dict[str, Any]:
        token = self.get_token("HOME")
        return self.rest(VOOM_ENDPOINTS["feed"], routing="MYHOME",
                         channel_token=token, body=body or None)

    def timeline_status(self) -> Dict[str, Any]:
        token = self.get_token("TIMELINE")
        return self.rest(VOOM_ENDPOINTS["timelineStatus"], routing="TIMELINE",
                         channel_token=token)


def _extract_token(result: Any) -> Optional[str]:
    if result is None:
        return None
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for key in ("token", "channelAccessToken", 1, "1"):
            if key in result and isinstance(result[key], str):
                return result[key]
    for attr in ("token", "channel_access_token", "channelAccessToken"):
        val = getattr(result, attr, None)
        if isinstance(val, str):
            return val
    return None
