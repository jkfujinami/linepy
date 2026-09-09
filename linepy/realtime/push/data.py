# -*- coding: utf-8 -*-
"""
LEGY Push Data Structures for LINEPY

HTTP/2 Push フレームのデータ構造定義
"""

import struct
from enum import IntEnum
from typing import Optional, Union


class LegyH2PingFrameType(IntEnum):
    NONE = 0
    ACK = 1
    ACK_REQUIRED = 2


class LegyH2PushFrameType(IntEnum):
    NONE = 0
    ACK = 1
    ACK_REQUIRED = 2


class LegyH2Frame:
    """Base class for LEGY H2 frames."""

    def __init__(self, frame_type: int):
        self.frame_type = frame_type

    def request_packet(self, payload: bytes) -> bytes:
        return struct.pack("!H", len(payload)) + bytes([self.frame_type]) + payload


class LegyH2StatusFrame(LegyH2Frame):
    """Status frame (type 0)."""

    def __init__(
        self,
        is_foreground: Optional[bool] = None,
        server_ping_interval: Optional[int] = None,
    ):
        super().__init__(0)
        self.is_foreground = is_foreground
        self.server_ping_interval = server_ping_interval


class LegyH2PingFrame(LegyH2Frame):
    """Ping frame (type 1)."""

    def __init__(
        self,
        ping_type: Optional[Union[LegyH2PingFrameType, int]] = None,
        ping_id: Optional[int] = None,
    ):
        super().__init__(1)
        self.ping_type = LegyH2PingFrameType(ping_type) if ping_type else LegyH2PingFrameType.NONE
        self.ping_id = ping_id

    def ack_packet(self) -> bytes:
        return self.request_packet(
            bytes([self.ping_type.value]) + struct.pack("!H", self.ping_id or 0)
        )


class LegyH2SignOnRequestFrame(LegyH2Frame):
    """Sign-on request frame (type 2)."""

    def __init__(
        self,
        request_id: Optional[int] = None,
        service_type: Optional[int] = None,
        request_payload: Optional[bytes] = None,
    ):
        super().__init__(2)
        self.request_id = request_id
        self.service_type = service_type
        self.request_payload = request_payload


class LegyH2SignOnResponseFrame(LegyH2Frame):
    """Sign-on response frame (type 3)."""

    def __init__(
        self,
        request_id: Optional[int] = None,
        is_fin: Optional[bool] = None,
        response_payload: Optional[bytes] = None,
    ):
        super().__init__(3)
        self.request_id = request_id
        self.is_fin = is_fin
        self.response_payload = response_payload


class LegyH2PushFrame(LegyH2Frame):
    """Push frame (type 4)."""

    def __init__(
        self,
        push_type: Optional[Union[LegyH2PushFrameType, int]] = None,
        service_type: Optional[int] = None,
        push_id: Optional[int] = None,
        push_payload: Optional[bytes] = None,
    ):
        super().__init__(4)
        self.push_type = LegyH2PushFrameType(push_type) if push_type else LegyH2PushFrameType.NONE
        self.service_type = service_type
        self.push_id = push_id
        self.push_payload = push_payload

    def ack_packet(self) -> bytes:
        if self.service_type is not None and self.push_id is not None:
            return self.request_packet(
                bytes([LegyH2PushFrameType.ACK.value, self.service_type])
                + struct.pack("!i", self.push_id)
            )
        raise ValueError("service_type and push_id required for ack")


# Service Types
class ServiceType(IntEnum):
    STATUS = 0
    PING = 1
    SIGN_ON_REQUEST = 2
    SQUARE = 3          # fetchMyEvents
    TALK_FETCHOPS = 5   # fetchOps (legacy)
    TALK_SYNC = 8       # sync (new)
    LIVETALK = 9        # fetchLiveTalkEvents
    OABOT = 10          # OA Bot push
