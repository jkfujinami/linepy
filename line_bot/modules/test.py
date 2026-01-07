# -*- coding: utf-8 -*-
"""
Test module for LINE OC Bot

!test コマンドで動作確認
"""

from core.context import MessageContext
from core.base import BaseModule
from core.storage import Role


class TestModule(BaseModule):
    """
    テストモジュール

    Commands:
        !help - ヘルプの表示
        !test - 動作確認と権限表示
        !myid - 自分のMIDを表示
        !stats - 自分の統計を表示
    """

    name = "test"
    description = "動作確認用テストモジュール"

    def on_message(self, ctx: MessageContext) -> bool:
        if not ctx.command:
            return False
        if ctx.command == "help":
            return self._cmd_help(ctx)
        if ctx.command == "test":
            return self._cmd_test(ctx)
        elif ctx.command == "myid":
            return self._cmd_myid(ctx)
        elif ctx.command == "stats":
            return self._cmd_stats(ctx)
        elif ctx.command == "おっぱいみせて":
            return self._cmd_oppai(ctx)
        elif ctx.command == "setrole" and ctx.has_permission(Role.ADMIN):
            return self._cmd_setrole(ctx)

        return False

    def _cmd_test(self, ctx: MessageContext) -> bool:
        """!test - 動作確認"""
        role = ctx.get_role()

        text = (
            f"👋 Hello! Test!\n"
            f"\n"
            f"📌 あなたの情報:\n"
            f"・名前: {ctx.sender_name}\n"
            f"・権限: {role.display_name}\n"
            f"・MID: {ctx.sender_mid[:12]}...\n"
        )

        ctx.reply(text)
        return True

    def _cmd_oppai(self, ctx: MessageContext) -> bool:
        """!oppai - おっぱい見せて"""
        ctx.reply("""自分のみとけ😆""")
        return True

    def _cmd_help(self, ctx: MessageContext) -> bool:
        """!help - ヘルプの表示"""
        ctx.reply("""
✅テスト用コマンド
    !help - ヘルプの表示
    !test - 動作確認と権限表示
    !myid - 自分のMIDを表示
    !stats - 自分の統計を表示
    !setrole <MID> <role> - 権限を設定（管理者のみ）

✅管理用コマンド
    !mute <MID|mention>    - ユーザーをミュート（モデレーター以上）
    !unmute <MID|mention>  - ユーザーをミュート解除（モデレーター以上）
    !broadcast <text>      - メッセージを全チャットに送信（モデレーター以上）
    !role <MID|mention> <role> - ユーザーの権限を変更（モデレーター以上）

✅他オプ招待機能
    !join <ticket> [displayName] [code]
    !update - 参加待機中のOCをチェックして入室済みならリストに追加
    !pending - 参加待機中リストを表示

📖 既読チェッカー
    !rp set    - チェックポイントを設置
    !rp check  - 最新メッセージの既読者を表示
    !rp list   - チェックポイント以降の既読者を表示
    !rp bad    - 既読したが発言していないメンバーを表示
    !rp reset  - 既読追跡をリセット

        """)
        return True

    def _cmd_myid(self, ctx: MessageContext) -> bool:
        """!myid - 自分のMIDを表示"""
        ctx.reply(f"🆔 あなたのMID:\n{ctx.sender_mid}")
        return True

    def _cmd_stats(self, ctx: MessageContext) -> bool:
        """!stats - 自分の統計を表示"""
        storage = self.bot.get_square_storage(ctx.square_mid)
        user = storage.get_user(ctx.sender_mid)
        role = Role.from_value(user.get("role", Role.MEMBER))

        text = (
            f"📊 あなたの統計:\n"
            f"\n"
            f"・権限: {role.display_name}\n"
            f"・発言数: {user.get('message_count', 0):,}\n"
            f"・最終発言: {user.get('last_seen', '不明')}\n"
            f"・参加日時: {user.get('joined_at', '不明')}\n"
        )

        ctx.reply(text)
        return True

    def _cmd_setrole(self, ctx: MessageContext) -> bool:
        """!setrole <MID> <role> - 権限を設定（管理者のみ）"""
        args = ctx.command_args.split()
        if len(args) < 2:
            ctx.reply("❌ 使い方: !setrole <MID> <role>\n役職: banned, guest, member, trusted, moderator, admin")
            return True

        target_mid = args[0]
        role_name = args[1].lower()

        role_map = {
            "banned": Role.BANNED,
            "guest": Role.GUEST,
            "member": Role.MEMBER,
            "trusted": Role.TRUSTED,
            "moderator": Role.MODERATOR,
            "admin": Role.ADMIN,
        }

        if role_name not in role_map:
            ctx.reply(f"❌ 不正な役職: {role_name}")
            return True

        new_role = role_map[role_name]

        # 自分より上の権限は設定不可
        my_role = ctx.get_role()
        if new_role >= my_role:
            ctx.reply("❌ 自分以上の権限は設定できません")
            return True

        storage = self.bot.get_square_storage(ctx.square_mid)
        storage.set_role(target_mid, new_role)

        ctx.reply(f"✅ 権限を設定しました: {new_role.display_name}")
        return True
