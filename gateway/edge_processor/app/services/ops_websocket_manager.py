from __future__ import annotations

import asyncio

from fastapi import WebSocket


class OpsWebSocketManager:
    """Track connected ops WebSocket clients and broadcast snapshots."""

    def __init__(self) -> None:
        """Create an empty ops connection registry."""
        self._lock = asyncio.Lock()
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new ops WebSocket connection.

        :param websocket: FastAPI WebSocket for an authenticated ops client.
        """
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket from the active broadcast set.

        :param websocket: Connection to remove.
        """
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, message: dict) -> None:
        """Broadcast a JSON-serializable message to all current clients.

        :param message: WebSocket message envelope to send.
        """
        async with self._lock:
            targets = list(self._connections)

        stale: list[WebSocket] = []
        for websocket in targets:
            try:
                await websocket.send_json(message)
            except Exception:
                stale.append(websocket)

        for websocket in stale:
            await self.disconnect(websocket)

    async def connection_count(self) -> int:
        """Return the number of active ops WebSocket connections."""
        async with self._lock:
            return len(self._connections)
