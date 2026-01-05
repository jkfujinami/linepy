from linepy.base import BaseClient
from linepy.models.square import FindSquareByInvitationTicketResponse, SquareJoinMethod, SquareJoinMethodType

client = BaseClient(device="ANDROID", storage=".linepy_bot.json")
if not client.auto_login():
    print("❌ Need login")
    client.login_with_qr()

print(f"Logged in as: {client.profile.display_name}")

try:
    ticket = "vcGjO56M-9HIc2P02raGa-uQhn6UJgiQxhh6oA"
    print(f"Finding square by ticket: {ticket}")
    response = client.square.findSquareByInvitationTicketV2(ticket)
    join_type:SquareJoinMethodType = response.square.joinMethod.type_
    if join_type == SquareJoinMethodType.NONE:
        print("✅ Join square by None")
    elif join_type == SquareJoinMethodType.APPROVAL:
        print("✅ Join square by approval")
    elif join_type == SquareJoinMethodType.CODE:
        print("✅ Join square by CODE")
    else:
        print("❌ Join square by other method")



    # 構造化して表示
    print(response.model_dump_json(indent=2))

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
