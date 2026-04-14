from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ComponentType = Literal[
    "gateway_api",
    "edge_processor",
    "mqtt_broker",
    "local_timeseries_db",
    "backend_api",
    "other",
]
HealthStatus = Literal["healthy", "degraded", "offline", "unknown"]


class GatewayHealthComponentInput(BaseModel):
    component_id: str
    component_type: ComponentType
    display_name: str
    online: bool
    health_status: HealthStatus
    checked_at: str
    endpoint: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    detail: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class GatewayHealthReportRequest(BaseModel):
    gateway_id: str
    gym_id: str
    reported_at: str
    components: list[GatewayHealthComponentInput] = Field(default_factory=list, min_length=1)
