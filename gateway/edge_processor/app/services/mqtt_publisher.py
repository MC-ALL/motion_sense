from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

from aiomqtt import Client

from app.settings import RuntimeSettings


LOGGER = logging.getLogger(__name__)


class MqttPublisher:
    def __init__(self, settings: RuntimeSettings) -> None:
        self._settings = settings
        self._client: Client | None = None
        self._connect_lock = asyncio.Lock()

    async def publish_json(
        self,
        *,
        topic: str,
        payload: dict[str, Any],
        qos: int,
        retain: bool,
    ) -> None:
        encoded_payload = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)

        for attempt in range(2):
            try:
                client = await self._ensure_connected()
                await client.publish(topic, payload=encoded_payload, qos=qos, retain=retain)
                return
            except Exception:
                LOGGER.exception(
                    "failed to publish mqtt message",
                    extra={"topic": topic, "attempt": attempt + 1},
                )
                await self._reset_client()
                if attempt == 1:
                    raise
                await asyncio.sleep(1)

    async def close(self) -> None:
        await self._reset_client()

    async def _ensure_connected(self) -> Client:
        if self._client is not None:
            return self._client

        async with self._connect_lock:
            if self._client is not None:
                return self._client

            client = Client(
                hostname=self._settings.mqtt.host,
                port=self._settings.mqtt.port,
                identifier=f"{self._settings.mqtt.client_id}-publisher",
                username=self._settings.mqtt.username,
                password=self._settings.mqtt.password,
            )
            await client.__aenter__()
            self._client = client
            return client

    async def _reset_client(self) -> None:
        async with self._connect_lock:
            client = self._client
            self._client = None
        if client is None:
            return
        with contextlib.suppress(Exception):
            await client.__aexit__(None, None, None)
