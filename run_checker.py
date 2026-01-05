# -*- coding: utf-8 -*-
"""
既読チェッカー実行スクリプト

ReadChecker と SquareHelper (Polling) を分離した構成。
"""

import time
from linepy.base import BaseClient
from linepy.models.square import SquareEventType, SquareEvent
from linepy.helpers.square import SquareEventData
from checker import ReadChecker


def main():
    # ========== クライアント初期化 ==========
    client = BaseClient(device="ANDROID", storage=".linepy_bot.json")

    if not client.auto_login():
        print("❌ Login failed")
        return

    print(f"✅ Logged in as: {client.profile.display_name}")

    # ========== ReadChecker初期化 ==========
    checker = ReadChecker(client)
    helper = client.square_helper

    # ========== PUSHイベントハンドラ ==========

    def on_push_event(service_type: int, event: SquareEvent):
        """LEGY Push からのイベント処理"""
        # B案: SquareEventData を使ってパース
        data = SquareEventData.from_event(event)

        if data.square_event_type == SquareEventType.RECEIVE_MESSAGE:
            checker.on_message_event(data)

            # デバッグ用: メッセージ表示
            if data.message_text:
                print(f"[MSG] {data.sender_name or '???'}: {data.message_text[:50]}")

        elif data.square_event_type == SquareEventType.NOTIFIED_MARK_AS_READ:
            checker.on_read_event(event)

    # ========== 監視対象チャット ==========
    TICKETS = [
        "UR6dTLsc8irzY8NrGGAD9YxnojotqNt_3EgHsQ",
    ]

    TARGET_CHATS = []
    for ticket in TICKETS:
        try:
            mid = helper.getSquareChatMidbyInvitationTicket(ticket)
            TARGET_CHATS.append(mid)
            print(f"📌 Watching Chat: {mid} (Ticket: {ticket[:10]}...)")
        except Exception as e:
            print(f"⚠️ Could not get MID for ticket {ticket}: {e}")

    if not TARGET_CHATS:
        print("❌ No chats to watch. Exiting.")
        return
    # ========== Push開始 ==========
    print(f"📡 Starting LEGY Push for {len(TARGET_CHATS)} chat(s)...")
    # fetch_type=2 (PREFETCH_BY_SERVER) で既読イベントなどを確実に取得
    client.start_push(TARGET_CHATS, on_event=on_push_event, fetch_type=1)

    print("\n既読チェッカー起動中 (LEGY Push) - Ctrl+C で停止")
    print("コマンド: 既読ポイント設置 / 既読確認 / 既読ポイント確認 / 既読無視 / 既読リセット")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping Push...")
        client.stop_push()
        print("終了しました")


if __name__ == "__main__":
    main()
