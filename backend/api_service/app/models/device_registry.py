from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DeviceRegistryType = Literal["wristband", "equipment", "env", "gateway"]


class DeviceRegistrationRequest(BaseModel):
    gym_id: str
    device_type: DeviceRegistryType
    device_id: str
    gateway_id: str | None = None
    display_name: str | None = None
    location: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeviceRegistrationUpdateRequest(BaseModel):
    gateway_id: str | None = None
    display_name: str | None = None
    location: str | None = None
    metadata: dict[str, Any] | None = None


class DeviceDeleteResponse(BaseModel):
    ok: bool = True
