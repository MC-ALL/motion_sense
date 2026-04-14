from __future__ import annotations

import asyncio
import json

from redis.asyncio import Redis

from app.services.websocket_manager import WebSocketManager
from app.settings import RuntimeSettings


class RealtimeService:
    def __init__(self, settings: RuntimeSettings, websocket_manager: WebSocketManager) -> None:
        self._settings = settings
        self._websocket_manager = websocket_manager
        self._redis: Redis | None = None
        self._listener_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._settings.realtime_backend != "redis":
            return

        self._redis = Redis.from_url(self._settings.redis.url(), decode_responses=True)
        await self._redis.ping()
        self._listener_task = asyncio.create_task(self._listen(), name="redis-realtime-listener")

    async def stop(self) -> None:
        if self._listener_task is not None:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def publish(self, message: dict) -> None:
        if self._settings.realtime_backend != "redis":
            await self._websocket_manager.broadcast(message)
            return

        if self._redis is None:
            raise RuntimeError("redis realtime service is not started")

        await self._redis.publish(
            self._settings.redis.channel,
            json.dumps(message, separators=(",", ":"), ensure_ascii=True),
        )

    async def _listen(self) -> None:
        assert self._redis is not None
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._settings.redis.channel)

        try:
            async for item in pubsub.listen():
                if item is None or item.get("type") != "message":
                    continue
                data = item.get("data")
                if not isinstance(data, str):
                    continue
                try:
                    message = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if isinstance(message, dict):
                    await self._websocket_manager.broadcast(message)
        finally:
            await pubsub.aclose()
