#!/usr/bin/env python3
"""
LINEPY Storage/Auto-Login Test

Tests the token persistence and auto-login functionality.
"""

import sys

sys.path.insert(0, ".")

from linepy.thrift import set_debug
from linepy.base import BaseClient

# Enable debug output
set_debug(True)

# Test token (from previous successful login)
TEST_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJqdGkiOiI5ZDJlMjdjMS1iM2M2LTQ1YzEtYjlmNy0yODIwODZiZGYyOGIiLCJhdWQiOiJMSU5FIiwiaWF0IjoxNzY3MTk2MTIzLCJleHAiOjE3Njc4MDA5MjMsInNjcCI6IkxJTkVfQ09SRSIsInJ0aWQiOiJlOTQ0MWVjNS03OWI3LTRlZWMtYTk4My04OTE2OTFkZjMxODkiLCJyZXhwIjoxNzk4NzMyMTIzLCJ2ZXIiOiIzLjAiLCJhaWQiOiJ1NjEwOTA0MmMxYWUyY2MwMmY4ZmEyN2UzODUyZmQ3M2MiLCJsc2lkIjoiYzhiZjE4NDItYTZlOC00M2VkLWE0MTktNzQzMmEwYTNhNzhiIiwiZGlkIjoiTk9ORSIsImN0eXBlIjoiREVTS1RPUF9XSU4iLCJjbW9kZSI6IlNFQ09OREFSWSIsImNpZCI6IjAxMDAwMDAwMDAifQ.oJewlBGostqqO_fUXcuX5BNmkK2l97qV_rZvCeyC45k"


def test_token_login_with_save():
    """Test token login with save feature"""
    print("=" * 50)
    print("  Test 1: Login with Token & Save")
    print("=" * 50)

    client = BaseClient(device="DESKTOPWIN", storage=".linepy_test.json")

    try:
        # Login with token and save
        client.login_with_token(TEST_TOKEN, save=True)

        # Show profile
        profile = client.profile
        print(f"\n✅ Login successful!")
        print(f"  MID: {profile.get(1)}")
        print(f"  Name: {profile.get(20)}")
        print(f"  Status: {profile.get(24, '(none)')}")

        # Check storage
        print(f"\n📁 Saved to storage:")
        print(f"  auth_token: {client.token_manager.auth_token[:50]}...")
        print(f"  mid: {client.token_manager.mid}")

        return True
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        client.close()


def test_auto_login():
    """Test auto-login from saved token"""
    print("\n" + "=" * 50)
    print("  Test 2: Auto-Login from Storage")
    print("=" * 50)

    # Create new client (should read from storage)
    client = BaseClient(device="DESKTOPWIN", storage=".linepy_test.json")

    try:
        if client.auto_login():
            print(f"\n✅ Auto-login successful!")
            print(f"  MID: {client.mid}")
            print(f"  Name: {client.profile.get(20)}")
            return True
        else:
            print("\n❌ Auto-login failed: No valid token")
            return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        client.close()


def test_api_calls():
    """Test API calls after auto-login"""
    print("\n" + "=" * 50)
    print("  Test 3: API Calls")
    print("=" * 50)

    client = BaseClient(device="DESKTOPWIN", storage=".linepy_test.json")

    try:
        if not client.auto_login():
            print("❌ Need to login first!")
            return False

        # Get friends
        print("\n[getAllContactIds]")
        friends = client.get_all_contact_ids()
        print(f"  Friends count: {len(friends)}")

        # Get chats
        print("\n[getAllChatMids]")
        chats = client.get_all_chat_mids()
        print(f"  Chats: {chats}")

        return True
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        client.close()


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  LINEPY Storage Test")
    print("=" * 50 + "\n")

    # Test 1: Login and save
    if test_token_login_with_save():
        # Test 2: Auto-login
        if test_auto_login():
            # Test 3: API calls
            test_api_calls()

    print("\nDone!")
