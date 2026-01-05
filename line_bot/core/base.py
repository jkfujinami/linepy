# -*- coding: utf-8 -*-
"""
Base module for LINE OC Bot

モジュール基底クラス
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .context import MessageContext, ReadContext, JoinContext, LeaveContext

if TYPE_CHECKING:
    from .bot import Bot


class BaseModule(ABC):
    """
    機能モジュールの基底クラス

    全てのモジュールはこのクラスを継承し、
    on_message() を実装する必要がある。

    priority が高いモジュールほど先に実行される（デフォルト: 50）。

    Example:
        class MyModule(BaseModule):
            name = "my_module"
            priority = 100  # 高いほど先に実行

            def on_message(self, ctx: MessageContext) -> bool:
                if ctx.text == "!hello":
                    ctx.reply("Hello!")
                    return True
                return False
    """

    # モジュール名（一意である必要がある）
    name: str = "base"

    # モジュールの説明
    description: str = ""

    # 優先度（高いほど先に実行）
    priority: int = 50

    def __init__(self, bot: "Bot"):
        self.bot = bot
        self.client = bot.client

    @abstractmethod
    def on_message(self, ctx: MessageContext) -> bool:
        """
        メッセージイベントを処理

        Args:
            ctx: メッセージコンテキスト

        Returns:
            True: このモジュールで処理完了（後続モジュールをスキップ）
            False: 処理しなかった（後続モジュールに処理を委譲）
        """
        pass

    def on_read(self, ctx: ReadContext) -> None:
        """
        既読イベントを処理（オプション）

        Args:
            ctx: 既読コンテキスト
        """
        pass

    def on_join(self, ctx: JoinContext) -> None:
        """
        入室イベントを処理（オプション）

        Args:
            ctx: 入室コンテキスト
        """
        pass

    def on_leave(self, ctx: LeaveContext) -> None:
        """
        退室イベントを処理（オプション）

        Args:
            ctx: 退室コンテキスト
        """
        pass

    def on_load(self) -> None:
        """
        モジュールがロードされたときに呼ばれる（オプション）

        初期化処理などに使用。
        """
        pass

    def on_unload(self) -> None:
        """
        モジュールがアンロードされたときに呼ばれる（オプション）

        クリーンアップ処理などに使用。
        """
        pass
