# -*- coding: utf-8 -*-
"""
LINE OC Bot - メインエントリーポイント

Usage:
    python main.py
"""

import logging
import sys
import time
from pathlib import Path

# linepy をインポートできるようにパスを追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import Bot
from core.watch_storage import WatchStorage
from modules import (
    AdminModule,
    BanHandlerModule,
    JoinModule,
    RateLimiterModule,
    ReadCheckerModule,
    TestModule,
)

from linepy import BaseClient

# ログ設定（DEBUGで詳細ログ、INFOで通常）
logging.basicConfig(
    level=logging.DEBUG ,  # 開発中はDEBUG、本番はINFOに変更
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
# httpx 関連のログは多すぎるので抑制
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("hpack").setLevel(logging.WARNING)
logger = logging.getLogger("line_bot")


# ========== 設定 ==========

# 監視するチャットのチケット
CHAT_TICKETS = [
    "UR6dTLsc8irzY8NrGGAD9YxnojotqNt_3EgHsQ",  # ここを変更
]

# グローバル管理者（MID）
GLOBAL_ADMINS = [
    # "p1234...",  # 管理者のMIDを追加
]


def main():
    # クライアント初期化
    client = BaseClient(
        device="ANDROID",
        storage=".linepy_bot.json",
    )

    # ログイン
    if not client.auto_login():
        print("❌ Auto-login failed. Starting QR login...")
        client.login_with_qr()

    print(f"✅ Logged in as: {client.profile.display_name}")

    # Bot 初期化
    bot = Bot(client, data_dir=Path("data"))

    # グローバル管理者を設定
    for admin_mid in GLOBAL_ADMINS:
        bot.global_storage.add_global_admin(admin_mid)

    # モジュール登録
    bot.register(BanHandlerModule)
    bot.register(RateLimiterModule)
    bot.register(AdminModule)
    bot.register(TestModule)
    bot.register(ReadCheckerModule)
    bot.register(JoinModule)

    # チャットMIDを取得
    chat_mids = []
    helper = client.square_helper

    for ticket in CHAT_TICKETS:
        try:
            mid = helper.getSquareChatMidbyInvitationTicket(ticket)
            chat_mids.append(mid)
            print(f"📌 Watching: {mid[:16]}... (Ticket: {ticket[:10]}...)")
        except Exception as e:
            print(f"⚠️ Could not get MID for ticket {ticket[:10]}...: {e}")

    # ストレージから保存済みチャットを読み込んでマージ
    watch_storage = WatchStorage()
    stored_chats = watch_storage.get_watched()
    for mid in stored_chats:
        if mid not in chat_mids:
            chat_mids.append(mid)
            print(f"📌 Watching (stored): {mid[:16]}...")

    if not chat_mids:
        print("❌ No chats to watch. Exiting.")
        return

    # 開始
    print(f"\n🚀 Starting bot with {len(chat_mids)} chat(s)...")
    print("Commands: !test, !myid, !stats")
    print("Press Ctrl+C to stop.\n")

    bot.start(chat_mids, fetch_type=2)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping bot...")
        bot.stop()
        print("👋 Bye!")


if __name__ == "__main__":
    main()
