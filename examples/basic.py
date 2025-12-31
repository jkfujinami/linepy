"""
LINEPY Example - Basic Usage

NOTE: This example requires a valid auth token.
      You can get one from an existing LINE login session.
"""

from linepy import Client


def main():
    # Create client
    client = Client(device="DESKTOPWIN")

    # Login with auth token
    # Get your auth token from CHRLINE or other means
    auth_token = "YOUR_AUTH_TOKEN_HERE"

    try:
        client.login(auth_token=auth_token)

        # Get profile
        profile = client.get_profile()
        print(f"Logged in as: {profile.display_name}")
        print(f"MID: {profile.mid}")

        # Get friends
        friends = client.get_all_friends()
        print(f"Friends count: {len(friends)}")

        # Get chats
        chats = client.get_all_chats()
        print(f"Chats count: {len(chats)}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
