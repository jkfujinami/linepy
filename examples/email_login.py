"""
LINEPY Example - Email Login

Login with email and password.
"""

from linepy import Client


def main():
    # Create client (DESKTOPWIN for v3 login, supports token refresh)
    client = Client(device="DESKTOPWIN")

    # Login with email/password
    # Note: You need to enter the PIN code displayed in the terminal
    #       on another logged-in device within 2 minutes
    email = "your_email@example.com"
    password = "your_password"

    try:
        # Custom pincode (optional, default is "114514")
        # This pincode will be displayed and you need to enter it
        # on another device to confirm the login
        client.login_with_email(
            email=email,
            password=password,
            pincode="123456",  # 6-digit PIN
            e2ee=True,  # Enable E2EE (recommended)
        )

        # After successful login, you can use the client
        profile = client.get_profile()
        print(f"Logged in as: {profile.display_name}")
        print(f"MID: {profile.mid}")

        # The auth token can be saved for future logins
        print(f"\nAuth Token: {client.auth_token}")
        print("Save this token for future quick logins!")

    except Exception as e:
        print(f"Login failed: {e}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
