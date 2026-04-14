from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DeviceType = Literal["wristband", "equipment", "env", "gateway"]


class DeviceConfigPublishRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)
    gym_id: str | None = None
    device_type: DeviceType | None = None
    qos: int | None = Field(default=None, ge=0, le=2)
    retain: bool | None = None


class DeviceConfigPublishResult(BaseModel):
    device_id: str
    gym_id: str
    device_type: DeviceType
    topic: str
    qos: int
    retain: bool
    payload: dict[str, Any]
