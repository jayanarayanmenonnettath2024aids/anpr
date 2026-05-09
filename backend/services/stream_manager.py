"""
WebSocket Stream Manager.
Manages active WebSocket connections and broadcasts data.
"""
import asyncio
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class StreamManager:
    def __init__(self):
        self._detection_clients: set[WebSocket] = set()
        self._feed_clients: set[WebSocket] = set()

    async def connect_detection(self, websocket: WebSocket):
        """Accept a detection WebSocket connection."""
        await websocket.accept()
        self._detection_clients.add(websocket)
        logger.info(f"Detection client connected. Total: {len(self._detection_clients)}")

    async def connect_feed(self, websocket: WebSocket):
        """Accept a live feed WebSocket connection."""
        await websocket.accept()
        self._feed_clients.add(websocket)
        logger.info(f"Feed client connected. Total: {len(self._feed_clients)}")

    def disconnect_detection(self, websocket: WebSocket):
        """Remove a detection WebSocket connection."""
        self._detection_clients.discard(websocket)
        logger.info(f"Detection client disconnected. Total: {len(self._detection_clients)}")

    def disconnect_feed(self, websocket: WebSocket):
        """Remove a feed WebSocket connection."""
        self._feed_clients.discard(websocket)
        logger.info(f"Feed client disconnected. Total: {len(self._feed_clients)}")

    async def broadcast_detection(self, data: dict):
        """Broadcast a detection event (JSON) to all detection clients."""
        if not self._detection_clients:
            return

        disconnected = set()
        for client in self._detection_clients:
            try:
                await client.send_json(data)
            except Exception:
                disconnected.add(client)

        for client in disconnected:
            self._detection_clients.discard(client)

    async def broadcast_frame(self, jpeg_bytes: bytes):
        """Broadcast a video frame (binary) to all feed clients."""
        if not self._feed_clients:
            return

        disconnected = set()
        for client in self._feed_clients:
            try:
                await client.send_bytes(jpeg_bytes)
            except Exception:
                disconnected.add(client)

        for client in disconnected:
            self._feed_clients.discard(client)

    @property
    def detection_client_count(self):
        return len(self._detection_clients)

    @property
    def feed_client_count(self):
        return len(self._feed_clients)
