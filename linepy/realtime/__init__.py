# -*- coding: utf-8 -*-
"""Realtime event reception.

Two transports, one dispatcher:

* :mod:`~linepy.realtime.push` -- LEGY's HTTP/2 PUSH stream, the low-latency
  path for both Talk sync and Square events.
* :mod:`~linepy.realtime.polling` -- a thread-per-chat fetch loop over
  ``fetchSquareChatEvents``, for when PUSH is unavailable or too slow.

Both hand raw operations to :class:`~linepy.realtime.dispatcher.EventDispatcher`,
which decrypts E2EE payloads, wraps them in the
:mod:`~linepy.realtime.message` objects and fans them out through the
client's single event bus (``BaseClient.on`` / ``emit``).
"""

from .dispatcher import EventDispatcher
from .message import SquareMessage, TalkMessage
from .polling import PollingManager
from .push import PushManager

__all__ = [
    "EventDispatcher",
    "PollingManager",
    "PushManager",
    "SquareMessage",
    "TalkMessage",
]
