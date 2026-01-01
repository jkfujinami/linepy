import time
import sys
import os

# Add parent directory to path to import linepy
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from linepy import BaseClient
from linepy.models.square import SquareEvent


def main():
    try:
        # Initialize Client
        client = BaseClient(
            "IOSIPAD", storage="/Users/fujinami/github/linepy/.linepy_test.json"
        )

        if not client.auto_login():
            print("Please login with QR code.")
            client.login(qr=True)
            print(f"Login successful. Auth Token: {client.auth_token}")

        # Display profile
        profile = client.get_profile()
        print(f"Logged in as: {profile.display_name}")

        # Start Polling
        start_polling(client)

    except Exception as e:
        print(f"Unhandled exception: {e}")


def start_polling(client: BaseClient):
    sync_token = None
    print("Starting Square polling loop... (Press Ctrl+C to stop)")

    while True:
        try:
            # Flat argument style: No need for FetchMyEventsRequest!
            response = client.square.fetch_my_events(
                subscription_id=0, sync_token=sync_token, limit=50
            )

            # Update sync token
            if response.sync_token:
                sync_token = response.sync_token

            # Process events
            for event in response.events:
                handle_event(client, event)

            time.sleep(1)  # Wait 1 second between polls

        except KeyboardInterrupt:
            print("\nPolling stopped.")
            break
        except Exception as e:
            print(f"Error in polling loop: {e}")
            import traceback

            traceback.print_exc()
            time.sleep(5)  # Wait before retrying


def handle_event(client, event: SquareEvent):
    payload = event.payload
    if not payload:
        return
    print("event:", payload.model_dump_json(indent=2, exclude_none=True))


if __name__ == "__main__":
    main()
