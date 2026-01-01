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

- ✅ **Login Methods**
  - QR Code Login (v1/v2) with E2EE
  - Email Login
  - Auth Token Login
  - Auto-login with persistent storage
- ✅ **Messaging**
  - Text, Image, Content types
  - Event-driven message handling (Long Polling)
- ✅ **Square (OpenChat)**
  - Join/Leave squares
  - Send/Receive messages
  - Mention, Reply, Reaction
- ✅ **Timeline / Note**
  - Create/Delete posts
  - List posts (Square Note supported)
- ✅ **Core**
  - Thrift protocol support (Binary/Compact)
  - HTTP/2 support
  - Multiple device types support

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
