# -*- coding: utf-8 -*-
"""
既読チェッカー for LINEPY

Square (OpenChat) の既読状況を追跡・確認するツール。

使い方:
    from linepy.base import BaseClient
    from checker import ReadChecker

    client = BaseClient(device="ANDROID", storage=".linepy_bot.json")
    client.auto_login()

    checker = ReadChecker(client)

    # ポーリングループから呼び出す
    checker.on_read_event(event)      # 既読イベント
    checker.on_message_event(event)   # メッセージイベント
"""

from typing import Dict, List, Optional, Any, Union
from linepy.base import BaseClient
from linepy.helpers.square import SquareEventData
from linepy.models.square import SquareEvent, SquareEventNotifiedMarkAsRead


class ReadChecker:
    """
    既読チェッカー（ロジックのみ）

    Push / Polling からイベントを受け取り、このクラスに渡す。

    機能:
    - 「既読ポイント設置」: チェックポイントを設定
    - 「既読確認」: 最新メッセージの既読者を確認
    - 「既読ポイント確認」: チェックポイント以降の既読者を確認
    - 「既読無視」: 既読したが発言していないメンバーを表示
    - 「既読リセット」: 既読追跡をリセット
    """

    def __init__(self, client: BaseClient):
        self.client = client
        self.square = client.square

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

    # ========== 外部から呼び出すメソッド ==========

    def on_read_event(self, event: SquareEvent) -> None:
        """
        既読イベントを処理 (Type 6)

        Args:
            data: SquareEventData オブジェクト
        """
        try:
            MaekAsRead:SquareEventNotifiedMarkAsRead = event.payload.notified_mark_as_read
            square_chat_mid = MaekAsRead.square_chat_mid
            member_mid = MaekAsRead.s_member_mid
            message_id = MaekAsRead.message_id
            if not all([square_chat_mid, member_mid, message_id]):
                return

            message_id_int = int(message_id) if isinstance(message_id, str) else message_id

            # チェックポイント追跡
            checkpoint = self._get_checkpoint(square_chat_mid)
            if (checkpoint["mode"] and
                checkpoint["message_id"] is not None and
                message_id_int > checkpoint["message_id"] and
                member_mid not in checkpoint["read_list"]):

                checkpoint["read_list"].append(member_mid)

                if member_mid not in checkpoint["not_bad_list"]:
                    if member_mid not in checkpoint["bad_list"]:
                        checkpoint["bad_list"].append(member_mid)

            # 最新メッセージ既読追跡
            # message_id >= latest["message_id"] で既読とみなす（完全一致でなくてもOK）
            latest = self._get_latest_reads(square_chat_mid)
            if (latest["message_id"] is not None and
                message_id_int >= latest["message_id"] and
                member_mid not in latest["read_list"]):
                latest["read_list"].append(member_mid)

        except Exception as e:
            print(f"[ReadChecker] Error in on_read_event: {e}")

    def on_message_event(self, data: SquareEventData) -> None:
        """
        メッセージイベントを処理 (Type 1/0)

        Args:
            data: SquareEventData オブジェクト
        """
        try:
            square_chat_mid = data.square_chat_mid
            text = data.message_text or ""
            message_id = data.message_id
            sender_mid = data.member_mid

            if not square_chat_mid:
                return

            message_id_int = int(message_id) if message_id else 0

            # コマンド処理
            self._handle_command(square_chat_mid, text, message_id_int, sender_mid)

            # 最新メッセージIDを更新
            latest = self._get_latest_reads(square_chat_mid)
            latest["message_id"] = message_id_int
            latest["read_list"] = []

            # 発言者を「既読無視」リストから除外
            checkpoint = self._get_checkpoint(square_chat_mid)
            if checkpoint["message_id"] is not None and sender_mid:
                if sender_mid in checkpoint["bad_list"]:
                    checkpoint["bad_list"].remove(sender_mid)
                if sender_mid not in checkpoint["not_bad_list"]:
                    checkpoint["not_bad_list"].append(sender_mid)

        except Exception as e:
            print(f"[ReadChecker] Error in on_message_event: {e}")

    def _handle_command(self, chat_mid: str, text: str, message_id: int, sender_mid: str):
        """コマンドを処理"""
        checkpoint = self._get_checkpoint(chat_mid)

        if text == "既読ポイント設置":
            checkpoint["mode"] = True
            checkpoint["message_id"] = message_id
            checkpoint["read_list"] = []
            checkpoint["bad_list"] = []
            checkpoint["not_bad_list"] = []
            self._reply(chat_mid, "✅ 既読ポイントを設置しました", message_id)

        elif text == "既読確認":
            latest = self._get_latest_reads(chat_mid)
            names = self._get_names(latest["read_list"])
            self._reply(chat_mid, f"📖 既読メンバー ({len(latest['read_list'])}人)\n{names}", message_id)

        elif text == "既読ポイント確認":
            if checkpoint["message_id"] is None:
                self._reply(chat_mid, "⚠️ 既読ポイントが未設置です", message_id)
            else:
                names = self._get_names(checkpoint["read_list"])
                self._reply(chat_mid, f"📖 既読メンバー ({len(checkpoint['read_list'])}人)\n{names}", message_id)

        elif text == "既読無視":
            if checkpoint["message_id"] is None:
                self._reply(chat_mid, "⚠️ 既読ポイントが未設置です", message_id)
            else:
                names = self._get_names(checkpoint["bad_list"])
                self._reply(chat_mid, f"👀 既読無視 ({len(checkpoint['bad_list'])}人)\n{names}", message_id)

        elif text == "既読リセット":
            checkpoint["mode"] = False
            checkpoint["message_id"] = None
            checkpoint["read_list"] = []
            checkpoint["bad_list"] = []
            checkpoint["not_bad_list"] = []
            self._reply(chat_mid, "🔄 リセットしました", message_id)

    def _get_names(self, mids: List[str]) -> str:
        """メンバー名一覧を取得"""
        if not mids:
            return "（なし）"

        names = []
        for mid in mids[:30]:
            try:
                m = self.square.getSquareMember(squareMemberMid=mid)
                name = m.square_member.display_name
                names.append(f"・{name}")
            except:
                names.append("・???")

        if len(mids) > 30:
            names.append(f"...他{len(mids)-30}人")

        return "\n".join(names)

    def _reply(self, chat_mid: str, text: str, reply_to: int):
        """返信"""
        try:
            self.square.sendSquareMessage(
                squareChatMid=chat_mid,
                text=text,
                relatedMessageId=str(reply_to)
            )
        except Exception as e:
            print(f"[ReadChecker] Reply failed: {e}")
