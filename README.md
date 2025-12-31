# LINEPY

LINE SelfBot library for Python - A port of [linejs](https://github.com/evex-dev/linejs)

## Installation

```bash
pip install -e .
```

## Quick Start

```python
from linepy import Client

# Create client
client = Client(device="DESKTOPWIN")

# Login with auth token
client.login(auth_token="YOUR_TOKEN")

# Get profile
profile = client.get_profile()
print(f"Logged in as: {profile.display_name}")

# Send message
client.send_message("USER_MID", "Hello!")

# Event-driven bot
@client.on("message")
def on_message(msg):
    if msg.text == "!ping":
        msg.reply("pong!")

client.poll()  # Start listening
```

## Features

- ✅ Thrift protocol support (Binary/Compact)
- ✅ Multiple device types (DESKTOPWIN, DESKTOPMAC, IOS, ANDROID, etc.)
- ✅ Synchronous API (no asyncio!)
- ✅ Event-driven message handling
- 🚧 QR code login (WIP)
- 🚧 E2EE encryption (WIP)
- 🚧 Square/OpenChat support (WIP)

## Supported Devices

| Device | Status |
|--------|--------|
| DESKTOPWIN | ✅ |
| DESKTOPMAC | ✅ |
| IOS | ✅ |
| IOSIPAD | ✅ |
| ANDROID | ✅ |
| WATCHOS | ✅ |
| WEAROS | ✅ |

## References

- [linejs](https://github.com/evex-dev/linejs) - Original JavaScript library
- [CHRLINE](https://github.com/DeachSword/CHRLINE) - Python reference implementation

## License

MIT
