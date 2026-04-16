from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiomqtt import Client

from app.settings import MqttSettings


class SimulatorMqttPublisher:
    def __init__(self, settings: MqttSettings) -> None:
        self._settings = settings
        self._client_context: AsyncIterator[Client] | None = None
        self._client: Client | None = None

    async def __aenter__(self) -> "SimulatorMqttPublisher":
        self._client_context = _build_client_context(self._settings)
        self._client = await self._client_context.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client_context is None:
            return
        await self._client_context.__aexit__(exc_type, exc, tb)
        self._client_context = None
        self._client = None

    async def publish_json(self, *, topic: str, payload: dict[str, object], retain: bool = False) -> None:
        if self._client is None:
            raise RuntimeError("mqtt client is not connected")
        encoded_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        await self._client.publish(topic, payload=encoded_payload, qos=self._settings.qos, retain=retain)


@asynccontextmanager
async def _build_client_context(settings: MqttSettings) -> AsyncIterator[Client]:
    async with Client(
        hostname=settings.host,
        port=settings.port,
        identifier=settings.client_id,
        username=settings.username,
        password=settings.password,
        keepalive=settings.keepalive_s,
    ) as client:
        yield client
