"""
LINEPY Example - QR Code Login

Login with QR code (scan from LINE mobile app).
"""

from linepy import Client


def main():
    # Create client
    client = Client(device="DESKTOPWIN")

    # Set up event handlers for QR code
    @client.base.on("pincall")
    def pincall(pincode):
        """Called when PIN code verification is needed"""
        print(f"\n🔐 Enter this PIN code on your device: {pincode}")

    @client.base.on("qrcall")
    def qrcall(url):
        """Called when QR code is ready"""
        print(f"\n📱 Scan this QR code with LINE app:")
        print(f"   {url}")
        print("\n   Or open the URL in your browser to view the QR code")

    try:
        # QR code login
        # The QR code URL will be printed to console
        # Scan it with LINE mobile app
        client.login_with_qr()

        # After successful login
        profile = client.get_profile()
        print(f"\n✅ Logged in as: {profile.display_name}")
        print(f"   MID: {profile.mid}")

        # Save auth token for future logins
        print(f"\n💾 Auth Token: {client.auth_token}")

    except Exception as e:
        print(f"Login failed: {e}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
