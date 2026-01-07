# -*- coding: utf-8 -*-
"""
Watch Storage - 監視対象と待機中リストの管理

ファイル構造:
{
    "watched": ["m123...", "m456..."],  # 監視中のチャットMID
    "pending": [                         # 承認待ちリスト
        {
            "square_mid": "s...",
            "chat_mid": "m...",
            "square_name": "OC名",
            "chat_name": "チャット名",
            "requested_at": 1234567890
        }
    ]
}
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Optional, Any

logger = logging.getLogger("line_bot.watch_storage")


class WatchStorage:
    """監視対象と参加待機中リストの管理"""

    def __init__(self, path: str = "data/watch_list.json"):
        self.path = Path(path)
        self._ensure_file()

    def _ensure_file(self):
        """ファイルが存在しなければ作成"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"watched": [], "pending": []})

    def _read(self) -> Dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"watched": [], "pending": []}

    def _write(self, data: Dict[str, Any]):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ========== Watched (監視中) ==========

    def get_watched(self) -> List[str]:
        """監視中のチャットMIDリストを取得"""
        return self._read().get("watched", [])

    def add_watched(self, chat_mid: str) -> bool:
        """監視リストに追加"""
        data = self._read()
        if chat_mid not in data["watched"]:
            data["watched"].append(chat_mid)
            self._write(data)
            logger.info("Added to watched: %s", chat_mid[:12])
            return True
        return False

    def remove_watched(self, chat_mid: str) -> bool:
        """監視リストから削除"""
        data = self._read()
        if chat_mid in data["watched"]:
            data["watched"].remove(chat_mid)
            self._write(data)
            logger.info("Removed from watched: %s", chat_mid[:12])
            return True
        return False

    def is_watched(self, chat_mid: str) -> bool:
        """監視中かどうか"""
        return chat_mid in self.get_watched()

    # ========== Pending (参加待機中) ==========

    def get_pending(self) -> List[Dict[str, Any]]:
        """参加待機中リストを取得"""
        return self._read().get("pending", [])

    def add_pending(
        self,
        square_mid: str,
        chat_mid: str,
        square_name: str,
        chat_name: str,
    ) -> bool:
        """待機リストに追加"""
        data = self._read()

        # 既に存在するか確認
        for item in data["pending"]:
            if item["chat_mid"] == chat_mid:
                return False

        data["pending"].append({
            "square_mid": square_mid,
            "chat_mid": chat_mid,
            "square_name": square_name,
            "chat_name": chat_name,
            "requested_at": int(time.time()),
        })
        self._write(data)
        logger.info("Added to pending: %s (%s)", chat_name, chat_mid[:12])
        return True

    def remove_pending(self, chat_mid: str) -> bool:
        """待機リストから削除"""
        data = self._read()
        original_len = len(data["pending"])
        data["pending"] = [p for p in data["pending"] if p["chat_mid"] != chat_mid]

        if len(data["pending"]) < original_len:
            self._write(data)
            logger.info("Removed from pending: %s", chat_mid[:12])
            return True
        return False

    def get_pending_by_square(self, square_mid: str) -> Optional[Dict[str, Any]]:
        """SquareMIDから待機中アイテムを取得"""
        for item in self.get_pending():
            if item["square_mid"] == square_mid:
                return item
        return None

    # ========== Move (待機 → 監視) ==========

    def move_pending_to_watched(self, chat_mid: str) -> bool:
        """待機リストから監視リストへ移動"""
        if self.remove_pending(chat_mid):
            return self.add_watched(chat_mid)
        return False
