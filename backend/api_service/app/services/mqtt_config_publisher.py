from __future__ import annotations

import json
from contextlib import AsyncExitStack
from typing import Any, Protocol

from app.settings import RuntimeSettings


class ConfigPublisher(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def publish(
        self,
        *,
        topic: str,
        payload: dict[str, Any],
        qos: int,
        retain: bool,
    ) -> None: ...


class MqttConfigPublisher:
    def __init__(self, settings: RuntimeSettings) -> None:
        self._settings = settings
        self._exit_stack: AsyncExitStack | None = None
        self._client: Any | None = None

    async def start(self) -> None:
        if self._settings.mqtt.backend != "mqtt":
            return

        try:
            import aiomqtt
        except ImportError as exc:
            raise RuntimeError("aiomqtt is required for mqtt config publishing") from exc

        self._exit_stack = AsyncExitStack()
        self._client = await self._exit_stack.enter_async_context(
            aiomqtt.Client(
                hostname=self._settings.mqtt.host,
                port=self._settings.mqtt.port,
                username=self._settings.mqtt.username,
                password=self._settings.mqtt.password,
                identifier=self._settings.mqtt.client_id,
            )
        )

    async def stop(self) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
            self._exit_stack = None
        self._client = None

    async def publish(
        self,
        *,
        topic: str,
        payload: dict[str, Any],
        qos: int,
        retain: bool,
    ) -> None:
        if self._settings.mqtt.backend != "mqtt":
            raise RuntimeError("mqtt config publishing backend is disabled")
        if self._client is None:
            raise RuntimeError("mqtt config publisher is not started")

        await self._client.publish(
            topic=topic,
            payload=json.dumps(payload, separators=(",", ":"), ensure_ascii=True),
            qos=qos,
            retain=retain,
        )
