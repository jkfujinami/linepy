# -*- coding: utf-8 -*-
"""
LIFF client (Phase 3 Step 11).

Faithful Python port of linejs LIFF (base/service/liff/mod.ts + client
features/liff.ts). Lets a bot issue LIFF views/tokens and send Flex, text and
sticker messages on a chat's behalf via LINE's message-share API.
"""

import json
from typing import Any, Dict, List, Optional

DEFAULT_LIFF_ID = "2006747340-AoraPvdD"
LIFF_ENDPOINT = "/LIFF1"
LIFF_SHARE_URL = "https://api.line.me/message/v3/share"


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------

def LiffTextMessage(text: str, sent_by: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    msg: Dict[str, Any] = {"type": "text", "text": text}
    if sent_by is not None:
        msg["sentBy"] = sent_by
    return msg


def LiffFlexMessage(alt_text: str, contents: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "flex", "altText": alt_text, "contents": contents}


def LiffStickerMessage(package_id: str, sticker_id: str) -> Dict[str, Any]:
    return {"type": "sticker", "packageId": str(package_id), "stickerId": str(sticker_id)}


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class LiffService:
    def __init__(self, client):
        self.client = client
        self.liff_id = DEFAULT_LIFF_ID
        self._token_cache: Dict[str, str] = {}

    def issue_liff_view(
        self, liff_id: str, chat_mid: Optional[str] = None, lang: str = "ja_JP"
    ) -> Any:
        """Call issueLiffView on /LIFF1 and return the parsed response."""
        context = [12, 1, []]
        if chat_mid:
            chat = [11, 1, chat_mid]
            cha_type = 2 if chat_mid[:1] in ("u", "c", "r") else 3
            context = [12, cha_type, [chat]]
        params = [
            [12, 1, [
                [11, 1, liff_id],
                [12, 2, [context]],
                [11, 3, lang],
            ]]
        ]
        return self.client._call_service(
            path=LIFF_ENDPOINT, method="issueLiffView", params=params
        )

    def get_liff_token(
        self, chat_mid: Optional[str], liff_id: str, lang: str = "ja_JP"
    ) -> str:
        """Issue a LIFF view and return its access token (field 3)."""
        resp = self.issue_liff_view(liff_id, chat_mid, lang)
        return _access_token(resp)

    def send_liff(
        self,
        to: str,
        messages: List[Dict[str, Any]],
        force_issue: bool = False,
    ) -> Any:
        """Send LIFF messages to a chat via the message-share API."""
        token = None if force_issue else self._token_cache.get(to)
        if not token:
            token = self.get_liff_token(chat_mid=to, liff_id=self.liff_id)
            self._token_cache[to] = token

        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 4.4.2; G730-U00 Build/JLS36C) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
                "Chrome/30.0.0.0 Mobile Safari/537.36 Line/9.8.0"
            ),
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-TW,zh;q=0.9",
            "Authorization": f"Bearer {token}",
            "content-type": "application/json",
        }
        payload = json.dumps({"messages": messages})
        response = self.client.request.post(
            LIFF_SHARE_URL, content=payload, headers=headers
        )
        response.raise_for_status()
        try:
            return response.json()
        except Exception:
            return response.text


def _access_token(resp: Any) -> str:
    if resp is None:
        raise ValueError("issueLiffView returned no response")
    if isinstance(resp, dict):
        for key in (3, "3", "access_token", "accessToken"):
            if key in resp and resp[key]:
                return resp[key]
    for attr in ("access_token", "accessToken"):
        val = getattr(resp, attr, None)
        if val:
            return val
    raise ValueError("issueLiffView response has no access token")
