from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


HealthStatus = Literal["healthy", "degraded", "offline", "unknown"]
AlertSeverity = Literal["info", "warning", "critical"]
AlertStatus = Literal["open", "closed"]
ModuleType = Literal["gateway", "backend"]


class ModuleHealthSummary(BaseModel):
    module_id: str
    module_type: ModuleType
    display_name: str | None = None
    online: bool
    health_status: HealthStatus
    checked_at: str
    component_total: int = Field(default=0, ge=0)
    healthy_components: int = Field(default=0, ge=0)
    degraded_components: int = Field(default=0, ge=0)
    offline_components: int = Field(default=0, ge=0)
    last_error: str | None = None


class ModuleComponent(BaseModel):
    module_id: str
    component_id: str
    component_type: str
    display_name: str
    online: bool
    health_status: HealthStatus
    checked_at: str
    endpoint: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    detail: str | None = None


class ModuleStats(BaseModel):
    module_id: str
    module_type: ModuleType
    updated_at: str
    data: dict[str, Any]


class OpsAlertRecord(BaseModel):
    id: int
    module_id: str
    module_type: ModuleType
    alert_type: str
    severity: AlertSeverity
    status: AlertStatus
    title: str
    detail: str
    created_at: str
    updated_at: str
    closed_at: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class OpsHealthListResponse(BaseModel):
    items: list[ModuleHealthSummary]
    updated_at: str | None = None


class OpsHealthDetailResponse(BaseModel):
    summary: ModuleHealthSummary
    components: list[ModuleComponent]
    stats: ModuleStats | None = None


class OpsAlertListResponse(BaseModel):
    items: list[OpsAlertRecord]


class OpsStatsResponse(BaseModel):
    items: list[ModuleStats]
    updated_at: str | None = None


class OpsSnapshotMessage(BaseModel):
    type: Literal["ops_snapshot"] = "ops_snapshot"
    data: OpsHealthListResponse


class OpsAlertMessage(BaseModel):
    type: Literal["ops_alert"] = "ops_alert"
    data: OpsAlertRecord
