#!/usr/bin/env python3
"""
LINEPY Test Script

Interactive script to test login functionality.
"""

import sys
sys.path.insert(0, ".")

from linepy import Client


def test_token_login():
    """Test login with auth token"""
    print("\n=== Token Login Test ===")
    token = input("Enter auth token (or press Enter to skip): ").strip()

    if not token:
        print("Skipped.")
        return None

    client = Client(device="DESKTOPWIN")
    try:
        client.login(auth_token=token)
        print(f"✅ Login successful!")
        return client
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return None


def test_email_login():
    """Test login with email/password"""
    print("\n=== Email Login Test ===")
    email = input("Enter email (or press Enter to skip): ").strip()

    if not email:
        print("Skipped.")
        return None

    password = input("Enter password: ").strip()
    pincode = input("Enter PIN code (default: 114514): ").strip() or "114514"

    client = Client(device="DESKTOPWIN")
    try:
        client.login_with_email(
            email=email,
            password=password,
            pincode=pincode,
        )
        print(f"✅ Login successful!")
        return client
    except Exception as e:
        print(f"❌ Login failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_qr_login():
    """Test login with QR code"""
    print("\n=== QR Code Login Test ===")
    confirm = input("Start QR login? (y/N): ").strip().lower()

    if confirm != 'y':
        print("Skipped.")
        return None

    client = Client(device="DESKTOPWIN")

    # Set up QR code callback
    @client.base.on("qrcall")
    def on_qr(url):
        print(f"\n[Login] QR Code URL: {url}")
        try:
            import qrcode
            qr = qrcode.QRCode()
            qr.add_data(url)
            qr.make()
            print("\nScanning QR Code:")
            qr.print_ascii()
        except ImportError:
            print("(Install 'qrcode' library to view QR code in terminal)")

    @client.base.on("pincall")
    def on_pin(pin):
        print(f"\n[Login] Enter PIN code: {pin}")

    try:
        client.login_with_qr()
        print(f"✅ Login successful!")
        return client
    except Exception as e:
        print(f"❌ Login failed: {e}")
        # import traceback
        # traceback.print_exc()
        return None


def test_api(client):
    """Test API calls"""
    print("\n=== API Tests ===")

    # Profile
    print("\n[getProfile]")
    try:
        profile = client.get_profile()
        print(f"  Display Name: {profile.display_name}")
        print(f"  MID: {profile.mid}")
        print(f"  Status: {profile.status_message or '(none)'}")
    except Exception as e:
        print(f"  Error: {e}")

    # Friends
    print("\n[getAllContactIds]")
    try:
        friends = client.get_all_friends()
        print(f"  Friends count: {len(friends)}")
        if friends:
            print(f"  First friend: {friends[0].display_name}")
    except Exception as e:
        print(f"  Error: {e}")

    # Chats
    print("\n[getAllChatMids]")
    try:
        chats = client.get_all_chats()
        print(f"  Chats count: {len(chats)}")
        if chats:
            print(f"  First chat: {chats[0].name or chats[0].mid}")
    except Exception as e:
        print(f"  Error: {e}")

    # Send message test
    print("\n[sendMessage]")
    to = input("  Enter MID to send test message (or Enter to skip): ").strip()
    if to:
        try:
            result = client.send_message(to, "Hello from LINEPY! 🎉")
            print(f"  ✅ Message sent!")
        except Exception as e:
            print(f"  Error: {e}")


def main():
    print("=" * 50)
    print("  LINEPY Test Script")
    print("=" * 50)

    print("\nSelect login method:")
    print("  1. Token login")
    print("  2. Email login")
    print("  3. QR code login")

    choice = input("\nChoice (1/2/3): ").strip()

    client = None
    if choice == "1":
        client = test_token_login()
    elif choice == "2":
        client = test_email_login()
    elif choice == "3":
        client = test_qr_login()
    else:
        print("Invalid choice.")
        return

    if client:
        test_api(client)

        print("\n" + "=" * 50)
        print(f"Auth Token: {client.auth_token}")
        print("=" * 50)

        client.close()

    print("\nDone!")


if __name__ == "__main__":
    main()
