# -*- coding: utf-8 -*-
"""
Bot core for LINE OC Bot

Bot本体 - イベントディスパッチャー
"""

import logging
import time
from pathlib import Path
from typing import Dict, List, Type, Optional, Callable, Any

from linepy.base import BaseClient
from linepy.models.square import SquareEvent, SquareEventType
from linepy.helpers.square import SquareEventData

from .storage import ChatStorage, SquareStorage, GlobalStorage, Role
from .context import MessageContext, ReadContext, JoinContext, LeaveContext
from .base import BaseModule

logger = logging.getLogger("line_bot")


class Bot:
    """
    LINE OC Bot 本体

    イベントを受け取り、登録されたモジュールにディスパッチする。

    Example:
        client = BaseClient(device="ANDROID", storage=".bot_storage.json")
        client.auto_login()

        bot = Bot(client)
        bot.register(TestModule)
        bot.start(["m1234...", "m5678..."])
    """

    def __init__(
        self,
        client: BaseClient,
        data_dir: Path = Path("data"),
    ):
        self.client = client
        self.data_dir = Path(data_dir)

        # モジュール
        self.modules: List[BaseModule] = []

        # ストレージ
        self.global_storage = GlobalStorage(self.data_dir)
        self._chat_storages: Dict[str, ChatStorage] = {}
        self._square_storages: Dict[str, SquareStorage] = {}

        # chat_mid → square_mid マッピング
        self._chat_to_square: Dict[str, str] = {}

        # 監視中のチャット
        self.watched_chats: List[str] = []

    # ========== モジュール管理 ==========

    def register(self, module_class: Type[BaseModule]) -> None:
        """モジュールを登録（優先度順にソート）"""
        module = module_class(self)
        self.modules.append(module)
        # 優先度が高い順にソート
        self.modules.sort(key=lambda m: m.priority, reverse=True)
        module.on_load()
        logger.info("Module registered: %s (priority=%d)", module.name, module.priority)

    def unregister(self, module_name: str) -> bool:
        """モジュールを登録解除"""
        for i, module in enumerate(self.modules):
            if module.name == module_name:
                module.on_unload()
                del self.modules[i]
                logger.info("Module unregistered: %s", module_name)
                return True
        return False

    def get_module(self, module_name: str) -> Optional[BaseModule]:
        """モジュールを取得"""
        for module in self.modules:
            if module.name == module_name:
                return module
        return None

    # ========== ストレージ管理 ==========

    def get_storage(self, chat_mid: str) -> ChatStorage:
        """チャット（部屋）のストレージを取得"""
        if chat_mid not in self._chat_storages:
            self._chat_storages[chat_mid] = ChatStorage(chat_mid, self.data_dir)
        return self._chat_storages[chat_mid]

    def get_square_storage(self, square_mid: str) -> SquareStorage:
        """Square（OC全体）のストレージを取得（権限管理用）"""
        if square_mid not in self._square_storages:
            self._square_storages[square_mid] = SquareStorage(square_mid, self.data_dir)
        return self._square_storages[square_mid]

    def get_square_mid(self, chat_mid: str) -> Optional[str]:
        """SquareChatMid から SquareMid を取得"""
        return self._chat_to_square.get(chat_mid)

    def _fetch_square_mid(self, chat_mid: str) -> Optional[str]:
        """APIから SquareMid を取得してキャッシュ"""
        if chat_mid in self._chat_to_square:
            return self._chat_to_square[chat_mid]

        try:
            res = self.client.square.getSquareChat(chat_mid)
            if res.squareChat and res.squareChat.squareMid:
                square_mid = res.squareChat.squareMid
                self._chat_to_square[chat_mid] = square_mid
                logger.debug("Cached mapping: %s -> %s", chat_mid[:12], square_mid[:12])
                return square_mid
        except Exception as e:
            logger.warning("Failed to get SquareMid for %s: %s", e)

        return None

    # ========== イベント処理 ==========

    def _on_push_event(self, service_type: int, event: SquareEvent) -> None:
        """Push イベントを処理"""
        try:
            data = SquareEventData.from_event(event)

            # デバッグ: イベントタイプを表示
            logger.debug("[EVENT] type=%s chat=%s", data.square_event_type, data.square_chat_mid[:12] if data.square_chat_mid else "?")

            if data.square_event_type == SquareEventType.RECEIVE_MESSAGE:
                self._handle_message(data, event)

            elif data.square_event_type == SquareEventType.NOTIFIED_MARK_AS_READ:
                self._handle_read(data, event)

            elif data.square_event_type == SquareEventType.NOTIFIED_JOIN_SQUARE_CHAT:
                self._handle_join(data, event)

            elif data.square_event_type == SquareEventType.NOTIFIED_LEAVE_SQUARE_CHAT:
                self._handle_leave(data, event)

        except Exception as e:
            logger.exception("Error handling event: %s", e)

    def _handle_message(self, data: SquareEventData, event: SquareEvent) -> None:
        """メッセージイベントを処理"""
        # デバッグ: メッセージ内容を表示
        logger.debug("[MSG] from=%s text=%s", data.sender_name, data.message_text[:30] if data.message_text else "(empty)")

        if not data.square_chat_mid or not data.message_text:
            logger.debug("[MSG] Skipped: chat_mid=%s text=%s", data.square_chat_mid, data.message_text)
            return
        if not data.square_chat_mid:
            logger.debug("[MSG] Skipped: chat_mid=%s", data.square_chat_mid)
            return
        if data.message_text:
            self.client.square.markAsRead(data.square_chat_mid, data.message_id)


        # SquareMid を取得
        square_mid = self._fetch_square_mid(data.square_chat_mid)
        if not square_mid:
            logger.warning("[MSG] Could not get SquareMid for %s", data.square_chat_mid[:12])
            return

        # SquareStorage でユーザーデータを更新（権限管理はOC単位）
        square_storage = self.get_square_storage(square_mid)
        square_storage.increment_message_count(data.member_mid)

        if data.sender_name:
            square_storage.update_display_name(data.member_mid, data.sender_name)
        print(data.message_text)
        # コンテキストを作成
        ctx = MessageContext(
            bot=self,
            chat_mid=data.square_chat_mid,
            square_mid=square_mid,
            sender_mid=data.member_mid,
            sender_name=data.sender_name or "???",
            message_id=data.message_id,
            text=data.message_text,
            content_type=data.content_type or 0,
            mentions=data.mention_mids,
            raw_event=event,
        )

        logger.debug("[MSG] Context created: text='%s' command='%s'", ctx.text, ctx.command)

        # モジュールにディスパッチ
        for module in self.modules:
            try:
                if module.on_message(ctx):
                    break  # 処理完了
            except Exception as e:
                logger.exception("Error in module %s: %s", module.name, e)

    def _handle_read(self, data: SquareEventData, event: SquareEvent) -> None:
        """既読イベントを処理"""
        if not data.square_chat_mid:
            return

        square_mid = self.get_square_mid(data.square_chat_mid) or ""

        ctx = ReadContext(
            bot=self,
            chat_mid=data.square_chat_mid,
            square_mid=square_mid,
            reader_mid=data.member_mid,
            message_id=data.message_id,
        )

        for module in self.modules:
            try:
                module.on_read(ctx)
            except Exception as e:
                logger.exception("Error in module %s on_read: %s", module.name, e)

    def _handle_join(self, data: SquareEventData, event: SquareEvent) -> None:
        """入室イベントを処理"""
        # 入室したメンバー情報を取得
        member_mid = None
        member_name = None

        if event.payload and event.payload.notifiedJoinSquareChat:
            join_data = event.payload.notifiedJoinSquareChat
            if join_data.joinedMember:
                member_mid = join_data.joinedMember.squareMemberMid
                member_name = join_data.joinedMember.displayName

        if not member_mid:
            return

        square_mid = self._fetch_square_mid(data.square_chat_mid)
        if not square_mid:
            return

        # SquareStorage に参加日時を記録
        square_storage = self.get_square_storage(square_mid)
        square_storage.set_joined_at(member_mid)

        ctx = JoinContext(
            bot=self,
            chat_mid=data.square_chat_mid,
            square_mid=square_mid,
            member_mid=member_mid,
            member_name=member_name or "???",
        )

        for module in self.modules:
            try:
                module.on_join(ctx)
            except Exception as e:
                logger.exception("Error in module %s on_join: %s", module.name, e)

    def _handle_leave(self, data: SquareEventData, event: SquareEvent) -> None:
        """退室イベントを処理"""
        member_mid = None
        member_name = None

        if event.payload and event.payload.notifiedLeaveSquareChat:
            leave_data = event.payload.notifiedLeaveSquareChat
            member_mid = leave_data.squareMemberMid
            if leave_data.squareMember:
                member_name = leave_data.squareMember.displayName

        if not member_mid:
            return

        square_mid = self.get_square_mid(data.square_chat_mid) or ""

        ctx = LeaveContext(
            bot=self,
            chat_mid=data.square_chat_mid,
            square_mid=square_mid,
            member_mid=member_mid,
            member_name=member_name or "???",
        )

        for module in self.modules:
            try:
                module.on_leave(ctx)
            except Exception as e:
                logger.exception("Error in module %s on_leave: %s", module.name, e)

    # ========== 起動 ==========

    def start(self, chat_mids: List[str], fetch_type: int = 2) -> None:
        """
        Bot を開始

        Args:
            chat_mids: 監視するチャットMIDのリスト
            fetch_type: 1=Default, 2=Prefetch by Server (推奨)
        """
        self.watched_chats = chat_mids

        logger.info("Starting bot with %d chat(s)...", len(chat_mids))
        self.client.start_push(
            chat_mids,
            on_event=self._on_push_event,
            fetch_type=fetch_type,
        )

    def stop(self) -> None:
        """Bot を停止"""
        logger.info("Stopping bot...")
        self.client.stop_push()

        # モジュールをアンロード
        for module in self.modules:
            try:
                module.on_unload()
            except Exception as e:
                logger.exception("Error unloading module %s: %s", module.name, e)
