from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DeviceType = Literal["wristband", "equipment", "env", "gateway"]
CommandStatus = Literal["pending", "succeeded", "failed", "timed_out"]


class DeviceConfigCommandRecord(BaseModel):
    """Configuration command leased from the backend command queue."""

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
    attempt_count: int = 0
    max_attempts: int
    retry_backoff_s: int
    last_attempt_at: str | None = None
    next_retry_at: str | None = None
    leased_until: str | None = None
    expires_at: str
    created_at: str
    updated_at: str
    result_detail: str | None = None
    result_payload: dict[str, Any] = Field(default_factory=dict)


class GatewayPendingCommandList(BaseModel):
    """Pending command response returned by the backend for one gateway."""

    gateway_id: str
    items: list[DeviceConfigCommandRecord] = Field(default_factory=list)


class GatewayCommandResultRequest(BaseModel):
    """Execution result posted back after the gateway handles a command."""

    status: Literal["succeeded", "failed"]
    reported_at: str
    detail: str | None = None
    result_payload: dict[str, Any] = Field(default_factory=dict)
