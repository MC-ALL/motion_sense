from __future__ import annotations

import time
from typing import cast

from app.models.device_config import (
    DeviceConfigPublishRequest,
    DeviceConfigPublishResult,
    DeviceType,
)
from app.services.mqtt_config_publisher import ConfigPublisher
from app.storage.store import Store


class DeviceConfigTargetNotFoundError(Exception):
    pass


class DeviceConfigConflictError(Exception):
    pass


class DeviceConfigPublisherUnavailableError(Exception):
    pass


class DeviceConfigService:
    _supported_device_types = {"wristband", "equipment", "env", "gateway"}

    def __init__(
        self,
        *,
        store: Store,
        publisher: ConfigPublisher,
        topic_prefix: str,
        default_qos: int,
        default_retain: bool,
    ) -> None:
        self._store = store
        self._publisher = publisher
        self._topic_prefix = topic_prefix
        self._default_qos = default_qos
        self._default_retain = default_retain

    async def publish_config(
        self,
        *,
        device_id: str,
        request: DeviceConfigPublishRequest,
    ) -> DeviceConfigPublishResult:
        if not request.config:
            raise ValueError("config must not be empty")

        gym_id, device_type = await self._resolve_target(
            device_id=device_id,
            request=request,
        )
        payload = dict(request.config)
        payload.setdefault("ts", int(time.time()))

        qos = request.qos if request.qos is not None else self._default_qos
        retain = request.retain if request.retain is not None else self._default_retain
        topic = f"{self._topic_prefix}/{gym_id}/{device_type}/{device_id}/config"

        try:
            await self._publisher.publish(
                topic=topic,
                payload=payload,
                qos=qos,
                retain=retain,
            )
        except RuntimeError as exc:
            raise DeviceConfigPublisherUnavailableError(str(exc)) from exc

        return DeviceConfigPublishResult(
            device_id=device_id,
            gym_id=gym_id,
            device_type=device_type,
            topic=topic,
            qos=qos,
            retain=retain,
            payload=payload,
        )

    async def _resolve_target(
        self,
        *,
        device_id: str,
        request: DeviceConfigPublishRequest,
    ) -> tuple[str, DeviceType]:
        if request.gym_id and request.device_type:
            return request.gym_id, request.device_type

        device = await self._store.get_device(device_id=device_id)
        if device is None:
            raise DeviceConfigTargetNotFoundError(
                "device snapshot not found; provide gym_id and device_type explicitly"
            )

        if request.gym_id is not None and request.gym_id != device.gym_id:
            raise DeviceConfigConflictError("request gym_id conflicts with device snapshot")
        if request.device_type is not None and request.device_type != device.device_type:
            raise DeviceConfigConflictError(
                "request device_type conflicts with device snapshot"
            )

        resolved_device_type = request.device_type or device.device_type
        if resolved_device_type not in self._supported_device_types:
            raise DeviceConfigTargetNotFoundError(
                f"unsupported device_type for config publish: {resolved_device_type}"
            )
        return request.gym_id or device.gym_id, cast(DeviceType, resolved_device_type)
