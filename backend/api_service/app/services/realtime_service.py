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
        self._telemetry_flush_task: asyncio.Task[None] | None = None
        self._telemetry_buffer: dict[str, dict] = {}
        self._telemetry_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._settings.realtime_backend != "redis":
            return

        self._redis = Redis.from_url(self._settings.redis.url(), decode_responses=True)
        await self._redis.ping()
        self._listener_task = asyncio.create_task(self._listen(), name="redis-realtime-listener")

    async def stop(self) -> None:
        telemetry_flush_task = self._telemetry_flush_task
        self._telemetry_flush_task = None
        if telemetry_flush_task is not None:
            telemetry_flush_task.cancel()
            try:
                await telemetry_flush_task
            except asyncio.CancelledError:
                pass

        await self.flush_telemetry()

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
        if self._should_buffer_telemetry(message):
            await self._buffer_telemetry(message)
            return

        await self._deliver(message)

    async def flush_telemetry(self) -> None:
        async with self._telemetry_lock:
            messages = list(self._telemetry_buffer.values())
            self._telemetry_buffer = {}
            self._telemetry_flush_task = None

        for message in messages:
            await self._deliver(message)

    async def _deliver(self, message: dict) -> None:
        if self._settings.realtime_backend != "redis":
            await self._websocket_manager.broadcast(message)
            return

        if self._redis is None:
            raise RuntimeError("redis realtime service is not started")

        await self._redis.publish(
            self._settings.redis.channel,
            json.dumps(message, separators=(",", ":"), ensure_ascii=True),
        )

    def _should_buffer_telemetry(self, message: dict) -> bool:
        return (
            message.get("type") == "telemetry"
            and self._settings.realtime_telemetry_flush_interval_ms > 0
        )

    async def _buffer_telemetry(self, message: dict) -> None:
        async with self._telemetry_lock:
            self._telemetry_buffer[_telemetry_buffer_key(message)] = message
            if self._telemetry_flush_task is None or self._telemetry_flush_task.done():
                self._telemetry_flush_task = asyncio.create_task(
                    self._flush_telemetry_later(),
                    name="realtime-telemetry-flush",
                )

    async def _flush_telemetry_later(self) -> None:
        await asyncio.sleep(self._settings.realtime_telemetry_flush_interval_ms / 1000)
        await self.flush_telemetry()

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


def _telemetry_buffer_key(message: dict) -> str:
    data = message.get("data")
    if not isinstance(data, dict):
        return str(id(message))
    gym_id = data.get("gym_id", "")
    device_type = data.get("device_type", "")
    device_id = data.get("device_id", "")
    return f"{gym_id}:{device_type}:{device_id}"
