# -*- coding: utf-8 -*-
"""
Object-oriented message wrappers (Phase 2 Step 7).

``TalkMessage`` / ``SquareMessage`` wrap a raw message struct plus the client
and expose direct operations (reply, react, read, unsend, ...), mirroring the
linejs client message features.
"""

import json
from typing import Any, Dict, List, Optional


def _field(raw, name):
    """Read a message field from a ModelBase dataclass or a dict, tolerating aliases."""
    aliases = {
        "from": ("from_mid", "_from", "from_", "from"),
        "to": ("to", "to_mid"),
        "id": ("id_", "id"),
        "text": ("text",),
        "contentType": ("content_type", "contentType"),
        "contentMetadata": ("content_metadata", "contentMetadata"),
        "chunks": ("chunks",),
    }.get(name, (name,))
    if isinstance(raw, dict):
        for a in aliases:
            if a in raw:
                return raw[a]
        return None
    for a in aliases:
        if hasattr(raw, a):
            return getattr(raw, a)
    return None


class _BaseMessage:
    def __init__(self, raw, client):
        self.raw = raw
        self.client = client
        self.id = _field(raw, "id")
        self.text = _field(raw, "text")
        self.to = _field(raw, "to")
        self.sender_mid = _field(raw, "from")
        self.content_type = _field(raw, "contentType")
        self.content_metadata = _field(raw, "contentMetadata") or {}

    # ---- metadata helpers (shared) ----
    def get_mentions(self) -> List[Dict[str, Any]]:
        """Parse the MENTION content metadata into its mentionee list."""
        raw = self.content_metadata.get("MENTION")
        if not raw:
            return []
        try:
            return json.loads(raw).get("MENTIONEES", [])
        except Exception:
            return []

    def get_decorations(self) -> List[Dict[str, Any]]:
        raw = self.content_metadata.get("DECORATION") or self.content_metadata.get("DECO")
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else [parsed]
        except Exception:
            return []

    def get_sticker_url(self) -> Optional[str]:
        sid = self.content_metadata.get("STKID")
        if not sid:
            return None
        return f"https://stickershop.line-scdn.net/stickershop/v1/sticker/{sid}/iPhone/sticker.png"


class TalkMessage(_BaseMessage):
    """OO wrapper over a Talk (1:1 / group) message."""

    def reply(self, text: str) -> "TalkMessage":
        result = self.client.send_message(self.to, text, related_message_id=self.id)
        return TalkMessage(result, self.client)

    def react(self, reaction_type: int = 2) -> None:
        talk = getattr(self.client, "talk", None)
        req = [[8, 1, self.client.get_reqseq()], [11, 2, self.id],
               [12, 3, [[8, 1, reaction_type]]]]
        return talk._call("react", [[12, 1, req]], response_model=None)

    def read(self) -> None:
        return self.client.talk.send_chat_checked(
            seq=self.client.get_reqseq(), chat_mid=self.to, last_message_id=self.id
        )

    def unsend(self) -> None:
        return self.client.talk.unsend_message(
            seq=self.client.get_reqseq(), message_id=self.id
        )

    def announce(self) -> Any:
        return self.client.talk.create_chat_room_announcement(
            req_seq=self.client.get_reqseq(),
            chat_room_mid=self.to,
        )

    def get_data(self, preview: bool = False) -> bytes:
        """Download the media attached to this Talk message.

        Uses ``DOWNLOAD_URL`` if present, otherwise E2EE-decrypts when the
        message carries ``chunks``, else downloads the plain object by id.
        """
        url = self.content_metadata.get(
            "PREVIEW_URL" if preview else "DOWNLOAD_URL"
        )
        if url:
            resp = self.client.request._http.get(url)
            resp.raise_for_status()
            return resp.content
        if _field(self.raw, "chunks"):
            result = self.client.obs.download_media_by_e2ee(self.raw)
            return result["data"] if isinstance(result, dict) else result
        result = self.client.obs.download_message_data(
            self.id, is_preview=preview, is_square=False
        )
        return result["data"] if isinstance(result, dict) else result

    def is_my_message(self) -> bool:
        return self.sender_mid == getattr(self.client, "mid", None)


class SquareMessage(_BaseMessage):
    """OO wrapper over a Square (OpenChat) message."""

    def __init__(self, raw, client, square_chat_mid: Optional[str] = None):
        super().__init__(raw, client)
        self.square_chat_mid = square_chat_mid or self.to

    def reply(self, text: str) -> "SquareMessage":
        result = self.client.square.sendSquareMessage(
            self.square_chat_mid, text, relatedMessageId=self.id
        )
        return SquareMessage(result, self.client, self.square_chat_mid)

    def react(self, reaction_type: int = 2) -> Any:
        return self.client.square.reactToMessage(
            self.square_chat_mid, self.id, reaction_type
        )

    def unsend(self) -> Any:
        return self.client.square.unsendSquareMessage(self.square_chat_mid, self.id)

    def delete(self) -> Any:
        # Deleting one's own square message is an unsend on LINE.
        return self.unsend()

    def is_my_message(self) -> bool:
        my = getattr(self.client, "square_mid", None) or getattr(self.client, "mid", None)
        return self.sender_mid == my

    def get_data(self, preview: bool = False) -> bytes:
        """Download Square media (served in the clear from OBS, not E2EE)."""
        url = self.content_metadata.get(
            "PREVIEW_URL" if preview else "DOWNLOAD_URL"
        )
        if url:
            resp = self.client.request._http.get(url)
            resp.raise_for_status()
            return resp.content
        result = self.client.obs.download_message_data(
            self.id, is_preview=preview, is_square=True
        )
        return result["data"] if isinstance(result, dict) else result
