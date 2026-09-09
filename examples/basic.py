"""
LINEPY Example - Basic Usage

NOTE: This example requires a valid auth token.
      You can get one from an existing LINE login session.
"""

from linepy.base import BaseClient


def main():

    try:
        client = BaseClient(
            "DESKTOPWIN", storage=".linepy_storage.json"
        )
        client.auto_login()
        

        # Get profile
        profile = client.get_profile()
        print(f"Logged in as: {profile.display_name}")
        print(f"MID: {profile.mid}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
