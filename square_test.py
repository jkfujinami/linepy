from linepy.base import BaseClient
from linepy.models.square import FindSquareByInvitationTicketResponse

client = BaseClient(device="IOSIPAD", storage=".linepy_test.json")
if not client.auto_login():
    print("❌ Need login")
    client.login_with_qr()

print(f"Logged in as: {client.profile.display_name}")

try:
    ticket = "juhuuv_G3WCk1KRUeJKpRKCi_9mx9lB4lJJ2dQ"
    print(f"Finding square by ticket: {ticket}")
    response = client.square.find_square_by_invitation_ticket(ticket)

    if response.chat:
        target_chat_mid = response.chat.squareChatMid
        print(f"   Chat Name: {response.chat.name}")
        print(f"   Chat MID: {target_chat_mid}")

        # Send message test
        print("Sending message...")
        try:
            res = client.square.send_message(target_chat_mid, "Hello from LINEPY!")
            print("✅ Message sent!")
            print(res)
        except Exception as e:
            print(f"❌ Send Error: {e}")
    else:
        print("⚠️ No chat info in response (Join required first?)")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback

    traceback.print_exc()
