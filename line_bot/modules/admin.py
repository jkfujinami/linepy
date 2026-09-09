# -*- coding: utf-8 -*-
"""
Admin module for LINE OC Bot

管理用コマンド（BAN, Kick, Role等）を提供。
"""

import logging
from typing import List, Optional

from core.base import BaseModule
from core.context import MessageContext
from core.storage import Role

logger = logging.getLogger("line_bot.admin")


class AdminModule(BaseModule):
    """
    管理モジュール

    Commands:
        !mute <MID|mention>    - ユーザーをミュート (ADMIN以上)
        !role <MID|mention> <role> - ユーザーの権限を変更 (ADMIN以上)
    """

    name = "admin"
    description = "管理用コマンド"
    priority = 60  # 通常モジュールより少し高め

    def on_message(self, ctx: MessageContext) -> bool:
        if not ctx.command:
            return False

        cmd = ctx.command.lower()

        # 権限チェックを伴うディスパッチ
        if cmd == "mute" and ctx.has_permission(Role.MODERATOR):
            return self._cmd_mute(ctx)
        if cmd == "unmute" and ctx.has_permission(Role.MODERATOR):
            return self._cmd_unmute(ctx)
        elif cmd == "role" and ctx.has_permission(Role.MODERATOR):
            return self._cmd_role(ctx)
        elif cmd == "broadcast" and ctx.has_permission(Role.ADMIN):
            return self._cmd_broadcast(ctx)
        return False

    def _get_target_mids(self, ctx: MessageContext) -> Optional[str]:
        """引数またはメンションから MID を取得"""
        if ctx.mentions:
            mids = []
            for i in ctx.mentions:
                mids.append(i['M'])
            return mids
        return None

    def _cmd_mute(self, ctx: MessageContext) -> bool:
        """!mute <MID|mention>"""
        target_mids = self._get_target_mids(ctx)
        if not target_mids:
            ctx.reply("⚠️ 対象をメンションで指定してください。")
            return True

        try:
            for i in target_mids:
                storage = self.bot.get_square_storage(ctx.square_mid)
                storage.set_role(i, Role.BANNED)
            ctx.reply(f"✅ ミュートに追加しました: {i[:12]}...")
            logger.info("User %s muted by %s in %s", i, ctx.sender_mid, ctx.square_mid)
        except Exception as e:
            ctx.reply(f"❌ ミュートの追加に失敗しました: {e}")

        return True

    def _cmd_unmute(self, ctx: MessageContext) -> bool:
        """!unmute <MID|mention>"""
        target_mids = self._get_target_mids(ctx)
        if not target_mids:
            ctx.reply("⚠️ 対象をメンションで指定してください。")
            return True

        try:
            for i in target_mids:
                storage = self.bot.get_square_storage(ctx.square_mid)
                storage.set_role(i, Role.MEMBER)
            ctx.reply(f"✅ ミュート解除しました: {i[:12]}...")
            logger.info("User %s unmuted by %s in %s", i, ctx.sender_mid, ctx.square_mid)
        except Exception as e:
            ctx.reply(f"❌ ミュートの解除に失敗しました: {e}")

        return True

    def _cmd_role(self, ctx: MessageContext) -> bool:
        """!role <MID|mention> <role_name>"""
        args = ctx.command_args.split()
        if len(args) < 2 and (not ctx.mentions or len(args) < 1):
            ctx.reply("⚠️ 使い方: !role <mention> <role_name>\n役職: guest, member, trusted, moderator, admin")
            return True

        target_mids = self._get_target_mids(ctx)
        role_name = args[-1].lower() # 最後の引数を役職名とみなす

        role_map = {
            "banned": Role.BANNED,
            "guest": Role.GUEST,
            "member": Role.MEMBER,
            "trusted": Role.TRUSTED,
            "moderator": Role.MODERATOR,
            "admin": Role.ADMIN,
        }

        if role_name not in role_map:
            ctx.reply(f"❌ 不正な役職名です: {role_name},役職例: guest, member, trusted, moderator, admin")
            return True

        new_role = role_map[role_name]

        # 権限レベルチェック（自分以上の権限は設定できない）
        my_role = ctx.get_role()
        if new_role >= my_role and not self.bot.global_storage.is_global_admin(ctx.sender_mid):
            ctx.reply("❌ 自分以上の権限を設定することはできません。")
            return True
        for i in target_mids:
            storage = self.bot.get_square_storage(ctx.square_mid)
            storage.set_role(i, new_role)
        ctx.reply(f"✅ 役職を更新しました: {new_role.display_name}\n💃Target: \n{self._get_names(target_mids)}")
        return True


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

    def _cmd_broadcast(self, ctx: MessageContext) -> bool:
        """!broadcast <message> - 監視中の全OCにメッセージを送信"""
        message = ctx.command_args
        if not message:
            ctx.reply("⚠️ 使い方: !broadcast <メッセージ>")
            return True

        watched_chats = getattr(self.bot, 'watched_chats', [])
        if not watched_chats:
            ctx.reply("❌ 監視中のチャットがありません。")
            return True

        success_count = 0
        fail_count = 0
        helper = self.bot.client.square_helper
        for chat_mid in watched_chats:
            try:
                # ランダムID付きで送信（BAN回避）
                helper.sendMessage(
                    squareChatMid=chat_mid,
                    text=f"{message}",
                    appendRandomId=True,
                )
                success_count += 1
            except Exception as e:
                logger.warning("Broadcast failed for %s: %s", chat_mid[:12], e)
                fail_count += 1

        ctx.reply(f"✅ 配信完了\n成功: {success_count}\n失敗: {fail_count}")
        return True
