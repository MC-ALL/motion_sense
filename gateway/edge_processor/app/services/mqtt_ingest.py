from __future__ import annotations

import json
import logging
from typing import Any

from aiomqtt import Client

from app.models.ingest_item import IngestItem
from app.settings import RuntimeSettings
from app.utils.topic_parser import parse_topic


LOGGER = logging.getLogger(__name__)


async def mqtt_ingest_loop(
    settings: RuntimeSettings,
    event_buffer,
    runtime_config_manager,
) -> None:
    while True:
        try:
            async with Client(
                hostname=settings.mqtt.host,
                port=settings.mqtt.port,
                identifier=settings.mqtt.client_id,
                username=settings.mqtt.username,
                password=settings.mqtt.password,
            ) as client:
                for topic in settings.mqtt.topic_patterns:
                    await client.subscribe(topic, qos=settings.mqtt.qos)

                LOGGER.info(
                    "connected to mqtt broker",
                    extra={
                        "host": settings.mqtt.host,
                        "port": settings.mqtt.port,
                        "username": settings.mqtt.username,
                        "topics": settings.mqtt.topic_patterns,
                    },
                )

                async for message in client.messages:
                    topic = str(message.topic)
                    payload = _decode_json_payload(topic, message.payload)
                    parsed = parse_topic(topic)

                    if parsed.action == "config" and parsed.device_type == "gateway":
                        if parsed.device_id == settings.gateway_id:
                            runtime_config_manager.update_from_gateway_config(payload)
                        continue

                    if parsed.action not in {"telemetry", "alert", "binding", "status"}:
                        continue

                    LOGGER.info("received mqtt event", extra={"kind": parsed.action, "topic": topic})
                    await event_buffer.append(
                        IngestItem(kind=parsed.action, topic=topic, payload=payload),
                        parsed,
                    )
        except Exception:
            LOGGER.exception("mqtt ingest loop failed; retrying")
            await __import__("asyncio").sleep(3)


def _decode_json_payload(topic: str, payload: bytes | bytearray | memoryview) -> dict[str, Any]:
    try:
        return json.loads(bytes(payload).decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON payload on topic {topic}: {exc}") from exc
