from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


HealthStatus = Literal["healthy", "degraded", "offline", "unknown"]


class GatewayOpsHealthSummary(BaseModel):
    module_id: str
    module_type: Literal["gateway"] = "gateway"
    gateway_id: str
    gym_id: str
    online: bool
    health_status: HealthStatus
    checked_at: str
    component_total: int = Field(ge=0)
    healthy_components: int = Field(ge=0)
    degraded_components: int = Field(ge=0)
    offline_components: int = Field(ge=0)


class GatewayOpsStats(BaseModel):
    module_id: str
    module_type: Literal["gateway"] = "gateway"
    gateway_id: str
    gym_id: str
    started_at: str
    uptime_s: int = Field(ge=0)
    active_ops_ws_connections: int = Field(ge=0)
    mqtt_events_received_total: int = Field(ge=0)
    telemetry_events_total: int = Field(ge=0)
    alert_events_total: int = Field(ge=0)
    binding_events_total: int = Field(ge=0)
    status_events_total: int = Field(ge=0)
    generated_alerts_total: int = Field(ge=0)
    generated_status_total: int = Field(ge=0)
    command_polls_total: int = Field(ge=0)
    commands_executed_total: int = Field(ge=0)
    command_failures_total: int = Field(ge=0)
    batch_upload_success_total: int = Field(ge=0)
    batch_upload_failure_total: int = Field(ge=0)
    last_batch_size: int = Field(default=0, ge=0)
    last_batch_uploaded_at: str | None = None
    last_batch_error: str | None = None
    health_report_success_total: int = Field(ge=0)
    health_report_failure_total: int = Field(ge=0)
    last_health_checked_at: str | None = None
    last_health_report_error: str | None = None
    last_known_health_status: HealthStatus = "unknown"
    batch_interval_s: int = Field(ge=1)
    command_poll_interval_s: int = Field(ge=1)
    health_interval_s: int = Field(ge=1)
    replay_batch_size: int = Field(ge=1)


class GatewayOpsSnapshotMessage(BaseModel):
    type: Literal["ops_snapshot"] = "ops_snapshot"
    data: GatewayOpsHealthSummary


class GatewayOpsStatsMessage(BaseModel):
    type: Literal["ops_stats"] = "ops_stats"
    data: dict[str, Any]
