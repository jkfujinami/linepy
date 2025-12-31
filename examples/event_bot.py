"""
LINEPY Example - Event-driven Bot

This example shows how to create an event-driven bot.
"""

from linepy import Client


def main():
    client = Client(device="DESKTOPWIN")

    # Login
    auth_token = "YOUR_AUTH_TOKEN_HERE"
    client.login(auth_token=auth_token)

    # Register event handlers
    @client.on("message")
    def on_message(msg):
        """Handle incoming messages"""
        print(f"[{msg.from_}] {msg.text}")

        # Simple command handler
        if msg.text == "!ping":
            msg.reply("pong!")

        elif msg.text == "!help":
            msg.reply("Available commands:\n!ping - Pong!\n!help - Show this help")

        elif msg.text and msg.text.startswith("!echo "):
            text = msg.text[6:]
            msg.reply(text)

    @client.on("event")
    def on_event(event):
        """Handle other events"""
        print(f"Event: {event}")

    print("Bot started! Press Ctrl+C to stop.")

    try:
        # Start polling (blocking)
        client.poll()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        client.close()


if __name__ == "__main__":
    main()
