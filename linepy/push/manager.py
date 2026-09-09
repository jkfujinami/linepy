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

from .conn import PushConnection
from .data import LegyH2PushFrame, ServiceType

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

    DEFAULT_SERVICES = (ServiceType.SQUARE, ServiceType.TALK_SYNC)

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
        self.chat_continuation_tokens: Dict[str, str] = {}
        self.square_fetch_type: int = 1  # Default 1

        # Thread
        self._thread: Optional[threading.Thread] = None
        self._fetch_lock = threading.Lock()

    def start(
        self,
        watched_chats: Optional[List[str]] = None,
        on_event: Optional[Callable[[Any, Any], None]] = None,
        fetch_type: int = 1,
        services: Optional[List[int]] = None,
    ):
        """Start Push connection loop.

        ``watched_chats=None`` keeps whatever :meth:`add_watched_chat` has
        already registered (along with its restored sync tokens); pass a list
        to replace the watch set outright.
        """
        if self._running:
            logger.warning("Push is already running")
            return

        if watched_chats is not None:
            self.watched_chats = list(watched_chats)
        services = list(services) if services is not None else list(self.DEFAULT_SERVICES)
        if on_event:
            self.on_event = on_event
        self.fetch_type = fetch_type

        # Initialize sync tokens
        self.event_sync_token = None
        self.subscription_id = 0

        self._running = True

        # Start main loop in a thread
        self._thread = threading.Thread(
            target=self._run_loop,
            args=(services,),  # Pass services to run_loop
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
                if hasattr(res, 'sync_token') and res.sync_token:
                    self.chat_sync_tokens[chat_mid] = res.sync_token
                    logger.debug("Token for %s: %s...", chat_mid[:12], res.sync_token[:10])
            except Exception as e:
                logger.warning("Failed to get sync token for %s: %s", chat_mid[:12], e)

    def _init_and_read(self, conn: PushConnection, services: List[int]):
        """Initialize services and start reading."""

        # Send Status Frame (Type 0)
        # Payload: [0, Flag(0), PingInterval(30)]
        ping_interval = 30
        status_payload = bytes([0, 0, ping_interval])
        conn.write_request(0, status_payload)
        logger.debug("Sent Status Frame: interval=%ds", ping_interval)

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
        """Initialize Talk service (Service 5/8) with an in-stream sync request.

        Sends a ``sync`` SignOnRequest carrying the last-known revisions; the
        response (TMoreCompactProtocol) is decoded in :meth:`on_sign_on_response`
        and the next sync request is re-issued on the same stream.
        """
        request = self._build_talk_sync_request()
        self._send_sign_on_request(conn, service_type, request, "sync")
        logger.debug("Talk service %d initialized (in-stream sync)", service_type)

    def _build_talk_sync_request(self) -> bytes:
        """Build a Talk ``sync`` request payload from stored revisions."""
        from ..protocol.thrift import write_thrift

        rev = getattr(self, "last_revision", 0) or 0
        global_rev = getattr(self, "last_global_revision", 0) or 0
        individual_rev = getattr(self, "last_individual_revision", 0) or 0
        params = [
            [12, 1, [
                [10, 1, rev],
                [8, 2, 100],  # count
                [10, 3, global_rev],
                [10, 4, individual_rev],
            ]]
        ]
        return bytes(write_thrift(params, "sync", 4))

    def decode_talk_sync(self, data: bytes):
        """Decode a Talk sync SignOn payload.

        Talk sync responses arrive as TMoreCompactProtocol; fall back to the
        standard compact protocol when TMC decoding fails.
        """
        from ..protocol.thrift.tmc import TMoreCompactProtocol

        try:
            return TMoreCompactProtocol(data).res
        except Exception as tmc_err:
            logger.debug("TMC decode failed (%s), falling back to compact", tmc_err)
            try:
                from ..protocol.thrift import read_thrift

                return read_thrift(data, 4)
            except Exception as compact_err:
                logger.warning("Talk sync decode failed: %s", compact_err)
                return None

    @staticmethod
    def extract_operations(decoded):
        """Pull the operations list out of a decoded sync result."""
        if decoded is None:
            return []
        # success struct at field 0; operations commonly at field 1 within it.
        success = None
        if isinstance(decoded, dict):
            success = decoded.get(0, decoded)
        else:
            success = decoded
        if isinstance(success, dict):
            for fid in (1, 2, 3):
                val = success.get(fid)
                if isinstance(val, list):
                    return val
        return []

    def _build_fetch_my_events_request(self, subscription_id: int, sync_token: str) -> bytes:
        """Build fetchMyEvents request payload."""
        from ..protocol.thrift import write_thrift

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
        logger.debug("Received LEGY PING id=%d", ping_id)

        # Check subscriptions that need refresh
        now = time.time()
        refresh_ids = []
        for sub_id, last_time in list(self.subscription_ids.items()):
            if (now - last_time) >= 3000:
                self.subscription_ids[sub_id] = now
                refresh_ids.append(sub_id)

        if refresh_ids:
            logger.debug("Refreshing subscriptions: %s", refresh_ids)

        # Call noop every 3 pings (like linejs)
        if ping_id % 3 == 0:
            threading.Thread(
                target=self._call_noop,
                daemon=True
            ).start()

    def _call_noop(self):
        """Call talk.noop() to keep session alive."""
        try:
            self.client.talk.noop()
            logger.debug("Called noop()")
        except Exception as e:
            logger.warning("noop() failed: %s", e)

    def on_sign_on_response(self, request_id: int, is_fin: bool, data: bytes):
        """Handle sign-on response."""
        if request_id not in self.sign_on_requests:
            return

        service_type, method_name, _ = self.sign_on_requests[request_id]

        if service_type == ServiceType.SQUARE:
            self._handle_square_response(data)
        elif service_type in (ServiceType.TALK_FETCHOPS, ServiceType.TALK_SYNC):  # 5, 8
            self._handle_talk_sync_response(data)

    def _handle_talk_sync_response(self, data: bytes):
        """Decode a Talk sync response (TMC) and dispatch its operations."""
        decoded = self.decode_talk_sync(data)
        operations = self.extract_operations(decoded)
        dispatcher = self._get_dispatcher()
        for op in operations:
            try:
                if dispatcher is not None:
                    dispatcher.dispatch_talk_operation(op)
                elif self.on_event:
                    self.on_event(ServiceType.TALK_SYNC, op)
            except Exception as exc:
                logger.debug("Talk operation dispatch error: %s", exc)
        # Advance revisions from the decoded result so the next sync continues.
        self._advance_talk_revisions(decoded)

    def _advance_talk_revisions(self, decoded):
        if not isinstance(decoded, dict):
            return
        success = decoded.get(0, decoded)
        if isinstance(success, dict):
            for attr, fid in (("last_revision", 1), ("last_global_revision", 3),
                              ("last_individual_revision", 4)):
                val = success.get(fid)
                if isinstance(val, int):
                    setattr(self, attr, val)

    def _get_dispatcher(self):
        getter = getattr(self.client, "get_dispatcher", None)
        return getter() if callable(getter) else None

    def _handle_square_response(self, data: bytes):
        """Handle Square (fetchMyEvents) response."""

        try:
            # Note: This is usually the initial fetch result
            logger.debug("Received Square response (%d bytes)", len(data))
        except Exception as e:
            logger.warning("Error parsing Square response: %s", e)

    def on_push(self, frame: LegyH2PushFrame):
        """Handle push frame from server."""
        logger.debug("Received push: service=%d", frame.service_type)

        if frame.service_type == ServiceType.SQUARE:  # 3
            # Extract subscriptionId from payload (like linejs L445-448)
            if frame.push_payload and len(frame.push_payload) > 0:
                try:
                    from ..protocol.thrift import CompactReader
                    proto = CompactReader(frame.push_payload)
                    parsed = proto.read_struct()
                    if 1 in parsed:  # Field 1 = subscriptionId
                        self.subscription_id = parsed[1]
                        logger.debug("Updated subscriptionId from push: %d", self.subscription_id)
                except Exception as e:
                    logger.debug("Failed to parse push payload: %s", e)

            # Server notified us of new events, fetch them in a separate thread
            threading.Thread(
                target=self._fetch_square_events,
                daemon=True
            ).start()
        elif frame.service_type == 8:
            logger.debug("Talk (Service 8) notification received")

    def _fetch_square_events(self):
        """Fetch Square events via HTTP (triggered by push)."""
        # ロックを取得
        logger.debug("Requesting fetch lock...")
        if not self._fetch_lock.acquire(blocking=False):
            logger.debug("Fetch lock busy, skipping to avoid concurrency.")
            return

        logger.debug("Fetch lock acquired.")
        try:
            # --- Keep-Alive Hack: Call fetchMyEvents to maintain global subscription ---
            # This mimics linejs behavior which uses fetchMyEvents for everything.
            # We discard the events here but update the subscriptionId and syncToken.
            if self.subscription_id and self.event_sync_token:
                try:
                    logger.debug("Calling fetchMyEvents to keep subscription alive (sub=%d, sync=%s...)",
                                 self.subscription_id, self.event_sync_token[:10])

                    # fetchMyEvents(subscriptionId, syncToken, limit, continuationToken)
                    # Note: Arguments order depends on the generated code. assuming standard order.
                    # Based on square.py: fetchMyEvents(self, subscriptionId, syncToken=None, limit=None, continuationToken=None, fetchType=None)

                    global_res = self.client.square.fetchMyEvents(
                        subscriptionId=self.subscription_id,
                        syncToken=self.event_sync_token,
                        limit=10  # Small limit just for keep-alive
                    )

                    if hasattr(global_res, 'subscription'):
                         if hasattr(global_res.subscription, 'subscription_id'):
                             new_sub = global_res.subscription.subscription_id
                             if new_sub != self.subscription_id:
                                 self.subscription_id = new_sub
                                 logger.info("Global Subscription ID updated to %d", new_sub)

                    if hasattr(global_res, 'sync_token') and global_res.sync_token:
                        self.event_sync_token = global_res.sync_token
                        # logger.debug("Global SyncToken updated")

                except Exception as e:
                    logger.warning("Keep-alive fetchMyEvents failed: %s", e)
            # --------------------------------------------------------------------------

            if not self.watched_chats:
                return

            for chat_mid in self.watched_chats:
                try:
                    sync_token = self.chat_sync_tokens.get(chat_mid)
                    cont_token = self.chat_continuation_tokens.get(chat_mid)
                    logger.debug("Fetch start for %s. Token: %s, Cont: %s",
                                 chat_mid[:12], sync_token, cont_token[:10] if cont_token else None)

                    # sync_token がない場合は、まず最新位置を取得する
                    if not sync_token:
                        logger.debug("No sync token, fetching limit=1 to init.")
                        init_res = self.client.square.fetchSquareChatEvents(chat_mid, limit=1)
                        if hasattr(init_res, 'sync_token') and init_res.sync_token:
                            self.chat_sync_tokens[chat_mid] = init_res.sync_token
                            logger.debug("Initialized Token: %s", init_res.sync_token)
                        # 初期化時はcontinuationTokenもクリアすべきか？ -> 多分YES
                        if chat_mid in self.chat_continuation_tokens:
                            del self.chat_continuation_tokens[chat_mid]
                        continue

                    response = self.client.square.fetchSquareChatEvents(
                        squareChatMid=chat_mid,
                        syncToken=sync_token,
                        continuationToken=cont_token,
                        limit=50,
                        fetchType=self.square_fetch_type
                    )

                    # Update sync token
                    if hasattr(response, 'sync_token') and response.sync_token:
                        new_token = response.sync_token
                        self.chat_sync_tokens[chat_mid] = new_token
                        if new_token != sync_token:
                            logger.debug("Token UPDATED.")
                            # Save to storage
                            if hasattr(self.client, 'token_manager'):
                                self.client.token_manager.set_square_sync_token(chat_mid, new_token)

                    # Update continuation token
                    if hasattr(response, 'continuation_token'):
                         # Noneの場合もあるので注意。Noneならクリアするか、単に上書きするか。
                         # linejsの実装: continuationToken = response.continuation_token
                         # Noneなら次はないということなので、保持しているものを更新する
                         self.chat_continuation_tokens[chat_mid] = response.continuation_token
                         if hasattr(self.client, 'token_manager') and response.continuation_token:
                             self.client.token_manager.set_square_continuation_token(chat_mid, response.continuation_token)

                    # Process events
                    events = response.events if hasattr(response, 'events') else []
                    if events:
                        first_ev = events[0]
                        last_ev = events[-1]
                        logger.debug(
                            "Fetched %d events. \nFirst: SQEqSeq=%s Type=%s\nLast:  SQEqSeq=%s Type=%s",
                            len(events),
                            getattr(first_ev, 'squareEventId', '?'), getattr(first_ev, 'type', '?'),
                            getattr(last_ev, 'squareEventId', '?'), getattr(last_ev, 'type', '?')
                        )

                    dispatcher = self._get_dispatcher()
                    for event in events:
                        if dispatcher is not None:
                            try:
                                dispatcher.dispatch_square_event(event)
                            except Exception as exc:
                                logger.debug("Square dispatch error: %s", exc)
                        if self.on_event:
                            self.on_event(ServiceType.SQUARE, event)

                except Exception as e:
                    logger.warning("Error fetching events for %s: %s", chat_mid[:12], e)
                    import traceback
                    logger.debug(traceback.format_exc())
        finally:
            self._fetch_lock.release()
            logger.debug("Fetch lock released.")



    def add_watched_chat(self, chat_mid: str):
        """Add a chat to watch list."""
        if chat_mid not in self.watched_chats:
            self.watched_chats.append(chat_mid)
            logger.debug("Watching chat: %s", chat_mid[:12])

            # Load tokens from storage
            if hasattr(self.client, 'token_manager'):
                saved_sync = self.client.token_manager.get_square_sync_token(chat_mid)
                saved_cont = self.client.token_manager.get_square_continuation_token(chat_mid)

                if saved_sync:
                    self.chat_sync_tokens[chat_mid] = saved_sync
                    logger.debug("Loaded sync token for %s", chat_mid[:12])
                if saved_cont:
                    self.chat_continuation_tokens[chat_mid] = saved_cont
                    logger.debug("Loaded continuation token for %s", chat_mid[:12])

    def remove_watched_chat(self, chat_mid: str):
        """Remove a chat from watch list."""
        if chat_mid in self.watched_chats:
            self.watched_chats.remove(chat_mid)
            if chat_mid in self.chat_sync_tokens:
                del self.chat_sync_tokens[chat_mid]
            if chat_mid in self.chat_continuation_tokens:
                del self.chat_continuation_tokens[chat_mid]
