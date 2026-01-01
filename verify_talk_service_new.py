
import sys
import os

# Add parent directory to path to import linepy
sys.path.append(os.path.join(os.path.dirname(__file__)))

from linepy import BaseClient

def test_talk():
    try:
        # Initialize Client
        client = BaseClient("IOSIPAD", storage=".linepy_test.json")

        if not client.auto_login():
            print("Please login first.")
            return

        print(f"Testing TalkService for: {client.profile.display_name}")

        # Test 1: get_profile (Simple call)
        profile = client.talk.get_profile()
        print(f"Successfully got profile: {profile.display_name}")

        # Test 2: sync (In SyncService)
        print("Testing sync.sync()...")
        sync_res = client.sync.sync(last_revision=0, count=100)
        print(f"Successfully called sync.sync(), rev: {sync_res.operation_response.revision if sync_res.operation_response else 'N/A'}")

        # Test 3: get_chats (Nested List call)
        print("Testing get_chats()...")
        # Just use an empty list to see if it doesn't crash
        chats = client.talk.get_chats(chat_mids=[])
        print(f"Successfully called get_chats()")

    except Exception as e:
        print(f"TalkService Test Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_talk()
