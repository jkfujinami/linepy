# -*- coding: utf-8 -*-
"""
Rate Limiter module for LINE OC Bot

短時間に大量のコマンドを投げるユーザーを制限する。
BAN回避攻撃対策。
"""

import logging
import time
from collections import defaultdict
from typing import Dict, List

from core.base import BaseModule
from core.context import MessageContext
from core.storage import Role

logger = logging.getLogger("line_bot.rate_limiter")


class RateLimiterModule(BaseModule):
    """
    レート制限モジュール

    短時間に大量のコマンドを投げるユーザーを検知・制限する。
    優先度を高く設定して、他のモジュールより先に処理。

    設定:
        max_commands: 許容コマンド数（デフォルト: 5）
        window_seconds: 時間枠（デフォルト: 10秒）
        cooldown_seconds: 制限時間（デフォルト: 60秒）
        auto_mute: 自動ミュートするか（デフォルト: False）
    """

    name = "rate_limiter"
    description = "コマンドレート制限"
    priority = 99  # BAN_HANDLERより低く、他より高い

    # 設定
    max_commands: int = 3  # 許容コマンド数
    window_seconds: int = 10  # 時間枠（秒）
    cooldown_seconds: int = 60  # 制限時間（秒）
    auto_mute: bool = False  # 自動ミュートするか
    warn_user: bool = True  # 警告メッセージを送るか

    def __init__(self, bot):
        super().__init__(bot)
        # ユーザーごとのコマンド履歴: {sender_mid: [timestamp, ...]}
        self._command_history: Dict[str, List[float]] = defaultdict(list)
        # 制限中のユーザー: {sender_mid: cooldown_end_time}
        self._rate_limited: Dict[str, float] = {}

    def on_message(self, ctx: MessageContext) -> bool:
        """コマンドのみレート制限をチェック"""
        # コマンド以外はスルー
        if not ctx.command:
            return False

        sender = ctx.sender_mid
        now = time.time()

        # 1. 既に制限中かチェック
        if sender in self._rate_limited:
            if now < self._rate_limited[sender]:
                # まだ制限中 → 無視
                logger.debug("[RATE] User %s is rate-limited, ignoring", sender[:12])
                return True  # コマンドを無視
            else:
                # 制限解除
                del self._rate_limited[sender]
                logger.info("[RATE] User %s cooldown expired", sender[:12])

        # 2. コマンド履歴を更新
        history = self._command_history[sender]
        history.append(now)

        # 古い履歴を削除（時間枠外）
        cutoff = now - self.window_seconds
        self._command_history[sender] = [t for t in history if t > cutoff]

        # 3. レート超過チェック
        if len(self._command_history[sender]) > self.max_commands:
            logger.warning(
                "[RATE] User %s exceeded rate limit (%d commands in %ds)",
                sender[:12], len(self._command_history[sender]), self.window_seconds
            )

            # 制限開始
            self._rate_limited[sender] = now + self.cooldown_seconds

            # 警告メッセージ
            if self.warn_user:
                ctx.reply(f"⚠️ コマンドの連続投稿を検知しました。{self.cooldown_seconds}秒間コマンドを無視します。")

            # 自動ミュート
            if self.auto_mute:
                try:
                    storage = self.bot.get_square_storage(ctx.square_mid)
                    storage.set_role(sender, Role.BANNED)
                    logger.info("[RATE] Auto-muted user %s", sender[:12])
                    ctx.reply("🔇 自動ミュートしました。")
                except Exception as e:
                    logger.warning("[RATE] Failed to auto-mute: %s", e)

            return True  # コマンドを無視

        return False  # 正常 → 後続モジュールに処理させる
