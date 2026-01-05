# -*- coding: utf-8 -*-
"""
LEGY Push Connection for LINEPY

HTTP/2 接続管理（同期版）
"""

import logging
import socket
import ssl
import struct
import time
from typing import TYPE_CHECKING, Optional

try:
    import h2.connection
    from h2.config import H2Configuration
    from h2.events import DataReceived, StreamEnded, StreamReset, PingAckReceived
    H2_AVAILABLE = True
except ImportError:
    H2_AVAILABLE = False

from .data import (
    LegyH2PingFrame,
    LegyH2PingFrameType,
    LegyH2PushFrame,
    LegyH2PushFrameType,
    LegyH2SignOnResponseFrame,
)

if TYPE_CHECKING:
    from .manager import PushManager

logger = logging.getLogger("linepy.push")


class PushConnection:
    """
    HTTP/2 Push Connection.

    サーバーとのHTTP/2接続を管理し、Push通知を受信する。
    """

    def __init__(self, manager: "PushManager"):
        if not H2_AVAILABLE:
            raise ImportError("h2 library required. Install with: pip install h2")

        self.manager = manager
        self.conn: Optional[h2.connection.H2Connection] = None
        self.writer: Optional[ssl.SSLSocket] = None
        self.h2_headers = []

        self.is_not_finished = False
        self.buffer = b""
        self.not_fin_payloads = {}

        self._last_send_time = 0.0
        self._last_ping_send_time = 0.0
        self._awaiting_pong = False
        self._closed = False

    @property
    def client(self):
        return self.manager.client

    def connect(self, host: str, port: int, path: str, headers: dict):
        """
        Establish HTTP/2 connection.

        Args:
            host: Server hostname
            port: Server port (usually 443)
            path: Request path (e.g., /PUSH/1/subs?m=...)
            headers: HTTP headers to send
        """
        ctx = ssl.create_default_context()
        ctx.set_alpn_protocols(["h2"])

        sock = socket.create_connection((host, port))
        self.writer = ctx.wrap_socket(sock, server_hostname=host)

        # タイムアウトを設定（ブロッキング回避）
        self.writer.settimeout(5.0)

        config = H2Configuration(client_side=True)
        self.conn = h2.connection.H2Connection(config=config)

        self.h2_headers = [
            (":method", "POST"),
            (":authority", host),
            (":scheme", "https"),
            (":path", path),
        ]
        for key, value in headers.items():
            self.h2_headers.append((key.lower(), value))

        self.conn.initiate_connection()
        self.conn.send_headers(1, self.h2_headers)
        self.send_data_to_socket()

        logger.debug("Connected to %s:%d%s", host, port, path)

    def send_data_to_socket(self):
        """Send pending data to server."""
        if self.conn and self.writer:
            send_data = self.conn.data_to_send()
            if send_data:
                self._last_send_time = time.time()
                self.writer.sendall(send_data)
        else:
            raise RuntimeError("Connection not established")

    def write_bytes(self, data: bytes, flush: bool = False):
        """Write raw bytes to stream."""
        if self.conn:
            self.conn.send_data(stream_id=1, data=data, end_stream=False)
            if flush:
                self.send_data_to_socket()
        else:
            raise RuntimeError("Connection not established")

    def write_request(self, packet_type: int, payload: bytes, flush: bool = True):
        """Write a packet to the stream."""
        data = self.build_packet(packet_type, payload)
        self.write_bytes(data, flush=flush)

    def write_ping(self, ping_id: int):
        """Send a Ping response (Packet Type 1)."""
        # Type 1, Payload: 0x01 + 2-byte ID
        payload = bytes([1]) + struct.pack("!H", ping_id)
        self.write_request(1, payload, flush=True)

    def build_packet(self, packet_type: int, payload: bytes) -> bytes:
        """Build LEGY packet with header."""
        size = len(payload)
        header = struct.pack("!HB", size & 32767, packet_type)
        return header + payload

    def send_h2_ping(self):
        """Send HTTP/2 PING frame for keep-alive."""
        if self.conn:
            self.conn.ping(b'KEEP_ALI')
            self.send_data_to_socket()
            self._last_ping_send_time = time.time()
            logger.debug("Sent H2 PING")

    def read_loop(self):
        """
        Read loop for handling incoming data.
        Blocks until connection is closed.
        """
        self._last_receive_time = time.time()

        try:
            response_stream_ended = False
            while not response_stream_ended and not self._closed:
                try:
                    # Read raw data from socket
                    data = self.writer.recv(65536)
                    self._last_receive_time = time.time()
                except socket.timeout:
                    # タイムアウト（正常なアイドル状態含む）
                    now = time.time()

                    # Keep-Alive Ping (every 30s)
                    if now - self._last_ping_send_time > 30:
                        if self._awaiting_pong:
                            # 前回のPingに対する応答がない -> 切断
                            logger.warning("Ping timeout (no PONG received). Reconnecting...")
                            break

                        try:
                            self.send_h2_ping()
                            self._awaiting_pong = True
                        except Exception as e:
                            logger.warning("Failed to send keep-alive ping: %s", e)
                            break

                    # 最後の受信から一定時間以上経過していたら切断とみなす
                    idle_time = now - self._last_receive_time
                    if idle_time > 120:  # 2分間パケットなし
                         logger.warning("Connection timed out (idle for %.1fs)", idle_time)
                         break
                    continue

                if not data:
                    logger.debug("Socket closed by server")
                    break

                # Process H2 events
                events = self.conn.receive_data(data)
                for event in events:
                    if isinstance(event, DataReceived):
                        self.conn.acknowledge_received_data(
                            event.flow_controlled_length, event.stream_id
                        )
                        if event.data:
                            self._on_data_received(event.data)
                    elif isinstance(event, StreamEnded):
                        response_stream_ended = True
                        break
                    elif isinstance(event, StreamReset):
                        logger.warning("Stream reset by server: %s", event.error_code)
                        raise RuntimeError(f"Stream reset: {event.error_code}")
                    elif isinstance(event, PingAckReceived):
                        self._awaiting_pong = False
                        logger.debug("Received H2 PONG")

                self.send_data_to_socket()

            self.conn.close_connection()
            self.send_data_to_socket()
        except Exception as e:
            if not self._closed:
                logger.warning("Connection error: %s", e)
        finally:
            self.close()

    def _on_data_received(self, data: bytes):
        """Handle incoming H2 data stream."""
        self.buffer += data

        while len(self.buffer) >= 3:
            # Parse Header: 2 bytes size, 1 byte type
            size_h, packet_type = struct.unpack("!HB", self.buffer[:3])
            size = size_h & 32767

            if len(self.buffer) < 3 + size:
                break  # Wait for more data

            payload = self.buffer[3 : 3 + size]
            self.buffer = self.buffer[3 + size :]

            self._on_packet_received(packet_type, payload)

    def _on_packet_received(self, packet_type: int, payload: bytes):
        """Handle a complete packet."""

        if packet_type == 1:  # Ping
            # Payload: [1-byte type, 2-byte id]
            ping_type = payload[0]
            if len(payload) >= 3:
                ping_id, = struct.unpack("!H", payload[1:3])
            else:
                ping_id = 0

            if ping_type == 2:  # Server Ping
                packet = LegyH2PingFrame(1, ping_id)  # Type 1 is ACK
                self.write_bytes(packet.ack_packet())
                self.manager.on_ping(ping_id)
            # else: PONG - no action needed

        elif packet_type == 2:  # Sign-on Request (Echo back)
            logger.debug("Sign-on request echo received")

        elif packet_type == 3:  # Sign-on response
            if len(payload) < 2:
                return
            req, = struct.unpack("!H", payload[0:2])
            request_id = req & 32767
            is_fin = (req & 32768) != 0
            response_payload = payload[2:]

            if is_fin:
                if request_id in self.not_fin_payloads:
                    response_payload = self.not_fin_payloads[request_id] + response_payload
                    del self.not_fin_payloads[request_id]
                self.manager.on_sign_on_response(request_id, is_fin, response_payload)
            else:
                if request_id not in self.not_fin_payloads:
                    self.not_fin_payloads[request_id] = b""
                self.not_fin_payloads[request_id] += response_payload

        elif packet_type == 4:  # Push
            if len(payload) < 6:
                return
            push_type = payload[0]
            service_type = payload[1]
            push_id, = struct.unpack("!i", payload[2:6])
            push_payload = payload[6:]

            packet = LegyH2PushFrame(push_type, service_type, push_id, push_payload)

            if packet.push_type in [LegyH2PushFrameType.NONE, LegyH2PushFrameType.ACK_REQUIRED]:
                if packet.push_type == LegyH2PushFrameType.ACK_REQUIRED:
                    self.write_bytes(packet.ack_packet())

                self.manager.on_push(packet)

    def close(self):
        """Close the connection."""
        self._closed = True
        if self.conn and self.writer:
            self.conn.close_connection()
            self.send_data_to_socket()
            self.writer.close()

    def is_active(self) -> bool:
        """Check if connection is active."""
        return not self._closed and self.conn is not None
