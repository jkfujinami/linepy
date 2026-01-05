# -*- coding: utf-8 -*-
"""
LEGY Push Manager for LINEPY

Push接続の管理とイベント処理
"""

import logging
import struct
import threading
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from .data import LegyH2PushFrame, ServiceType
from .conn import PushConnection

if TYPE_CHECKING:
    from ..base import BaseClient

logger = logging.getLogger("linepy.push")


def gen_service_mask(services: List[int]) -> int:
    """Generate service mask for /PUSH endpoint."""
    mask = 0
    for s in services:
        mask |= 1 << (s - 1)
    return mask


class PushManager:
    """
    LEGY Push Manager.

    HTTP/2 Push接続を管理し、サーバーからのイベントを処理する。

    Example:
        push = PushManager(client)
        push.on_event = lambda service, event: print(event)
        push.start()
    """

    def __init__(self, client: "BaseClient"):
        self.client = client
        self.connections: List[PushConnection] = []

        # State
        self._running = False
        self._ping_interval = 30
        self._current_ping_id = 0
        self._access_token: Optional[str] = None

        # Sync tokens
        self.event_sync_token: Optional[str] = None
        self.subscription_id: Optional[int] = None
        self.subscription_ids: Dict[int, float] = {}

        # Request tracking
        self.sign_on_requests: Dict[int, List] = {}

        # Callbacks
        self.on_event: Optional[Callable[[int, Any], None]] = None

        # Watched square chats (for fetchSquareChatEvents)
        self.watched_chats: List[str] = []
        self.chat_sync_tokens: Dict[str, str] = {}
        self.square_fetch_type: int = 1  # Default 1

        # Thread
        self._thread: Optional[threading.Thread] = None

    def start(self, services: List[int] = [3, 8], fetch_type: int = 1):
        """
        Start push connection in background thread.

        Args:
            services: Service types to subscribe (3=Square, 8=Talk)
            fetch_type: Fetch type for Square events (1=Default, 2=Prefetch by Server)
        """
        if self._running:
            logger.debug("Push already running")
            return

        self.square_fetch_type = fetch_type
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            args=(services,),
            daemon=True
        )
        self._thread.start()
        logger.info("Push started (fetch_type=%d)", fetch_type)

    def stop(self):
        """Stop push connection."""
        self._running = False
        for conn in self.connections:
            conn.close()
        self.connections = []
        logger.info("Push stopped")

    def _run_loop(self, services: List[int]):
        """Main run loop with auto-reconnect."""
        while self._running and self.client.auth_token:
            try:
                # Fetch sync tokens via HTTP first to avoid blocking the Push socket later
                self._refresh_sync_tokens()

                self.connections = []
                conn = self._initialize_connection(services)
                self._init_and_read(conn, services)
            except Exception as e:
                logger.warning("Push connection error: %s", e)

            if self._running:
                logger.debug("Reconnecting in 3 seconds...")
                time.sleep(3)

    def _initialize_connection(self, services: List[int]) -> PushConnection:
        """Create and initialize a new connection."""
        conn = PushConnection(self)
        self.connections.append(conn)
        self._access_token = self.client.auth_token

        headers = {
            "x-line-application": self.client.app_name,
            "x-line-access": self._access_token,
            "content-type": "application/octet-stream",
            "accept": "application/octet-stream",
        }

        mask = gen_service_mask(services)
        host = "gd2.line.naver.jp"  # TODO: configurable
        path = f"/PUSH/1/subs?m={mask}"

        logger.debug("Connecting to %s with mask=%d", host, mask)
        conn.connect(host, 443, path, headers)

        return conn

    def _refresh_sync_tokens(self):
        """Fetch initial sync tokens for watched chats."""
        if not self.watched_chats:
            return

        logger.debug("Refreshing sync tokens for %d chats", len(self.watched_chats))
        for chat_mid in self.watched_chats:
            # 既に sync_token がある場合はスキップ（再接続時の上書き防止）
            if chat_mid in self.chat_sync_tokens:
                logger.debug("Skipping %s (already has token)", chat_mid[:12])
                continue

            try:
                res = self.client.square.fetchSquareChatEvents(chat_mid, limit=1)
                if hasattr(res, 'syncToken') and res.syncToken:
                    self.chat_sync_tokens[chat_mid] = res.syncToken
                    logger.debug("Token for %s: %s...", chat_mid[:12], res.syncToken[:10])
            except Exception as e:
                logger.warning("Failed to get sync token for %s: %s", chat_mid[:12], e)

    def _init_and_read(self, conn: PushConnection, services: List[int]):
        """Initialize services and start reading."""

        # Initialize each service
        for service in services:
            if service == ServiceType.SQUARE:  # 3
                self._init_square_service(conn)
            elif service in [ServiceType.TALK_FETCHOPS, ServiceType.TALK_SYNC]:  # 5, 8
                self._init_talk_service(conn, service)

        # Start read loop (blocks)
        conn.read_loop()

    def _init_square_service(self, conn: PushConnection):
        """Initialize Square (Service 3) context."""
        # Use m=255 for full event mask
        params = {"m": "255"}

        # Ensure subscription_id is set if not already
        # CHRLINE forces new subscriptionID on every Init
        self.subscription_id = int(time.time() * 1000)

        request = self._build_fetch_my_events_request(
            self.subscription_id,
            self.event_sync_token or ""
        )

        # Build path with params
        path = "fetchMyEvents?" + "&".join([f"{k}={v}" for k, v in params.items()])
        self._send_sign_on_request(conn, ServiceType.SQUARE, request, path)

        # Initialize subscription_ids for tracking refreshes
        self.subscription_ids[self.subscription_id] = time.time()
        logger.debug("Square service initialized (subscription=%d)", self.subscription_id)

    def _init_talk_service(self, conn: PushConnection, service_type: int):
        """Initialize Talk service."""
        # TODO: implement sync request
        logger.debug("Talk service %d (not implemented)", service_type)

    def _build_fetch_my_events_request(self, subscription_id: int, sync_token: str) -> bytes:
        """Build fetchMyEvents request payload."""
        from ..thrift import write_thrift

        params = [
            [12, 1, [
                [10, 1, subscription_id],
                [11, 2, sync_token],
                [8, 3, 100],  # limit
            ]]
        ]
        return bytes(write_thrift(params, "fetchMyEvents", 4))

    def _send_sign_on_request(
        self,
        conn: PushConnection,
        service_type: int,
        request: bytes,
        method_name: str
    ):
        """Send a sign-on request."""
        request_id = len(self.sign_on_requests) + 1
        logger.debug("Sending sign-on request #%d: service=%d", request_id, service_type)

        payload = struct.pack("!H", request_id)
        payload += bytes([service_type, 0])
        payload += struct.pack("!H", len(request))
        payload += request

        self.sign_on_requests[request_id] = [service_type, method_name, None]
        conn.write_request(2, payload)

    # ========== Callbacks from Connection ==========

    def on_ping(self, ping_id: int):
        """Handle ping callback."""
        self._current_ping_id = ping_id

        # Check subscriptions that need refresh
        now = time.time()
        refresh_ids = []
        for sub_id, last_time in list(self.subscription_ids.items()):
            if (now - last_time) >= 3000:
                self.subscription_ids[sub_id] = now
                refresh_ids.append(sub_id)

        if refresh_ids:
            logger.debug("Refreshing subscriptions: %s", refresh_ids)

    def on_sign_on_response(self, request_id: int, is_fin: bool, data: bytes):
        """Handle sign-on response."""
        if request_id not in self.sign_on_requests:
            return

        service_type, method_name, _ = self.sign_on_requests[request_id]

        if service_type == ServiceType.SQUARE:
            self._handle_square_response(data)

    def _handle_square_response(self, data: bytes):
        """Handle Square (fetchMyEvents) response."""
        from ..thrift import read_thrift

        try:
            # Note: This is usually the initial fetch result
            logger.debug("Received Square response (%d bytes)", len(data))
        except Exception as e:
            logger.warning("Error parsing Square response: %s", e)

    def on_push(self, frame: LegyH2PushFrame):
        """Handle push frame from server."""
        logger.debug("Received push: service=%d", frame.service_type)

        if frame.service_type == ServiceType.SQUARE:  # 3
            # Server notified us of new events, fetch them in a separate thread
            threading.Thread(
                target=self._fetch_square_events,
                daemon=True
            ).start()
        elif frame.service_type == 8:
            logger.debug("Talk (Service 8) notification received")

    def _fetch_square_events(self):
        """Fetch Square events via HTTP (triggered by push)."""
        if not self.watched_chats:
            return

        for chat_mid in self.watched_chats:
            try:
                sync_token = self.chat_sync_tokens.get(chat_mid)

                # sync_token がない場合は、まず最新位置を取得する（古いイベント大量取得を防止）
                if not sync_token:
                    logger.debug("No sync token for %s, fetching initial position", chat_mid[:12])
                    init_res = self.client.square.fetchSquareChatEvents(chat_mid, limit=1)
                    if hasattr(init_res, 'syncToken') and init_res.syncToken:
                        self.chat_sync_tokens[chat_mid] = init_res.syncToken
                    continue  # 今回は取得せず、次回以降の Push で処理

                response = self.client.square.fetchSquareChatEvents(
                    squareChatMid=chat_mid,
                    syncToken=sync_token,
                    limit=50,
                    fetchType=self.square_fetch_type
                )

                # Update sync token
                if hasattr(response, 'syncToken') and response.syncToken:
                    self.chat_sync_tokens[chat_mid] = response.syncToken

                # Process events
                events = response.events if hasattr(response, 'events') else []
                if events:
                    logger.debug("Found %d events in %s", len(events), chat_mid[:12])

                for event in events:
                    if self.on_event:
                        # Pass Pydantic object directly for easier handling
                        self.on_event(ServiceType.SQUARE, event)

            except Exception as e:
                logger.warning("Error fetching events for %s: %s", chat_mid[:12], e)

    def add_watched_chat(self, chat_mid: str):
        """Add a chat to watch list."""
        if chat_mid not in self.watched_chats:
            self.watched_chats.append(chat_mid)
            logger.debug("Watching chat: %s", chat_mid[:12])

    def remove_watched_chat(self, chat_mid: str):
        """Remove a chat from watch list."""
        if chat_mid in self.watched_chats:
            self.watched_chats.remove(chat_mid)
            if chat_mid in self.chat_sync_tokens:
                del self.chat_sync_tokens[chat_mid]
