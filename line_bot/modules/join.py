# -*- coding: utf-8 -*-
"""
Join Module - OC参加・監視追加機能

Usage:
    !join <ticket>
"""

from core.base import BaseModule
from core.context import MessageContext
from linepy.models.square import SquareJoinMethodType


class JoinModule(BaseModule):
    """OC参加モジュール"""

    name = "join"
    priority = 50

    def on_message(self, ctx: MessageContext) -> bool:
        if ctx.command != "join":
            return False

        # 引数チェック
        if not ctx.args:
            ctx.reply("使い方: !join <ticket>")
            return True

        ticket = ctx.args[0]
        self._handle_join(ctx, ticket)
        return True

    def _handle_join(self, ctx: MessageContext, ticket: str):
        """参加処理"""
        try:
            square = ctx.bot.client.square

            # 1. Ticket から情報取得
            ctx.reply(f"🔍 チケット確認中...")
            response = square.findSquareByInvitationTicketV2(ticket)

            square_name = response.square.name
            chat_name = response.chat.name
            chat_mid = response.chat.squareChatMid
            square_mid = response.square.mid
            join_method = response.square.joinMethod.type_
            membership = response.myMembership

            # 2. 状態判定
            if membership is None:
                # OC自体に未参加
                self._join_square(ctx, response, square_mid, chat_mid)
            else:
                # OC参加済み
                state = membership.membershipState
                if state == 1:  # PENDING
                    ctx.reply(f"⏳ 承認待ち中です: {square_name}")
                elif state == 2:  # JOINED
                    # サブトークに参加を試みる
                    self._join_chat(ctx, chat_mid, chat_name)
                else:
                    ctx.reply(f"❓ 不明な状態 (state={state})")

        except Exception as e:
            ctx.reply(f"❌ エラー: {e}")

    def _join_square(self, ctx: MessageContext, response, square_mid: str, chat_mid: str):
        """OC自体に参加する"""
        square = ctx.bot.
        join_method = response.square.joinMethod.type_
        square_name = response.square.name

        if join_method == SquareJoinMethodType.NONE:
            # 公開OC → 直接参加可能（デフォルトチャットに参加）
            try:
                # まずSquareに参加
                square.joinSquare(square_mid)
                ctx.reply(f"✅ 参加しました: {square_name}")

                # チャットにも参加
                self._join_chat(ctx, chat_mid, response.chat.name)
            except Exception as e:
                ctx.reply(f"❌ 参加失敗: {e}")

        elif join_method == SquareJoinMethodType.APPROVAL:
            # 承認制OC → リクエスト送信
            try:
                approval_msg = ""
                if response.square.joinMethod.value and response.square.joinMethod.value.approvalValue:
                    approval_msg = response.square.joinMethod.value.approvalValue.message or ""

                square.requestToJoinSquare(square_mid, displayName="Bot", profileImageObsHash="")
                ctx.reply(f"📨 参加リクエスト送信: {square_name}\n承認メッセージ: {approval_msg}")
            except Exception as e:
                ctx.reply(f"❌ リクエスト失敗: {e}")

        elif join_method == SquareJoinMethodType.CODE:
            # 鍵付きOC → パスコードが必要
            ctx.reply(f"🔐 パスコードが必要です: {square_name}\n使い方: !join <ticket> <code>")

        else:
            ctx.reply(f"❓ 不明な参加方法: {join_method}")

    def _join_chat(self, ctx: MessageContext, chat_mid: str, chat_name: str):
        """サブトーク/チャットに参加する"""
        square = ctx.bot.client.square

        try:
            square.joinSquareChat(chat_mid)
            ctx.reply(f"✅ チャット参加: {chat_name}")

            # 監視リストに追加
            self._add_to_watch(ctx, chat_mid)

        except Exception as e:
            error_msg = str(e)
            if "既に" in error_msg or "already" in error_msg.lower() or "メンバー" in error_msg:
                # 既に参加済み → 監視に追加するだけ
                ctx.reply(f"ℹ️ 既に参加済み: {chat_name}")
                self._add_to_watch(ctx, chat_mid)
            else:
                ctx.reply(f"❌ チャット参加失敗: {e}")

    def _add_to_watch(self, ctx: MessageContext, chat_mid: str):
        """監視リストに追加"""
        bot = ctx.bot

        # 既に監視中ならスキップ
        if chat_mid in bot.watched_chats:
            ctx.reply(f"ℹ️ 既に監視中: {chat_mid[:12]}...")
            return

        # 1. Bot の watched_chats に追加
        bot.watched_chats.append(chat_mid)

        # 2. 実行中の Polling に動的追加（新しい ChatWorker スレッドが起動）
        if hasattr(bot.client, 'polling') and bot.client.polling:
            bot.client.polling.add_watched_chat(chat_mid)
            ctx.reply(f"👁️ 監視開始: {chat_mid[:12]}...")

        # 3. 永続化（任意）
        # TODO: 設定ファイルに保存して再起動後も維持
