# LINEPY

LINE SelfBot library for Python — a faithful port of [linejs](https://github.com/evex-dev/linejs)'s protocol/crypto/auth layer, with a Python-friendly high-level API on top.

- Pure-Python end to end: **no C or Rust extensions anywhere in the dependency tree.** Models are stdlib `dataclasses`, and crypto (AES/RSA/X25519/HKDF/AES-GCM-SIV/xxHash32) is a from-scratch pure-Python implementation. This means it also installs and runs on sandboxed/no-compiler environments like **a-Shell on iPhone/iPad** — see [Running on iOS (a-Shell)](#running-on-ios-a-shell) below.

## Installation

```bash
git clone <this-repo>
cd linepy
pip install -e .
```

Runtime dependencies are intentionally minimal and all pure-Python: `httpx[http2]`, `pyaes`, `qrcode`. See [Why no pycryptodome/cryptography/pydantic/xxhash?](#why-no-pycryptodomecryptographypydanticxxhash) for the reasoning.

## Two ways to use it: `Client` vs `BaseClient`

| | `Client` | `BaseClient` |
|---|---|---|
| Best for | Simple bots, quick scripts | Fine-grained control, scripts that need specific RPCs |
| Import | `from linepy import Client` | `from linepy.base import BaseClient` |
| Events | `client.on(...)` / `client.listen()` | same, but you build the reconnect/listen loop yourself if you don't use `.listen()` |
| Convenience methods | `send_message`, `get_all_friends`, `get_all_chats`, ... | none — you call `client.talk.*` / `client.square.*` / `client.channel.*` directly |
| Under the hood | Wraps a `BaseClient` instance (`client.base`) | The actual protocol/session/services live here |

`Client` is a thin convenience wrapper — everything it does, it does by calling into `BaseClient`. Reach for `BaseClient` directly whenever you need a specific Thrift RPC that `Client` doesn't wrap (most of `linepy/talk.py`, `linepy/square.py`, `linepy/channel.py`), or when you want full control over the login/session lifecycle. Most of the example scripts in `examples/` use `BaseClient` directly for this reason.

## Quick Start — `Client` (high-level)

```python
from linepy import Client

client = Client(device="DESKTOPWIN")

# First run: no token yet, so log in interactively (QR or email/password work too).
# Subsequent runs: auto_login() picks up the saved token from storage.
client.login(qr=True)  # scans a QR code; falls back to auto_login() if a token exists

profile = client.get_profile()
print(f"Logged in as: {profile.display_name}")

client.send_message("USER_MID", "Hello!")

@client.on("message")
def on_message(msg):
    if msg.text == "!ping":
        msg.reply("pong!")

client.listen()          # starts the PUSH listener in a background thread
import time
while True:
    time.sleep(1)         # keep the main thread alive
```

`client.login(...)` accepts exactly one of:

```python
client.login(auth_token="...")            # token login
client.login(email="...", password="...") # email/password login (full E2EE PIN handshake)
client.login(qr=True)                     # QR code login
client.login()                            # tries auto_login() from storage, then falls back to QR
```

## Quick Start — `BaseClient` (low-level, recommended for scripts)

This is the pattern used by most of `examples/`:

```python
from linepy.base import BaseClient

client = BaseClient("DESKTOPWIN", storage=".linepy_storage.json")

if not client.auto_login():
    # No valid saved token -- log in once and it'll be saved for next time.
    client.login_with_qr()

profile = client.get_profile()
print(f"Logged in as: {profile.display_name}")

# Talk to a friend
client.send_message("USER_MID", "Hello!")

# Direct RPC access -- anything defined on TalkService/SquareService/ChannelService
friends = client.talk.get_all_contact_ids()
square_resp = client.square.findSquareByInvitationTicketV2("your_ticket")
```

**Important:** `BaseClient(...)` does **not** load a saved token automatically — you must call `client.auto_login()` (or `client.login_with_token(...)` / `client.login_with_qr()` / `client.login_with_email(...)`) yourself. Forgetting this is the #1 cause of `[403] Forbidden` errors against `legy.line-apps.com` in this library (the request goes out unauthenticated).

## Login methods

| Method | Notes |
|---|---|
| `login_with_qr(v3=None, save=True)` | Prints/returns a QR login URL; scan it with the LINE mobile app. |
| `login_with_email(email, password, pincode="114514", e2ee=True)` | Full E2EE PIN-verification handshake (loginZ/loginV2), matching linejs. |
| `login_with_token(auth_token, save=True)` | Log in with an existing auth token (e.g. exported from another client). |
| `auto_login()` | Loads and validates the token from storage; returns `False` if none is saved or it's invalid. |

All of them persist the resulting token to `storage` (when `save=True`) so `auto_login()` works on the next run.

## Storage

By default, tokens are saved to `.linepy_storage.json` in the working directory (`FileStorage`). Pass a different path as `storage="path/to/file.json"`, or pass your own `BaseStorage` subclass for a custom backend (database, keychain, etc.) — see `linepy/storage.py`.

## Events (`Client.on` / `BaseClient.on`)

```python
@client.on("message")
def on_message(msg):
    print(f"[{msg.sender_mid}] {msg.text}")

@client.on("edit")
def on_edit(msg):
    ...
```

Call `client.listen()` to start the PUSH listener in a background thread, then keep the main thread alive (`while True: time.sleep(1)`) — there is no `client.poll()` blocking call.

For Square (OpenChat) push events specifically, see `client.square_helper` / `client.start_push(chat_mids, on_event=...)` / `client.stop_push()`, demonstrated in `examples/verify_legy_push.py` and `examples/run_checker.py`.

## Features

- **Login**: QR code (v1/v2, ForSecure), email/password with full E2EE PIN handshake, auth-token login, auto-login with persistent storage
- **Messaging**: text/image/video/audio/file, event-driven handling via long polling (PUSH/LEGY)
- **Square (OpenChat)**: join/leave, send/receive messages, mention/reply/reaction, invitation tickets, chat/member management
- **Timeline / Note**: create/delete posts, list posts (including Square Note)
- **Core protocol**: Thrift Binary + Compact protocol, HTTP/2, LEGY encrypted transport (`/enc`), E2EE (1:1 and group), multiple device profiles

## Supported Devices

`device=` accepts: `DESKTOPWIN`, `DESKTOPMAC`, `CHROMEOS`, `ANDROID`, `ANDROIDSECONDARY`, `IOS`, `IOSIPAD`, `WATCHOS`, `WEAROS`.

## Examples

See `examples/` for complete, runnable scripts:

| Script | Demonstrates |
|---|---|
| `basic.py` | `BaseClient` + `auto_login()` + profile fetch |
| `qr_login.py` | QR login with `pincall`/`qrcall` event hooks |
| `email_login.py` | Email/password login |
| `event_bot.py` | `Client` + `on("message")` + `listen()` |
| `simple_square_bot.py` | Square push events via long polling |
| `verify_legy_push.py` / `run_checker.py` | Square LEGY push (`start_push`/`stop_push`) |
| `square_test.py` | Invitation-ticket lookup and joining a Square |

## Running on iOS (a-Shell)

linepy is designed to install and run inside [a-Shell](https://github.com/holzschu/a-shell) (a sandboxed terminal app for iOS/iPadOS) with **no compiled/native dependencies at all**. a-Shell's Python cannot build C or Rust extensions, and — critically — even a *prebuilt* iOS wheel for a native-extension package will fail to load at runtime with a code-signing error (`dlopen(...): missing code signature`), because iOS refuses to execute unsigned code downloaded by pip. This rules out `pydantic` (needs `pydantic-core`, Rust), `pycryptodome`/`cryptography`/`pynacl` (C/Rust), and `xxhash` (C) — all common Python packages that normally look installable but silently can't actually run there.

linepy avoids every one of these:

- **Data models**: plain stdlib `dataclasses` (see `linepy/_model_base.py`) instead of pydantic.
- **Crypto**: AES (ECB/CBC/CTR/GCM), RSA (PKCS1v1.5/OAEP), X25519, HKDF-SHA256, and AES-GCM-SIV are all implemented from scratch in pure Python in `linepy/_purecrypto.py`, on top of `pyaes` (itself pure-Python). Every primitive is verified byte-for-byte against `pycryptodome`/`cryptography` and, where available, official test vectors (RFC 7748 for X25519, RFC 8452 for AES-GCM-SIV) — see `tests/test_purecrypto.py`.
- **xxHash32**: reimplemented in pure Python (`linepy/_purecrypto.py`) for the LEGY transport's integrity trailer, verified against the real `xxhash` package across boundary-length inputs.

To install in a-Shell:

```bash
pip install httpx[http2] pyaes qrcode
cd linepy
pip install -e . --no-deps   # --no-deps: pyproject's deps are already pure-Python and installed above
```

If `pip install -e .` itself fails on metadata generation (older `hatchling` bundled with a-Shell), install the runtime deps directly and add the repo root to `sys.path` instead of using an editable install:

```python
import sys
sys.path.insert(0, "/path/to/linepy")
from linepy.base import BaseClient
```

### Why no pycryptodome/cryptography/pydantic/xxhash?

Short version: they're all C or Rust extensions, and a-Shell's Python sandbox cannot execute any dynamically-loaded native code that wasn't compiled and code-signed as part of the app bundle itself — not because the wheel doesn't exist, but because iOS's code-signing enforcement blocks it at `dlopen()` time regardless. This is a hard platform constraint, not something fixable by pinning a different version. See the comment block at the top of `pyproject.toml` and `linepy/_purecrypto.py`'s module docstring for the full story.

## References

- [linejs](https://github.com/evex-dev/linejs) — original TypeScript library (protocol/crypto reference)
- [CHRLINE](https://github.com/DeachSword/CHRLINE) — Python reference implementation

## License

MIT
