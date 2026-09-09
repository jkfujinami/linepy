# -*- coding: utf-8 -*-
"""
Event dispatcher for the PUSH listen loop (Phase 3 Step 10).

Turns raw Talk operations / Square events into high-level events, decrypting
E2EE messages and wrapping them in TalkMessage / SquareMessage. Each dispatch
is isolated so one bad message never stops the stream (本家 requirement).
"""

from typing import Any

from .message import SquareMessage, TalkMessage

# Talk operation types (LINE OpType enum)
OP_RECEIVE_MESSAGE = 26
OP_SEND_MESSAGE = 25
OP_EDIT_MESSAGE = 158
OP_NOTIFIED_EDIT_MESSAGE = 159
OP_NOTIFIED_RECEIVED_CALL = 60

# Square event types
SQ_NOTIFICATION_MESSAGE = "NOTIFICATION_MESSAGE"


def _attr(obj, *names, default=None):
    if isinstance(obj, dict):
        for n in names:
            if n in obj:
                return obj[n]
        return default
    for n in names:
        if hasattr(obj, n):
            return getattr(obj, n)
    return default


class EventDispatcher:
    def __init__(self, client):
        self.client = client

    # ---- Talk ----
    def dispatch_talk_operation(self, op: Any) -> None:
        try:
            op_type = _attr(op, "type", "op_type", "opType")
            if isinstance(op_type, str):
                op_type = {
                    "RECEIVE_MESSAGE": OP_RECEIVE_MESSAGE,
                    "SEND_MESSAGE": OP_SEND_MESSAGE,
                    "EDIT_MESSAGE": OP_EDIT_MESSAGE,
                    "NOTIFIED_EDIT_MESSAGE": OP_NOTIFIED_EDIT_MESSAGE,
                    "NOTIFIED_RECEIVED_CALL": OP_NOTIFIED_RECEIVED_CALL,
                }.get(op_type, op_type)

            if op_type in (OP_RECEIVE_MESSAGE, OP_SEND_MESSAGE):
                message = _attr(op, "message", "param3") or op
                message = self._maybe_decrypt(message)
                self._emit("message", TalkMessage(message, self.client))
            elif op_type in (OP_EDIT_MESSAGE, OP_NOTIFIED_EDIT_MESSAGE):
                message = _attr(op, "message") or op
                self._emit("edit", TalkMessage(message, self.client))
            elif op_type == OP_NOTIFIED_RECEIVED_CALL:
                self._emit("call", op)
        except Exception as exc:  # isolation: never break the stream
            self._safe_emit("error", exc)

    # ---- Square ----
    def dispatch_square_event(self, event: Any) -> None:
        try:
            ev_type = _attr(event, "type", "eventType")
            payload = _attr(event, "payload") or {}
            if ev_type == SQ_NOTIFICATION_MESSAGE or str(ev_type).endswith(
                "NOTIFICATION_MESSAGE"
            ):
                notif = _attr(payload, "notificationMessage", "notification_message") \
                    or payload
                sq_msg = _attr(notif, "squareMessage", "square_message") or notif
                message = _attr(sq_msg, "message") or sq_msg
                message = self._maybe_decrypt(message)
                self._emit("square:message", SquareMessage(message, self.client))
        except Exception as exc:
            self._safe_emit("error", exc)

    # ---- helpers ----
    def _maybe_decrypt(self, message):
        try:
            chunks = _attr(message, "chunks")
            if chunks and getattr(self.client, "e2ee", None):
                self.client.e2ee.decrypt_e2ee_message(message)
        except Exception:
            # A single undecryptable message must not stop the loop.
            pass
        return message

    def _emit(self, event: str, payload) -> None:
        """Primary emit — callback errors propagate to the dispatch guard,
        which reports them as an ``error`` event (isolation + reporting)."""
        emit = getattr(self.client, "emit", None)
        if emit is not None:
            emit(event, payload)

    def _safe_emit(self, event: str, payload) -> None:
        """Secondary emit that never raises (used for the error channel)."""
        emit = getattr(self.client, "emit", None)
        if emit is None:
            return
        try:
            emit(event, payload)
        except Exception:
            pass
