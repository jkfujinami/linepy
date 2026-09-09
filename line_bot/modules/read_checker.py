# -*- coding: utf-8 -*-
"""
既読チェッカーモジュール for LINE OC Bot

Square (OpenChat) の既読状況を追跡・確認する。

コマンド:
    !rp set    - チェックポイントを設置
    !rp check  - 最新メッセージの既読者を表示
    !rp list   - チェックポイント以降の既読者を表示
    !rp bad    - 既読したが発言していないメンバーを表示
    !rp reset  - 既読追跡をリセット
"""

import logging
from typing import Any, Dict, List

from core.base import BaseModule
from core.context import MessageContext, ReadContext

logger = logging.getLogger("line_bot.read_checker")


class ReadCheckerModule(BaseModule):
    """
    既読チェッカーモジュール

    チャットごとに独立した既読追跡を行う。
    """

    name = "read_checker"
    description = "既読状況を追跡・確認"

    def __init__(self, bot):
        super().__init__(bot)

        # チェックポイント管理 (per chat)
        self._checkpoints: Dict[str, Dict[str, Any]] = {}

        # 最新メッセージ既読管理 (per chat)
        self._latest_reads: Dict[str, Dict[str, Any]] = {}

    def _get_checkpoint(self, chat_mid: str) -> Dict[str, Any]:
        """チャットのチェックポイント状態を取得"""
        if chat_mid not in self._checkpoints:
            self._checkpoints[chat_mid] = {
                "mode": False,
                "message_id": None,
                "read_list": [],      # 既読したメンバー
                "bad_list": [],       # 既読無視メンバー
                "not_bad_list": [],   # 発言済みメンバー
            }
        return self._checkpoints[chat_mid]

    def _get_latest_reads(self, chat_mid: str) -> Dict[str, Any]:
        """最新メッセージの既読状態を取得"""
        if chat_mid not in self._latest_reads:
            self._latest_reads[chat_mid] = {
                "message_id": None,
                "read_list": [],
            }
        return self._latest_reads[chat_mid]

    # ========== イベントハンドラ ==========

    def on_message(self, ctx: MessageContext) -> bool:
        """メッセージイベントを処理"""
        chat_mid = ctx.chat_mid
        sender_mid = ctx.sender_mid

        try:
            message_id_int = int(ctx.message_id) if ctx.message_id else 0
        except ValueError:
            message_id_int = 0

        # !rp コマンド処理
        if ctx.command == "rp":
            self._handle_command(ctx, ctx.command_args.strip(), message_id_int)
            return True  # コマンドは処理済み

        # 最新メッセージIDを更新
        latest = self._get_latest_reads(chat_mid)
        latest["message_id"] = message_id_int
        latest["read_list"] = []

        # 発言者を「既読無視」リストから除外
        checkpoint = self._get_checkpoint(chat_mid)
        if checkpoint["message_id"] is not None and sender_mid:
            if sender_mid in checkpoint["bad_list"]:
                checkpoint["bad_list"].remove(sender_mid)
            if sender_mid not in checkpoint["not_bad_list"]:
                checkpoint["not_bad_list"].append(sender_mid)

        return False  # 他のモジュールも処理可能

    def on_read(self, ctx: ReadContext) -> None:
        """既読イベントを処理"""
        chat_mid = ctx.chat_mid
        member_mid = ctx.reader_mid
        message_id = ctx.message_id

        if not all([chat_mid, member_mid, message_id]):
            return

        try:
            message_id_int = int(message_id) if isinstance(message_id, str) else message_id
        except ValueError:
            return

        # チェックポイント追跡
        checkpoint = self._get_checkpoint(chat_mid)
        if (checkpoint["mode"] and
            checkpoint["message_id"] is not None and
            message_id_int > checkpoint["message_id"] and
            member_mid not in checkpoint["read_list"]):

            checkpoint["read_list"].append(member_mid)

            if member_mid not in checkpoint["not_bad_list"]:
                if member_mid not in checkpoint["bad_list"]:
                    checkpoint["bad_list"].append(member_mid)

        # 最新メッセージ既読追跡
        latest = self._get_latest_reads(chat_mid)
        if (latest["message_id"] is not None and
            message_id_int >= latest["message_id"] and
            member_mid not in latest["read_list"]):
            latest["read_list"].append(member_mid)

    # ========== コマンド処理 ==========

    def _handle_command(self, ctx: MessageContext, subcommand: str, message_id: int):
        """コマンドを処理"""
        chat_mid = ctx.chat_mid
        checkpoint = self._get_checkpoint(chat_mid)

        if subcommand == "set":
            checkpoint["mode"] = True
            checkpoint["message_id"] = message_id
            checkpoint["read_list"] = []
            checkpoint["bad_list"] = []
            checkpoint["not_bad_list"] = []
            ctx.reply("✅ 既読ポイントを設置しました")

        elif subcommand == "check":
            latest = self._get_latest_reads(chat_mid)
            names = self._get_names(latest["read_list"])
            ctx.reply(f"📖 既読メンバー ({len(latest['read_list'])}人)\n{names}")

        elif subcommand == "list":
            if checkpoint["message_id"] is None:
                ctx.reply("⚠️ 既読ポイントが未設置です\n使い方: !rp set")
            else:
                names = self._get_names(checkpoint["read_list"])
                ctx.reply(f"📖 既読メンバー ({len(checkpoint['read_list'])}人)\n{names}")

        elif subcommand == "bad":
            if checkpoint["message_id"] is None:
                ctx.reply("⚠️ 既読ポイントが未設置です\n使い方: !rp set")
            else:
                names = self._get_names(checkpoint["bad_list"])
                ctx.reply(f"👀 既読無視 ({len(checkpoint['bad_list'])}人)\n{names}")

        elif subcommand == "reset":
            checkpoint["mode"] = False
            checkpoint["message_id"] = None
            checkpoint["read_list"] = []
            checkpoint["bad_list"] = []
            checkpoint["not_bad_list"] = []
            ctx.reply("🔄 リセットしました")

        else:
            # ヘルプ
            ctx.reply(
                "📖 既読チェッカー\n"
                "\n"
                "!rp set   - ポイント設置\n"
                "!rp check - 最新既読者\n"
                "!rp list  - ポイント以降の既読者\n"
                "!rp bad   - 既読無視\n"
                "!rp reset - リセット"
            )

    # ========== ユーティリティ ==========

    def _get_names(self, mids: List[str]) -> str:
        """メンバー名一覧を取得"""
        if not mids:
            return "（なし）"

        names = []
        for mid in mids[:30]:
            try:
                m = self.client.square.getSquareMember(squareMemberMid=mid)
                name = m.squareMember.displayName
                names.append(f"・{name}")
            except Exception:
                names.append("・???")

        if len(mids) > 30:
            names.append(f"...他{len(mids)-30}人")

        return "\n".join(names)
