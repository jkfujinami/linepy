#!/usr/bin/env python3
"""
LINEPY TalkService Verification Script

Verifies that TalkService methods correctly communicate with LINE servers
and parse responses into Pydantic models.
"""

import sys
import os
import time

# Add current directory to path
sys.path.insert(0, ".")

from linepy.base import BaseClient
from linepy.models.talk import (
    Profile,
    Contact,
    Chat,
    Settings,
    GetChatsResponse,
    GetAllChatMidsResponse,
)


def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def verify_talk_service():
    print_header("Initializing BaseClient")

    # Initialize client (uses .linepy_storage.json by default)
    client = BaseClient(device="IOSIPAD", storage=".linepy_test.json")

    # Try auto-login
    if not client.auto_login():
        print("Auto-login failed. Please login with QR code.")
        client.login_with_qr()

    if not client.is_logged_in:
        print("❌ Login failed. Exiting.")
        return

    print(f"✅ Logged in as: {client.profile.get(20) if client.profile else 'Unknown'}")

    # 1. get_profile
    print_header("1. get_profile()")
    try:
        profile = client.talk.get_profile()
        print(f"Result type: {type(profile)}")
        if isinstance(profile, Profile):
            print(f"✅ Success! Profile object received.")
            print(f"  MID: {profile.mid}")
            print(f"  Name: {profile.display_name}")
            print(f"  Status: {profile.status_message}")
        else:
            print(f"❌ Failed: Expected Profile object, got {type(profile)}")
            print(f"  Value: {profile}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()

    # 2. get_settings
    print_header("2. get_settings()")
    try:
        settings = client.talk.get_settings()
        print(f"Result type: {type(settings)}")
        if isinstance(settings, Settings):
            print(f"✅ Success! Settings object received.")
            print(f"  Noti Enabled: {settings.notification_enable}")
            print(f"  Search by ID: {settings.privacy_search_by_userid}")
        else:
            print(f"❌ Failed: Expected Settings object, got {type(settings)}")
    except Exception as e:
        print(f"❌ Error: {e}")

    # 3. get_all_contact_ids
    print_header("3. get_all_contact_ids()")
    contact_ids = []
    try:
        contact_ids = client.talk.get_all_contact_ids()
        print(f"Result type: {type(contact_ids)}")
        print(f"Found {len(contact_ids)} friends.")
        if contact_ids:
            print(f"Sample: {contact_ids[:5]}")
            print("✅ Success!")
        else:
            print("⚠️ Warning: No friends found (or empty list returned).")
    except Exception as e:
        print(f"❌ Error: {e}")

    # 4. get_contacts
    if contact_ids:
        print_header("4. get_contacts() [First 5]")
        try:
            targets = contact_ids[:5]
            contacts = client.talk.get_contacts(targets)
            print(f"Result type: {type(contacts)}")
            if (
                isinstance(contacts, list)
                and len(contacts) > 0
                and isinstance(contacts[0], Contact)
            ):
                print(f"✅ Success! List of Contact objects received.")
                for c in contacts:
                    print(f"  - {c.display_name} ({c.mid[:10]}...)")
            else:
                print(f"❌ Failed or Empty: {contacts}")
        except Exception as e:
            print(f"❌ Error: {e}")

    # 5. get_all_chat_mids
    print_header("5. get_all_chat_mids()")
    chat_mids = []
    try:
        response = client.talk.get_all_chat_mids()
        print(f"Result type: {type(response)}")
        if isinstance(response, GetAllChatMidsResponse):
            print(f"✅ Success! GetAllChatMidsResponse object received.")
            chat_mids = response.member_chat_mids
            print(f"  Joined Chats: {len(chat_mids)}")
            print(f"  Invited Chats: {len(response.invited_chat_mids)}")
            if chat_mids:
                print(f"  Sample: {chat_mids[:5]}")
        else:
            print(f"❌ Failed: Expected GetAllChatMidsResponse, got {type(response)}")
    except Exception as e:
        print(f"❌ Error: {e}")

    # 6. get_chats
    if chat_mids:
        print_header("6. get_chats() [First 5]")
        try:
            targets = chat_mids[:5]
            response = client.talk.get_chats(targets)
            print(f"Result type: {type(response)}")
            if isinstance(response, GetChatsResponse):
                print(f"✅ Success! GetChatsResponse object received.")
                for chat in response.chats:
                    # chat is now Chat object directly
                    print(f"  - {chat.chat_name or '(No Name)'} mid={chat.chat_mid}")
            else:
                print(f"❌ Failed: Expected GetChatsResponse, got {type(response)}")
        except Exception as e:
            print(f"❌ Error: {e}")
    print_header("7. E2EE Check")
    try:
        # 鍵が登録されているか確認（なければ自動登録されます）
        client.e2ee.ensure_key_registered()
        print(f"✅ E2EE Key Registered! Key ID: {client.e2ee._key_id}")

        # 公開鍵一覧の取得テスト
        keys = client.talk.get_e2ee_public_keys()
        print(f"Current Public Keys on Server: {len(keys)}")
        for k in keys:
            print(f"  - KeyID: {k.key_id} (Version: {k.version})")

    except Exception as e:
        print(f"❌ E2EE Error: {e}")

    print_header("Verify Complete")


if __name__ == "__main__":
    verify_talk_service()
