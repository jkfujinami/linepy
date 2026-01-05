"""
Polling Manager for LINEPY

High-frequency polling alternative to LEGY Push connection.
Each chat gets its own worker thread for maximum throughput.
"""

import threading
import queue
import time
import logging
from typing import List, Callable, Optional, Dict, Any

logger = logging.getLogger("linepy.polling")


class ChatWorker(threading.Thread):
    """
    Worker thread for a single chat.
    Continuously fetches events via fetchSquareChatEvents.
    """

    def __init__(
        self,
        client,
        chat_mid: str,
        event_queue: queue.Queue,
        token_manager,
        fetch_type: int = 2,
    ):
        super().__init__(daemon=True)
        self.client = client
        self.chat_mid = chat_mid
        self.event_queue = event_queue
        self.token_manager = token_manager
        self.fetch_type = fetch_type

        self._running = False

        # Load sync token from storage
        self.sync_token: Optional[str] = None
        self.continuation_token: Optional[str] = None
        if token_manager:
            self.sync_token = token_manager.get_square_sync_token(chat_mid)
            self.continuation_token = token_manager.get_square_continuation_token(chat_mid)
            if self.sync_token:
                logger.debug("[%s] Loaded token from storage", chat_mid[:8])

    def run(self):
        self._running = True
        logger.info("[%s] ChatWorker started", self.chat_mid[:8])

        # Initialize token if not loaded
        if not self.sync_token:
            self._init_token()

        # Main loop
        while self._running:
            try:
                self._fetch_once()
            except Exception as e:
                # Check for rate limit (429)
                error_str = str(e).lower()
                if "429" in error_str or "too many" in error_str or "rate" in error_str:
                    logger.warning("[%s] Rate limited, sleeping 2s", self.chat_mid[:8])
                    time.sleep(2)
                else:
                    # Other errors: brief pause then continue
                    time.sleep(0.1)

        logger.info("[%s] ChatWorker stopped", self.chat_mid[:8])

    def stop(self):
        self._running = False

    def _init_token(self):
        """Fetch initial sync token (limit=1 to get latest position)."""
        try:
            res = self.client.square.fetchSquareChatEvents(
                self.chat_mid, limit=1, fetchType=self.fetch_type
            )
            if hasattr(res, 'syncToken') and res.syncToken:
                self.sync_token = res.syncToken
                if self.token_manager:
                    self.token_manager.set_square_sync_token(self.chat_mid, self.sync_token)
                logger.debug("[%s] Initialized token", self.chat_mid[:8])
        except Exception as e:
            logger.warning("[%s] Failed to init token: %s", self.chat_mid[:8], e)

    def _fetch_once(self):
        """Fetch events once and push to queue."""
        if not self.sync_token:
            self._init_token()
            return

        res = self.client.square.fetchSquareChatEvents(
            squareChatMid=self.chat_mid,
            syncToken=self.sync_token,
            continuationToken=self.continuation_token,
            limit=50,
            fetchType=self.fetch_type,
        )

        # Update sync token
        if hasattr(res, 'syncToken') and res.syncToken:
            self.sync_token = res.syncToken
            if self.token_manager:
                self.token_manager.set_square_sync_token(self.chat_mid, self.sync_token)

        # Update continuation token
        if hasattr(res, 'continuationToken'):
            self.continuation_token = res.continuationToken
            if self.token_manager and res.continuationToken:
                self.token_manager.set_square_continuation_token(
                    self.chat_mid, res.continuationToken
                )

        # Push events to queue
        events = getattr(res, 'events', [])
        for event in events:
            # (service_type, event)
            self.event_queue.put((3, event))  # 3 = Square


class DispatchWorker(threading.Thread):
    """
    Worker thread that dispatches events to the callback.
    Pulls events from the queue and calls on_event.
    """

    def __init__(self, event_queue: queue.Queue, on_event: Callable):
        super().__init__(daemon=True)
        self.event_queue = event_queue
        self.on_event = on_event
        self._running = False

    def run(self):
        self._running = True
        logger.info("DispatchWorker started")

        while self._running:
            try:
                service_type, event = self.event_queue.get(timeout=0.1)
                if self.on_event:
                    try:
                        self.on_event(service_type, event)
                    except Exception as e:
                        logger.exception("Error in on_event callback: %s", e)
            except queue.Empty:
                continue

        logger.info("DispatchWorker stopped")

    def stop(self):
        self._running = False


class PollingManager:
    """
    Manages high-frequency polling for Square events.

    Creates one ChatWorker thread per watched chat.
    All events are funneled through a single DispatchWorker.
    """

    def __init__(self, client):
        self.client = client
        self.token_manager = getattr(client, 'token_manager', None)

        self.watched_chats: List[str] = []
        self.on_event: Optional[Callable[[int, Any], None]] = None
        self.fetch_type: int = 2

        self._running = False
        self._workers: Dict[str, ChatWorker] = {}
        self._dispatcher: Optional[DispatchWorker] = None
        self._event_queue: queue.Queue = queue.Queue()

    def add_watched_chat(self, chat_mid: str):
        """Add a chat to watch list."""
        if chat_mid not in self.watched_chats:
            self.watched_chats.append(chat_mid)

            # If already running, spawn a new worker immediately
            if self._running and chat_mid not in self._workers:
                worker = ChatWorker(
                    self.client,
                    chat_mid,
                    self._event_queue,
                    self.token_manager,
                    self.fetch_type,
                )
                self._workers[chat_mid] = worker
                worker.start()

    def remove_watched_chat(self, chat_mid: str):
        """Remove a chat from watch list."""
        if chat_mid in self.watched_chats:
            self.watched_chats.remove(chat_mid)

        # Stop the worker if running
        if chat_mid in self._workers:
            self._workers[chat_mid].stop()
            del self._workers[chat_mid]

    def start(
        self,
        watched_chats: List[str] = None,
        on_event: Optional[Callable[[int, Any], None]] = None,
        fetch_type: int = 2,
    ):
        """
        Start polling.

        Args:
            watched_chats: List of chat MIDs to watch
            on_event: Callback function(service_type, event)
            fetch_type: 1=Default, 2=PrefetchByServer (recommended)
        """
        if self._running:
            logger.warning("Polling is already running")
            return

        if watched_chats:
            self.watched_chats = watched_chats
        if on_event:
            self.on_event = on_event
        self.fetch_type = fetch_type

        self._running = True
        self._event_queue = queue.Queue()

        # Start dispatcher
        self._dispatcher = DispatchWorker(self._event_queue, self.on_event)
        self._dispatcher.start()

        # Start chat workers
        for chat_mid in self.watched_chats:
            worker = ChatWorker(
                self.client,
                chat_mid,
                self._event_queue,
                self.token_manager,
                self.fetch_type,
            )
            self._workers[chat_mid] = worker
            worker.start()

        logger.info(
            "Polling started: %d chat worker(s), 1 dispatcher",
            len(self._workers)
        )

    def stop(self):
        """Stop polling."""
        if not self._running:
            return

        self._running = False

        # Stop all chat workers
        for worker in self._workers.values():
            worker.stop()

        # Stop dispatcher
        if self._dispatcher:
            self._dispatcher.stop()

        # Wait for threads to finish
        for worker in self._workers.values():
            worker.join(timeout=1.0)
        if self._dispatcher:
            self._dispatcher.join(timeout=1.0)

        self._workers.clear()
        self._dispatcher = None

        logger.info("Polling stopped")
