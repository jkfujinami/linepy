# -*- coding: utf-8 -*-
"""
LEGY Push 動作確認テストスクリプト

リアルタイムでイベントを取得し、プロトコルの中身を整形して表示します。
"""

import time
import json
from linepy.base import BaseClient
from linepy.push.data import ServiceType


def format_event(event):
    """イベント内容を読みやすく整形"""
    if isinstance(event, dict):
        return json.dumps(event, indent=2, ensure_ascii=False)
    return str(event)


from linepy.models.square import SquareEventType, SquareEvent
from linepy.helpers.square import SquareEventData

def on_push_event(service_type: int, event: SquareEvent):
    """Callback for push events."""
    print("=" * 50)
    print(f"🔔 PUSH EVENT RECEIVED (Service: {service_type})")

    # Parse event using Helper dataclass
    data = SquareEventData.from_event(event)

    if data.square_event_type == SquareEventType.RECEIVE_MESSAGE:
        print(f"📩 MESSAGE (RECEIVE_MESSAGE):")
        print(f"   From: {data.member_mid}")
        print(f"   Name: {data.sender_name}")
        print(f"   Text: {data.message_text or '(No Text/Content)'}")
        print(f"   ID:   {data.message_id}")

    elif data.square_event_type == SquareEventType.NOTIFIED_MARK_AS_READ:
        # Note: NOTIFIED_MARK_AS_READ logic wasn't fully added to SquareEventData yet,
        # so we might need to fallback or add it to helper.
        # But for now let's just show what we have or raw event slightly.
        if event.payload.notifiedMarkAsRead:
            read = event.payload.notifiedMarkAsRead
            print(f"👀 READ MARK (NOTIFIED_MARK_AS_READ):")
            print(f"   Mid: {read.sMemberMid}")
            print(f"   MsgId: {read.messageId}")

    elif data.square_event_type == SquareEventType.NOTIFIED_JOIN_SQUARE_CHAT:
        print(f"👋 JOIN (NOTIFIED_JOIN_SQUARE_CHAT)")
        print(f"   SquareChatMid: {data.square_chat_mid or event.payload.notifiedJoinSquareChat.squareChatMid}")

    elif data.square_event_type == SquareEventType.NOTIFIED_LEAVE_SQUARE_CHAT:
        print(f"👋 LEAVE (NOTIFIED_LEAVE_SQUARE_CHAT)")

    else:
        print(f"📦 OTHER EVENT: {data.square_event_type}")

    print("=" * 50)
    print("="*50 + "\n")


def main():
    print("🚀 Initializing Client...")

    # クライアント初期化 (ANDROIDモード)
    client = BaseClient(device="ANDROID", storage=".linepy_bot.json")

    if not client.auto_login():
        print("❌ Login failed. Check your token or storage.")
        return

    print(f"✅ Logged in as: {client.profile.display_name}")

    # 監視するチャットのリスト
    # 前回のやり取りで使われていたチケットからMIDを取得
    TICKETS = [
        "AaZkPfqiE4Z43tj1794ZSkmRxaeStw_Qu-nRxA",
        "UR6dTLsc8irzY8NrGGAD9YxnojotqNt_3EgHsQ",
        "IFW8cbNn6-FksnF2rTS-x0T_CuHJG88VxQY9zg"
    ]

    chat_mids = []
    helper = client.square_helper

    for ticket in TICKETS:
        try:
            mid = helper.getSquareChatMidbyInvitationTicket(ticket)
            chat_mids.append(mid)
            print(f"📌 Watching Chat: {mid} (Ticket: {ticket[:10]}...)")
        except Exception as e:
            print(f"⚠️ Could not get MID for ticket {ticket}: {e}")

    if not chat_mids:
        print("❌ No chats to watch. Exiting.")
        return

    # LEGY Push 開始
    print(f"📡 Starting LEGY Push for {len(chat_mids)} chats...")
    # fetch_type=2 (PREFETCH_BY_SERVER) to try getting full data including sender names
    client.start_push(chat_mids, on_event=on_push_event, fetch_type=2)

    print("\n🎧 Listener is active. Send a message to the Square chat to test.")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping Push...")
        client.stop_push()
        print("Done.")


if __name__ == "__main__":
    main()
