from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass

from fastapi import WebSocket

from app.models.auth import AuthUser


@dataclass(slots=True)
class WebSocketAccessScope:
    username: str
    role: str
    gym_ids: set[str]
    device_ids: set[str]


class WebSocketManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._connections: set[WebSocket] = set()
        self._subscriptions: dict[WebSocket, set[str]] = defaultdict(set)
        self._access_scopes: dict[WebSocket, WebSocketAccessScope] = {}

    async def connect(self, websocket: WebSocket, user: AuthUser) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
            self._access_scopes[websocket] = WebSocketAccessScope(
                username=user.username,
                role=user.role,
                gym_ids=set(user.gym_ids),
                device_ids=set(user.device_ids),
            )

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)
            self._subscriptions.pop(websocket, None)
            self._access_scopes.pop(websocket, None)

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
        gym_id = None
        target_username = None
        target_gym_ids: set[str] = set()
        target_device_ids: set[str] = set()
        data = message.get("data")
        if isinstance(data, dict):
            device_id = data.get("device_id")
            gym_id = data.get("gym_id")
        scope = message.get("scope")
        if isinstance(scope, dict):
            raw_target_gym_ids = scope.get("gym_ids")
            raw_target_device_ids = scope.get("device_ids")
            target_username = scope.get("user_id")
            if isinstance(raw_target_gym_ids, list):
                target_gym_ids = {str(item) for item in raw_target_gym_ids}
            if isinstance(raw_target_device_ids, list):
                target_device_ids = {str(item) for item in raw_target_device_ids}

        async with self._lock:
            targets = list(self._connections)
            subscriptions = {conn: set(self._subscriptions.get(conn, set())) for conn in targets}
            access_scopes = {conn: self._access_scopes.get(conn) for conn in targets}

        stale: list[WebSocket] = []
        for websocket in targets:
            if not _should_deliver(
                message_type=message_type,
                gym_id=gym_id,
                device_id=device_id,
                target_username=target_username if isinstance(target_username, str) else None,
                target_gym_ids=target_gym_ids,
                target_device_ids=target_device_ids,
                subscribed_ids=subscriptions.get(websocket, set()),
                access_scope=access_scopes.get(websocket),
            ):
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


def _should_deliver(
    *,
    message_type: str | None,
    gym_id: str | None,
    device_id: str | None,
    target_username: str | None,
    target_gym_ids: set[str],
    target_device_ids: set[str],
    subscribed_ids: set[str],
    access_scope: WebSocketAccessScope | None,
) -> bool:
    if access_scope is not None and not _has_access(
        access_scope,
        message_type=message_type,
        gym_id=gym_id,
        device_id=device_id,
        target_username=target_username,
        target_gym_ids=target_gym_ids,
        target_device_ids=target_device_ids,
    ):
        return False
    if not subscribed_ids or message_type == "alert":
        return True
    if device_id is None:
        return True
    return device_id in subscribed_ids


def _has_access(
    access_scope: WebSocketAccessScope,
    *,
    message_type: str | None,
    gym_id: str | None,
    device_id: str | None,
    target_username: str | None,
    target_gym_ids: set[str],
    target_device_ids: set[str],
) -> bool:
    if message_type == "ai_report":
        return _has_ai_report_access(
            access_scope,
            target_username=target_username,
            target_gym_ids=target_gym_ids,
            target_device_ids=target_device_ids,
        )
    if access_scope.role in {"admin", "anonymous"}:
        return True
    if access_scope.role == "teacher":
        return (device_id is not None and device_id in access_scope.device_ids) or (
            gym_id is not None and gym_id in access_scope.gym_ids
        )
    if access_scope.role == "student":
        return device_id is not None and device_id in access_scope.device_ids
    return False


def _has_ai_report_access(
    access_scope: WebSocketAccessScope,
    *,
    target_username: str | None,
    target_gym_ids: set[str],
    target_device_ids: set[str],
) -> bool:
    if access_scope.role in {"admin", "anonymous"}:
        return True
    if target_username is not None and access_scope.username == target_username:
        return True
    if access_scope.role != "teacher":
        return False
    if access_scope.gym_ids.intersection(target_gym_ids):
        return True
    if access_scope.device_ids.intersection(target_device_ids):
        return True
    return False
