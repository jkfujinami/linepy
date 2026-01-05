# -*- coding: utf-8 -*-
"""
BAN Handler module for LINE OC Bot

BANユーザーの発言を処理する。
最優先で実行される（priority=100）。
"""

import logging
from typing import Optional

from core.context import MessageContext
from core.base import BaseModule
from core.storage import Role

logger = logging.getLogger("line_bot.ban_handler")


class BanHandlerModule(BaseModule):
    """
    BANハンドラモジュール

    BANユーザーが発言した場合に特定の処理を行う。
    デフォルトでは警告メッセージを送信してメッセージをスキップ。

    カスタマイズ:
        - on_banned_message をオーバーライドして処理を変更
        - kick_banned = True でキックする
        - warn_message でメッセージをカスタマイズ
    """

    name = "ban_handler"
    description = "BANユーザーの発言を処理"
    priority = 100  # 最優先で実行

    # 設定
    kick_banned: bool = False  # BANユーザーをキックするか
    delete_message: bool = True  # BANユーザーのメッセージを削除するか
    warn_message: Optional[str] = None  # 警告メッセージ（Noneで無効）
    log_only: bool = False  # ログのみ出力

    def on_message(self, ctx: MessageContext) -> bool:
        """BANユーザーかチェック"""
        if not ctx.is_banned():
            return False  # BANされていなければスルー

        # BANユーザーの処理
        return self.on_banned_message(ctx)

    def on_banned_message(self, ctx: MessageContext) -> bool:
        """
        BANユーザーの発言を処理

        オーバーライドしてカスタマイズ可能。

        Returns:
            True: 後続モジュールをスキップ
            False: 後続モジュールにも処理させる
        """
        logger.info(
            "[BAN] User %s (%s) sent message in %s",
            ctx.sender_name,
            ctx.sender_mid[:12],
            ctx.chat_mid[:12]
        )

        if self.log_only:
            return True  # ログのみ、後続はスキップ

        # 警告メッセージを送信
        if self.warn_message:
            ctx.reply(self.warn_message)
        # メッセージの削除
        if self.delete_message:
            try:
                self.client.square.destroySquareMessage(
                    squareChatMid=ctx.chat_mid,
                    messageId=ctx.message_id
                )
                logger.info("[BAN] Deleted message: %s", ctx.message_id)
            except Exception as e:
                logger.warning("[BAN] Failed to delete message: %s", e)
        return True  # 後続モジュールはスキップ
        # キック
        if self.kick_banned:
            try:
                self.client.square.deleteOtherFromSquare(
                    squareMid=ctx.square_mid,
                    squareMemberMid=ctx.sender_mid,
                    forChannel=True
                )
                logger.info("[BAN] Kicked user: %s", ctx.sender_mid[:12])
            except Exception as e:
                logger.warning("[BAN] Failed to kick: %s", e)

        return True  # 後続モジュールはスキップ
