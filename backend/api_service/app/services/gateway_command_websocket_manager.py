from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket

from app.models.device_config import DeviceConfigCommandRecord


class GatewayCommandWebSocketManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._connections_by_gateway: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, gateway_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections_by_gateway[gateway_id].add(websocket)

    async def disconnect(self, gateway_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._connections_by_gateway.get(gateway_id)
            if connections is None:
                return
            connections.discard(websocket)
            if not connections:
                self._connections_by_gateway.pop(gateway_id, None)

    async def notify_command_ready(self, command: DeviceConfigCommandRecord) -> None:
        message = {
            "type": "command_ready",
            "data": {
                "gateway_id": command.gateway_id,
                "command_id": command.command_id,
                "device_id": command.device_id,
                "device_type": command.device_type,
                "issued_at": command.created_at,
            },
        }
        await self._broadcast(command.gateway_id, message)

    async def connection_count(self) -> int:
        async with self._lock:
            return sum(len(connections) for connections in self._connections_by_gateway.values())

    async def _broadcast(self, gateway_id: str, message: dict[str, object]) -> None:
        async with self._lock:
            targets = list(self._connections_by_gateway.get(gateway_id, set()))

        stale: list[WebSocket] = []
        for websocket in targets:
            try:
                await websocket.send_json(message)
            except Exception:
                stale.append(websocket)

        for websocket in stale:
            await self.disconnect(gateway_id, websocket)
