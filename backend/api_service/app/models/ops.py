from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


HealthStatus = Literal["healthy", "degraded", "offline", "unknown"]


class BackendOpsComponent(BaseModel):
    component_id: str
    component_type: str
    display_name: str
    online: bool
    health_status: HealthStatus
    checked_at: str
    endpoint: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    detail: str | None = None


class BackendOpsHealthSummary(BaseModel):
    module_id: str
    module_type: Literal["backend"] = "backend"
    online: bool
    health_status: HealthStatus
    checked_at: str
    component_total: int = Field(ge=0)
    healthy_components: int = Field(ge=0)
    degraded_components: int = Field(ge=0)
    offline_components: int = Field(ge=0)


class BackendOpsStats(BaseModel):
    module_id: str
    module_type: Literal["backend"] = "backend"
    started_at: str
    uptime_s: int = Field(ge=0)
    storage_backend: str
    realtime_backend: str
    rest_auth_enabled: bool
    ws_auth_enabled: bool
    active_business_ws_connections: int = Field(ge=0)
    active_ops_ws_connections: int = Field(ge=0)
    ingest_batches_total: int = Field(ge=0)
    ingest_items_total: int = Field(ge=0)
    published_telemetry_total: int = Field(ge=0)
    published_alert_total: int = Field(ge=0)
    published_device_status_total: int = Field(ge=0)
    config_commands_created_total: int = Field(ge=0)
    command_results_reported_total: int = Field(ge=0)
    command_result_failures_total: int = Field(ge=0)
    last_ingest_at: str | None = None
    last_health_checked_at: str | None = None
    last_health_error: str | None = None
    last_known_health_status: HealthStatus = "unknown"
