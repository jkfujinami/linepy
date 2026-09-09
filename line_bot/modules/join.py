# -*- coding: utf-8 -*-
"""
Join Module - OC参加・監視追加機能

Usage:
    !join <ticket> [displayName] [code]
    !update - 参加待機中のOCをチェックして入室済みならPollingに追加
    !pending - 参加待機中リストを表示
"""

from core.base import BaseModule
from core.context import MessageContext
from core.watch_storage import WatchStorage


class JoinModule(BaseModule):
    """OC参加モジュール"""

    name = "join"
    priority = 50

    def __init__(self, bot):
        super().__init__(bot)
        self.watch_storage = WatchStorage()

    def on_message(self, ctx: MessageContext) -> bool:
        if ctx.command == "join":
            return self._handle_join_command(ctx)
        elif ctx.command == "update":
            return self._handle_update_command(ctx)
        elif ctx.command == "pending":
            return self._handle_pending_command(ctx)
        return False

    def _handle_join_command(self, ctx: MessageContext) -> bool:
        """!join コマンド処理"""
        args = ctx.command_args.split() if ctx.command_args else []

        if not args:
            ctx.reply("使い方: !join <ticket> [code]")
            return True

        ticket = args[0]
        join_code = args[1] if len(args) > 1 else ""

        self._handle_join(ctx, ticket, join_code)
        return True

    def _handle_join(self, ctx: MessageContext, ticket: str, join_code: str):
        """参加処理"""
        try:
            helper = ctx.bot.client.square_helper
            result = helper.joinSquareByInvitationTicket(
                InvitationTicket=ticket,
                displayName="Mira",
                profileImagePath="/Users/fujinami/github/linepy/line_bot/assets/IMG_0001.jpg",
                defaultApprovalMessage="I'm Mira!よろしくお願いします！",
                defaultJoinCode=join_code,
            )

            status = result["status"]
            message = result["message"]
            chat_mid = result["chat_mid"]
            square_mid = result["square_mid"]
            square_name = result["square_name"]
            chat_name = result["chat_name"]

            # 結果を通知
            if status == "JOINED":
                ctx.reply(f"✅ {message}")
                # 監視リストに追加 & Pollingに追加
                self._add_to_watch(ctx, chat_mid)

            elif status == "ALREADY_MEMBER":
                ctx.reply(f"ℹ️ {message}")
                # 既に参加済みでも監視に追加
                self._add_to_watch(ctx, chat_mid)

            elif status == "PENDING":
                ctx.reply(f"📨 {message}")
                # 待機リストに追加
                self.watch_storage.add_pending(
                    square_mid=square_mid,
                    chat_mid=chat_mid,
                    square_name=square_name,
                    chat_name=chat_name,
                )
                ctx.reply("⏳ 待機リストに追加しました。!update で入室チェックできます。")

            elif status == "CODE_REQUIRED":
                ctx.reply(f"🔐 {message}\n使い方: !join <ticket> <displayName> <code>")

            else:  # ERROR
                ctx.reply(f"❌ {message}")

        except Exception as e:
            ctx.reply(f"❌ エラー: {e}")

    def _handle_update_command(self, ctx: MessageContext) -> bool:
        """!update コマンド - 待機リストをチェック"""
        pending_list = self.watch_storage.get_pending()

        if not pending_list:
            ctx.reply("📭 待機リストは空です")
            return True

        ctx.reply(f"🔄 {len(pending_list)}件の待機中OCをチェック中...")

        joined_count = 0
        still_pending = 0

        for item in pending_list:
            square_mid = item["square_mid"]
            chat_mid = item["chat_mid"]
            chat_name = item["chat_name"]

            try:
                # 入室確認: getSquareMembers で自分がいるかチェック
                if self._check_membership(ctx, square_mid):
                    # 入室済み → 監視に追加
                    self.watch_storage.move_pending_to_watched(chat_mid)
                    self._add_to_polling(ctx, chat_mid)
                    ctx.reply(f"✅ 入室確認: {chat_name}")
                    joined_count += 1
                else:
                    still_pending += 1
            except Exception as e:
                ctx.reply(f"⚠️ チェック失敗 ({chat_name}): {e}")
                still_pending += 1

        ctx.reply(f"📊 結果: 入室={joined_count}, 待機中={still_pending}")
        return True

    def _check_membership(self, ctx: MessageContext, square_mid: str) -> bool:
        """Squareのメンバーかどうかをチェック"""
        try:
            square = ctx.bot.client.square

            # getSquare で自分のメンバーシップ情報を取得
            res = square.getSquare(square_mid)

            if res and hasattr(res, 'myMembership') and res.myMembership:
                state = getattr(res.myMembership, 'membershipState', None)
                # state == 2 は JOINED
                return state == 2
            return False
        except Exception as e:
            # エラーの場合は未参加とみなす
            error_str = str(e).lower()
            if "not a member" in error_str or "メンバーではありません" in str(e):
                return False
            raise

    def _handle_pending_command(self, ctx: MessageContext) -> bool:
        """!pending コマンド - 待機リストを表示"""
        pending_list = self.watch_storage.get_pending()

        if not pending_list:
            ctx.reply("📭 待機リストは空です")
            return True

        lines = [f"⏳ 待機中: {len(pending_list)}件"]
        for item in pending_list:
            lines.append(f"  • {item['square_name']} / {item['chat_name']}")

        ctx.reply("\n".join(lines))
        return True

    def _add_to_watch(self, ctx: MessageContext, chat_mid: str):
        """監視リストに追加 & Pollingに追加"""
        if not chat_mid:
            return

        # ストレージに追加
        self.watch_storage.add_watched(chat_mid)

        # Pollingに追加
        self._add_to_polling(ctx, chat_mid)

    def _add_to_polling(self, ctx: MessageContext, chat_mid: str):
        """Pollingに動的追加"""
        bot = ctx.bot

        # 既に監視中ならスキップ
        if chat_mid in bot.watched_chats:
            return

        # Bot の watched_chats に追加
        bot.watched_chats.append(chat_mid)

        # 実行中の Polling に動的追加
        if hasattr(bot.client, 'polling') and bot.client.polling:
            bot.client.polling.add_watched_chat(chat_mid)
            ctx.reply(f"👁️ 監視開始: {chat_mid[:12]}...")
