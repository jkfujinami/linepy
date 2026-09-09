# -*- coding: utf-8 -*-
"""
Storage module for LINE OC Bot

LiveJSON を使ったデータ永続化
"""

from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Dict

import livejson


class Role(IntEnum):
    """ユーザー権限レベル"""
    BANNED = 0       # BAN済み
    GUEST = 10       # ゲスト（制限あり）
    MEMBER = 50      # 通常メンバー
    TRUSTED = 70     # 信頼済み
    MODERATOR = 80   # モデレーター
    ADMIN = 90       # 管理者
    OWNER = 100      # オーナー

    @classmethod
    def from_value(cls, value: int) -> "Role":
        """値からRoleを取得（不正値はMEMBERを返す）"""
        try:
            return cls(value)
        except ValueError:
            return cls.MEMBER

    @property
    def display_name(self) -> str:
        """表示用の名前"""
        names = {
            Role.BANNED: "🚫 BAN",
            Role.GUEST: "👤 ゲスト",
            Role.MEMBER: "👥 メンバー",
            Role.TRUSTED: "⭐ 信頼済み",
            Role.MODERATOR: "🛡️ モデレーター",
            Role.ADMIN: "👑 管理者",
            Role.OWNER: "🏠 オーナー",
        }
        return names.get(self, "❓ 不明")


class ChatStorage:
    """
    チャット（部屋）ごとのデータストレージ (LiveJSON)

    部屋固有のデータ（既読チェッカー状態、設定等）を管理する。
    ユーザー権限は SquareStorage で管理。
    """

    def __init__(self, chat_mid: str, data_dir: Path):
        self.chat_mid = chat_mid
        self.file_path = data_dir / "chats" / f"{chat_mid}.json"
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        # LiveJSONで開く（なければ自動作成）
        self._db = livejson.File(str(self.file_path))

        # 初期構造を保証
        if "settings" not in self._db:
            self._db["settings"] = {}
        if "chat_mid" not in self._db:
            self._db["chat_mid"] = chat_mid

    # ========== 設定操作 ==========

    def get_setting(self, key: str, default=None):
        """設定を取得"""
        return self._db["settings"].get(key, default)

    def set_setting(self, key: str, value) -> None:
        """設定を保存"""
        self._db["settings"][key] = value


class SquareStorage:
    """
    Square（OC全体）単位のデータストレージ (LiveJSON)

    ユーザー権限、統計など OC 全体で共有するデータを管理する。
    同じ SquareMid 内の複数部屋で権限を共有できる。
    """

    def __init__(self, square_mid: str, data_dir: Path):
        self.square_mid = square_mid
        self.file_path = data_dir / "squares" / f"{square_mid}.json"
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        # LiveJSONで開く（なければ自動作成）
        self._db = livejson.File(str(self.file_path))

        # 初期構造を保証
        if "users" not in self._db:
            self._db["users"] = {}
        if "settings" not in self._db:
            self._db["settings"] = {}
        if "square_mid" not in self._db:
            self._db["square_mid"] = square_mid

    # ========== ユーザー操作 ==========

    def get_user(self, user_mid: str) -> dict:
        """ユーザー情報を取得（なければ作成）"""
        if user_mid not in self._db["users"]:
            self._db["users"][user_mid] = {
                "role": int(Role.MEMBER),
                "message_count": 0,
                "display_name": None,
                "last_seen": None,
                "joined_at": None,
                "notes": None,
            }
        return self._db["users"][user_mid]

    def get_role(self, user_mid: str) -> Role:
        """権限を取得"""
        user = self.get_user(user_mid)
        return Role.from_value(user.get("role", Role.MEMBER))

    def set_role(self, user_mid: str, role: Role) -> None:
        """権限を設定"""
        user = self.get_user(user_mid)
        user["role"] = int(role)

    def has_permission(self, user_mid: str, required: Role) -> bool:
        """指定権限以上を持っているか"""
        return self.get_role(user_mid) >= required

    def update_display_name(self, user_mid: str, name: str) -> None:
        """表示名を更新"""
        user = self.get_user(user_mid)
        user["display_name"] = name

    def increment_message_count(self, user_mid: str) -> int:
        """発言カウント +1"""
        user = self.get_user(user_mid)
        user["message_count"] = user.get("message_count", 0) + 1
        user["last_seen"] = datetime.now().isoformat()
        return user["message_count"]

    def get_message_count(self, user_mid: str) -> int:
        """発言カウントを取得"""
        return self.get_user(user_mid).get("message_count", 0)

    def set_joined_at(self, user_mid: str) -> None:
        """参加日時を設定（未設定の場合のみ）"""
        user = self.get_user(user_mid)
        if user.get("joined_at") is None:
            user["joined_at"] = datetime.now().isoformat()

    # ========== 設定操作 ==========

    def get_setting(self, key: str, default=None):
        """設定を取得"""
        return self._db["settings"].get(key, default)

    def set_setting(self, key: str, value) -> None:
        """設定を保存"""
        self._db["settings"][key] = value

    # ========== 統計 ==========

    def get_user_count(self) -> int:
        """登録ユーザー数"""
        return len(self._db["users"])

    def get_all_users(self) -> Dict[str, dict]:
        """全ユーザーを取得"""
        return dict(self._db["users"])


class GlobalStorage:
    """
    グローバル設定 (全OC共通)

    グローバルBANリスト、全体管理者リストなどを管理する。
    """

    def __init__(self, data_dir: Path):
        self.file_path = data_dir / "global.json"
        data_dir.mkdir(parents=True, exist_ok=True)

        self._db = livejson.File(str(self.file_path))

        # 初期構造を保証
        if "banned_users" not in self._db:
            self._db["banned_users"] = []
        if "admins" not in self._db:
            self._db["admins"] = []

    def is_global_banned(self, user_mid: str) -> bool:
        """グローバルBANされているか"""
        return user_mid in self._db["banned_users"]

    def add_global_ban(self, user_mid: str) -> None:
        """グローバルBANに追加"""
        if user_mid not in self._db["banned_users"]:
            banned = list(self._db["banned_users"])
            banned.append(user_mid)
            self._db["banned_users"] = banned

    def remove_global_ban(self, user_mid: str) -> None:
        """グローバルBANから削除"""
        if user_mid in self._db["banned_users"]:
            banned = list(self._db["banned_users"])
            banned.remove(user_mid)
            self._db["banned_users"] = banned

    def is_global_admin(self, user_mid: str) -> bool:
        """グローバル管理者か"""
        return user_mid in self._db["admins"]

    def add_global_admin(self, user_mid: str) -> None:
        """グローバル管理者に追加"""
        if user_mid not in self._db["admins"]:
            admins = list(self._db["admins"])
            admins.append(user_mid)
            self._db["admins"] = admins
