from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DeviceType = Literal["wristband", "equipment", "env", "gateway"]
CommandStatus = Literal["pending", "succeeded", "failed"]


class DeviceConfigCommandRecord(BaseModel):
    command_id: str
    gateway_id: str
    device_id: str
    gym_id: str
    device_type: DeviceType
    topic: str
    qos: int
    retain: bool
    payload: dict[str, Any] = Field(default_factory=dict)
    status: CommandStatus
    created_at: str
    updated_at: str
    result_detail: str | None = None
    result_payload: dict[str, Any] = Field(default_factory=dict)


class GatewayPendingCommandList(BaseModel):
    gateway_id: str
    items: list[DeviceConfigCommandRecord] = Field(default_factory=list)


class GatewayCommandResultRequest(BaseModel):
    status: Literal["succeeded", "failed"]
    reported_at: str
    detail: str | None = None
    result_payload: dict[str, Any] = Field(default_factory=dict)
