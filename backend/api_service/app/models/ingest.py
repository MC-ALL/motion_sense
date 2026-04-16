from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


IngestKind = Literal["telemetry", "alert", "binding", "status"]


class IngestItem(BaseModel):
    kind: IngestKind
    topic: str
    payload: dict[str, Any]


class IngestBatch(BaseModel):
    gateway_id: str
    sent_at: str
    items: list[IngestItem] = Field(default_factory=list)


class IngestBatchAccepted(BaseModel):
    accepted: int


class DeviceSummary(BaseModel):
    gym_id: str
    device_type: str
    device_id: str
    gateway_id: str | None = None
    display_name: str | None = None
    location: str | None = None
    metadata: dict[str, Any] | None = None
    status: str
    online: bool
    last_seen_ts: int | None = None
    last_payload: dict[str, Any] = Field(default_factory=dict)
    registered_at: str | None = None
    updated_at: str | None = None


class AlertRecord(BaseModel):
    id: int
    gym_id: str
    device_type: str
    device_id: str
    level: str
    code: str
    message: str
    priority: str | None = None
    is_ack: bool = False
    triggered_at: str
    payload: dict[str, Any] = Field(default_factory=dict)


class AlertBatchAckRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)


class AlertBatchAckResult(BaseModel):
    updated: int
    items: list[AlertRecord] = Field(default_factory=list)


class TelemetryRecord(BaseModel):
    ts: str
    gym_id: str
    device_type: str
    device_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class MetricAggregate(BaseModel):
    min: float
    max: float
    avg: float


class EnvTelemetryAggregateRecord(BaseModel):
    bucket_start: str
    bucket_end: str
    count: int
    metrics: dict[str, MetricAggregate] = Field(default_factory=dict)


class BindingEventRecord(BaseModel):
    id: int
    wristband_id: str
    equipment_id: str
    gym_id: str
    action: str
    reason: str | None = None
    ts: str
    duration_s: int | None = None
