# -*- coding: utf-8 -*-
"""Convenience helpers for Talk (1:1, group and room) messages.

Function-style counterparts to :class:`~linepy.realtime.message.TalkMessage`,
for code that holds a raw ``Message`` model rather than the OO wrapper.

The previous version of this module lived at ``linepy/helpers.py``, where the
``linepy/helpers/`` package shadowed it, so nothing could import it -- which
hid the fact that it called ``client.talk.send_message(to=..., text=...)``.
The generated TalkService takes ``(seq, message)``; the keyword form belongs
to ``BaseClient.send_message``, which is what these call.
"""

from typing import TYPE_CHECKING, Any, Optional

from ..realtime.message import reply_target as _reply_target

if TYPE_CHECKING:
    from ..base import BaseClient
    from ..models import Chat, Message

__all__ = ["reply_target", "reply_message", "send_chat_message"]


def reply_target(client: "BaseClient", message: "Message") -> Optional[str]:
    """Where a reply to ``message`` should be addressed.

    Same rule as :attr:`linepy.realtime.message.TalkMessage.reply_target`,
    which this delegates to, but reading the mids off a raw ``Message``.
    Returns ``None`` when the message carries no sender or no target.
    """
    if not message.from_ or not message.to:
        return None
    return _reply_target(message.from_, message.to, client.mid)


def reply_message(client: "BaseClient", message: "Message", text: str) -> Optional[Any]:
    """Reply to ``message``, quoting it.

    Returns ``None`` when the message carries no sender/target to reply to.
    """
    target = reply_target(client, message)
    if target is None:
        return None

    # The generated Message model names the field ``id_`` -- ``id`` shadows a
    # builtin, so the generator suffixes it. The old helper used ``message.id``
    # and would have raised AttributeError had it ever been reachable.
    return client.send_message(to=target, text=text, related_message_id=message.id_)


def send_chat_message(client: "BaseClient", chat: "Chat", text: str) -> Optional[Any]:
    """Send ``text`` to ``chat``. Returns ``None`` if the chat has no mid."""
    if not chat.chat_mid:
        return None

    return client.send_message(to=chat.chat_mid, text=text)
