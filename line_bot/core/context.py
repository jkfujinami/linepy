# -*- coding: utf-8 -*-
"""
Context module for LINE OC Bot

イベントコンテキスト - メッセージ情報と便利メソッドを提供
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Dict, Any, List

from .storage import Role

if TYPE_CHECKING:
    from .bot import Bot


@dataclass
class MessageContext:
    """
    メッセージイベントのコンテキスト

    各モジュールに渡される、メッセージに関する全ての情報と
    返信などの便利メソッドを提供する。
    """

    # Bot参照
    bot: "Bot" = field(repr=False)

    # 基本情報
    chat_mid: str = ""              # どの部屋 (SquareChatMid)
    square_mid: str = ""            # どのOC (SquareMid)
    sender_mid: str = ""            # 送信者MID
    sender_name: str = ""           # 表示名
    message_id: str = ""            # メッセージID
    text: str = ""                  # 本文
    content_type: int = 0           # コンテンツ種別 (0=TEXT)

    # メンション
    mentions: Optional[List[str]] = None  # メンションされたMIDリスト

    # 生データ
    raw_event: Any = field(default=None, repr=False)

    RES_TEXT = "‎"

    # ========== 便利メソッド ==========

    def reply(self, text: str) -> None:
        """返信を送信"""
        self.bot.client.square.sendSquareMessage(
            squareChatMid=self.chat_mid,
            text=text,
            relatedMessageId=self.message_id,
        )

    def send(self, text: str) -> None:
        """メッセージを送信（返信なし）"""
        text = text
        self.bot.client.square.sendSquareMessage(
            squareChatMid=self.chat_mid,
            text=text,
        )

    # ========== 権限関連 ==========

    def get_role(self) -> Role:
        """送信者の権限を取得（SquareMid単位）"""
        storage = self.bot.get_square_storage(self.square_mid)
        return storage.get_role(self.sender_mid)

    def has_permission(self, required: Role) -> bool:
        """送信者が指定権限以上を持っているか"""
        # グローバル管理者は常にOWNER扱い
        if self.bot.global_storage.is_global_admin(self.sender_mid):
            return True

        storage = self.bot.get_square_storage(self.square_mid)
        return storage.has_permission(self.sender_mid, required)

    def is_banned(self) -> bool:
        """送信者がBANされているか"""
        # グローバルBAN
        if self.bot.global_storage.is_global_banned(self.sender_mid):
            return True

        # OC固有BAN（SquareMid単位）
        return self.get_role() == Role.BANNED

    # ========== ユーティリティ ==========

    @property
    def is_text(self) -> bool:
        """テキストメッセージか"""
        return self.content_type == 0

    @property
    def command(self) -> Optional[str]:
        """コマンド部分を取得 (!xxx の xxx 部分)"""
        if self.text and self.text.startswith("!"):
            parts = self.text[1:].split(maxsplit=1)
            return parts[0] if parts else None
        return None

    @property
    def command_args(self) -> str:
        """コマンド引数を取得"""
        if self.text and self.text.startswith("!"):
            parts = self.text[1:].split(maxsplit=1)
            return parts[1] if len(parts) > 1 else ""
        return ""


@dataclass
class ReadContext:
    """既読イベントのコンテキスト"""

    bot: "Bot" = field(repr=False)
    chat_mid: str = ""
    square_mid: str = ""
    reader_mid: str = ""      # 既読をつけた人
    message_id: str = ""      # どこまで読んだか


@dataclass
class JoinContext:
    """入室イベントのコンテキスト"""

    bot: "Bot" = field(repr=False)
    chat_mid: str = ""
    square_mid: str = ""
    member_mid: str = ""      # 入室した人
    member_name: str = ""

    def send_welcome(self, text: str) -> None:
        """入室メッセージを送信"""
        self.bot.client.square.sendSquareMessage(
            squareChatMid=self.chat_mid,
            text=text,
        )


@dataclass
class LeaveContext:
    """退室イベントのコンテキスト"""

    bot: "Bot" = field(repr=False)
    chat_mid: str = ""
    square_mid: str = ""
    member_mid: str = ""
    member_name: str = ""
