# LINEPY

A pure-Python LINE SelfBot library. It communicates directly with LINE's internal Thrift-based API.

## Features
- **100% Pure Python**: No C or Rust extensions. Runs anywhere, including sandboxed environments like iOS (a-Shell).
- **Comprehensive API**: Supports Login, E2EE, Messaging, Square (OpenChat), and Timeline.
- **Multiple Login Methods**: QR code, Email/Password, or Auth Token.

## Installation

```bash
git clone https://github.com/your_repo/linepy.git
cd linepy
pip install .
```

## Quick Start

```python
from linepy import Client

client = Client(device="DESKTOPWIN")

# 1. Login (scans QR code on first run, uses saved token later)
client.login(qr=True)

# 2. Print profile
profile = client.get_profile()
print(f"Logged in as: {profile.display_name}")

# 3. Send a message
client.send_message("USER_MID", "Hello!")

# 4. Listen for messages (Echo bot)
@client.on("message")
def on_message(msg):
    if msg.text == "!ping":
        msg.reply("pong!")

client.listen()
```

## Advanced Usage (`BaseClient`)

For fine-grained control or specific RPC calls, use `BaseClient`. Most scripts in the `examples/` folder use this approach.

```python
from linepy.base import BaseClient

client = BaseClient("DESKTOPWIN")
if not client.auto_login():
    client.login_with_qr()

# Direct RPC access
friends = client.talk.get_all_contact_ids()
square_resp = client.square.findSquareByInvitationTicketV2("your_ticket")
```

## Login Methods

Tokens are automatically saved to `.linepy_storage.json` for future sessions.

| Method | Description |
|---|---|
| `login(qr=True)` / `login_with_qr()` | QR code login (scan with mobile app). |
| `login(email="...", password="...")` | Email/password login (with E2EE PIN verification). |
| `login(auth_token="...")` | Log in with an existing auth token. |
| `login()` / `auto_login()` | Loads saved token from storage. |

## Examples

See the [`examples/`](./examples/) directory for runnable scripts:
- **`qr_login.py` / `email_login.py`**: Login flows.
- **`event_bot.py`**: Basic message listener.
- **`simple_square_bot.py`**: OpenChat (Square) bot.

## License
MIT
