# -*- coding: utf-8 -*-
"""
PUSH stream packet framing (Phase 3 Step 9).

Faithful Python port of the packet layer in linejs
(resource/linejs/packages/linejs/base/push/conn.ts): a length-prefixed frame
``[2B dl][1B dt][dd...]`` carried on the bidirectional HTTP/2 PUSH stream, with
buffering for split frames and coalescing of multi-frame reads.

Frame types (``dt``):
  1 = ping, 3 = SignOn response (sync data), 4 = push notification.
"""

from typing import Callable, Dict, List, Optional


class PingFrame:
    ACK_REQUIRED = 1

    def __init__(self, ping_type: int, ping_id: int):
        self.ping_type = ping_type
        self.ping_id = ping_id


class SignOnResponseFrame:
    def __init__(self, request_id: int, is_fin: bool, payload: bytes):
        self.request_id = request_id
        self.is_fin = is_fin
        self.payload = payload


class PushFrame:
    def __init__(self, push_type: int, service_type: int, push_id: int, payload: bytes):
        self.push_type = push_type
        self.service_type = service_type
        self.push_id = push_id
        self.payload = payload


class PushPacketParser:
    """Stream parser that turns raw PUSH bytes into decoded frames.

    Register callbacks:
      * ``on_ping(PingFrame)``
      * ``on_sign_on_response(request_id, is_fin, payload)`` — fired only when a
        request's payload is complete (fragments are accumulated internally)
      * ``on_push(PushFrame)``
    """

    def __init__(
        self,
        on_ping: Optional[Callable[[PingFrame], None]] = None,
        on_sign_on_response: Optional[Callable[[int, bool, bytes], None]] = None,
        on_push: Optional[Callable[[PushFrame], None]] = None,
    ):
        self.cache_data = b""
        self.is_not_finished = False
        self.not_fin_payloads: Dict[int, bytes] = {}
        self.on_ping = on_ping
        self.on_sign_on_response = on_sign_on_response
        self.on_push = on_push

    @staticmethod
    def read_packet_header(data: bytes):
        dl = (data[0] << 8) | data[1]
        dt = data[2]
        dd = data[3:]
        return dt, dd, dl

    def on_data_received(self, data: bytes) -> None:
        if self.is_not_finished:
            data = self.cache_data + data

        # A frame needs at least the 3-byte header before it can be parsed.
        if len(data) < 3:
            self.is_not_finished = True
            self.cache_data = data
            return

        dt, dd, dl = self.read_packet_header(data)
        if dl > len(dd):
            # Frame body not fully arrived yet — buffer and wait.
            self.is_not_finished = True
            self.cache_data = data
            return
        self.is_not_finished = False
        self.cache_data = b""
        if len(dd) > dl:
            self.on_packet_received(dt, dd[:dl])
            rest = dd[dl:]
            self.on_data_received(rest)
            return
        self.on_packet_received(dt, dd)

    def on_packet_received(self, dt: int, dd: bytes) -> None:
        if dt == 1:
            ping = PingFrame(dd[0], (dd[1] << 8) | dd[2])
            if self.on_ping:
                self.on_ping(ping)
        elif dt == 3:
            req = (dd[0] << 8) | dd[1]
            request_id = req & 0x7FFF
            is_fin = (req & 0x8000) != 0
            payload = dd[2:]
            if is_fin:
                if request_id in self.not_fin_payloads:
                    payload = self.not_fin_payloads.pop(request_id) + payload
                if self.on_sign_on_response:
                    self.on_sign_on_response(request_id, is_fin, payload)
            else:
                self.not_fin_payloads[request_id] = (
                    self.not_fin_payloads.get(request_id, b"") + payload
                )
        elif dt == 4:
            push = PushFrame(
                dd[0], dd[1],
                (dd[2] << 24) | (dd[3] << 16) | (dd[4] << 8) | dd[5],
                dd[6:],
            )
            if self.on_push:
                self.on_push(push)
        else:
            raise ValueError(f"PUSH not implemented: type={dt}, len={len(dd)}")


def build_packet(dt: int, dd: bytes) -> bytes:
    """Build a framed PUSH packet (mainly for tests/round-trips)."""
    return bytes([(len(dd) >> 8) & 0xFF, len(dd) & 0xFF, dt]) + dd
