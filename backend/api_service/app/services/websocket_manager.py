from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket


class WebSocketManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._connections: set[WebSocket] = set()
        self._subscriptions: dict[WebSocket, set[str]] = defaultdict(set)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)
            self._subscriptions.pop(websocket, None)

    async def subscribe(self, websocket: WebSocket, device_ids: list[str]) -> None:
        async with self._lock:
            self._subscriptions[websocket].update(device_ids)

    async def unsubscribe(self, websocket: WebSocket, device_ids: list[str]) -> None:
        async with self._lock:
            subscriptions = self._subscriptions.get(websocket)
            if subscriptions is None:
                return
            subscriptions.difference_update(device_ids)

    async def broadcast(self, message: dict) -> None:
        message_type = message.get("type")
        device_id = None
        data = message.get("data")
        if isinstance(data, dict):
            device_id = data.get("device_id")

        async with self._lock:
            targets = list(self._connections)
            subscriptions = {conn: set(self._subscriptions.get(conn, set())) for conn in targets}

        stale: list[WebSocket] = []
        for websocket in targets:
            if not _should_deliver(message_type, device_id, subscriptions.get(websocket, set())):
                continue
            try:
                await websocket.send_json(message)
            except Exception:
                stale.append(websocket)

        for websocket in stale:
            await self.disconnect(websocket)

    async def connection_count(self) -> int:
        async with self._lock:
            return len(self._connections)


def _should_deliver(message_type: str | None, device_id: str | None, subscribed_ids: set[str]) -> bool:
    if not subscribed_ids or message_type == "alert":
        return True
    if device_id is None:
        return True
    return device_id in subscribed_ids
