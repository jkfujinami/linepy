from linepy.base import BaseClient
from linepy.models.square import FindSquareByInvitationTicketResponse

client = BaseClient(device="ANDROID", storage=".linepy_bot.json")
if not client.auto_login():
    print("❌ Need login")
    client.login_with_qr()

print(f"Logged in as: {client.profile.display_name}")

try:
    ticket = "IFW8cbNn6-FksnF2rTS-x0T_CuHJG88VxQY9zg"
    print(f"Finding square by ticket: {ticket}")
    response = client.square.findSquareByInvitationTicketV2(ticket)

    if response.chat:
        target_chat_mid = response.chat.squareChatMid
        print(f"   Chat Name: {response.chat.name}")
        print(f"   Chat MID: {target_chat_mid}")

        # Send message test
        print("Sending message...")
        try:
            print("✅ Message sent!")
            client.square.sendSquareMessage(target_chat_mid, "Hello from linepy!")

        except Exception as e:
            print(f"❌ Send Error: {e}")
    else:
        print("⚠️ No chat info in response (Join required first?)")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback

    traceback.print_exc()
