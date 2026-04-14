from __future__ import annotations

import time
from typing import cast

from app.models.device_config import (
    DeviceConfigCommandRecord,
    DeviceConfigPublishRequest,
    DeviceConfigPublishResult,
    DeviceType,
    GatewayCommandResultRequest,
)
from app.storage.store import Store


class DeviceConfigTargetNotFoundError(Exception):
    pass


class DeviceConfigConflictError(Exception):
    pass


class DeviceConfigCommandNotFoundError(Exception):
    pass


class DeviceConfigCommandGatewayMismatchError(Exception):
    pass


class DeviceConfigService:
    _supported_device_types = {"wristband", "equipment", "env", "gateway"}

    def __init__(
        self,
        *,
        store: Store,
        topic_prefix: str,
        default_qos: int,
        default_retain: bool,
        pending_fetch_limit: int = 100,
    ) -> None:
        self._store = store
        self._topic_prefix = topic_prefix
        self._default_qos = default_qos
        self._default_retain = default_retain
        self._pending_fetch_limit = pending_fetch_limit

    async def publish_config(
        self,
        *,
        device_id: str,
        request: DeviceConfigPublishRequest,
    ) -> DeviceConfigPublishResult:
        if not request.config:
            raise ValueError("config must not be empty")

        gym_id, gateway_id, device_type = await self._resolve_target(
            device_id=device_id,
            request=request,
        )
        payload = dict(request.config)
        payload.setdefault("ts", int(time.time()))

        qos = request.qos if request.qos is not None else self._default_qos
        retain = request.retain if request.retain is not None else self._default_retain
        topic = f"{self._topic_prefix}/{gym_id}/{device_type}/{device_id}/config"
        record = await self._store.create_device_config_command(
            gateway_id=gateway_id,
            gym_id=gym_id,
            device_type=device_type,
            device_id=device_id,
            topic=topic,
            qos=qos,
            retain=retain,
            payload=payload,
        )
        return DeviceConfigPublishResult.model_validate(record.model_dump())

    async def list_pending_commands(
        self,
        *,
        gateway_id: str,
    ) -> list[DeviceConfigCommandRecord]:
        return await self._store.list_pending_device_config_commands(
            gateway_id=gateway_id,
            limit=self._pending_fetch_limit,
        )

    async def get_command(
        self,
        *,
        command_id: str,
    ) -> DeviceConfigCommandRecord:
        command = await self._store.get_device_config_command(command_id=command_id)
        if command is None:
            raise DeviceConfigCommandNotFoundError("device config command not found")
        return command

    async def report_command_result(
        self,
        *,
        gateway_id: str,
        command_id: str,
        result: GatewayCommandResultRequest,
    ) -> DeviceConfigCommandRecord:
        command = await self._store.get_device_config_command(command_id=command_id)
        if command is None:
            raise DeviceConfigCommandNotFoundError("device config command not found")
        if command.gateway_id != gateway_id:
            raise DeviceConfigCommandGatewayMismatchError(
                "device config command does not belong to this gateway"
            )

        updated = await self._store.update_device_config_command_result(
            gateway_id=gateway_id,
            command_id=command_id,
            result=result,
        )
        if updated is None:
            raise DeviceConfigCommandNotFoundError("device config command not found")
        return updated

    async def _resolve_target(
        self,
        *,
        device_id: str,
        request: DeviceConfigPublishRequest,
    ) -> tuple[str, str, DeviceType]:
        if request.gym_id and request.gateway_id and request.device_type:
            return request.gym_id, request.gateway_id, request.device_type

        device = await self._store.get_device(device_id=device_id)
        if device is None:
            if request.gym_id and request.device_type:
                return request.gym_id, self._require_gateway_id(device_id=device_id, request=request), request.device_type
            raise DeviceConfigTargetNotFoundError(
                "device snapshot not found; provide gym_id, gateway_id and device_type explicitly"
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

        resolved_gateway_id = self._resolve_gateway_id(
            device_id=device_id,
            device_type=cast(DeviceType, resolved_device_type),
            request=request,
            device_payload=device.last_payload,
        )
        return device.gym_id, resolved_gateway_id, cast(DeviceType, resolved_device_type)

    def _resolve_gateway_id(
        self,
        *,
        device_id: str,
        device_type: DeviceType,
        request: DeviceConfigPublishRequest,
        device_payload: dict[str, object],
    ) -> str:
        if request.gateway_id:
            return request.gateway_id
        if device_type == "gateway":
            return device_id
        payload_gateway_id = device_payload.get("gateway_id")
        if isinstance(payload_gateway_id, str) and payload_gateway_id:
            return payload_gateway_id
        raise DeviceConfigTargetNotFoundError(
            "gateway_id is required for non-gateway config commands"
        )

    def _require_gateway_id(
        self,
        *,
        device_id: str,
        request: DeviceConfigPublishRequest,
    ) -> str:
        if request.gateway_id:
            return request.gateway_id
        if request.device_type == "gateway":
            return device_id
        raise DeviceConfigTargetNotFoundError(
            "gateway_id is required for non-gateway config commands"
        )
