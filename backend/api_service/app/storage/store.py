from __future__ import annotations

from typing import Protocol

from app.models.device_config import DeviceConfigCommandRecord, GatewayCommandResultRequest
from app.models.ingest import (
    AlertRecord,
    BindingEventRecord,
    DeviceSummary,
    EnvTelemetryAggregateRecord,
    TelemetryRecord,
)
from app.models.system_health import GatewayHealthDetail, GatewayHealthReportRequest, GatewayHealthSummary


class Store(Protocol):
    async def initialize(self) -> None: ...

    async def close(self) -> None: ...

    async def upsert_device(
        self,
        *,
        gym_id: str,
        device_type: str,
        device_id: str,
        status: str,
        online: bool,
        last_seen_ts: int | None,
        payload: dict,
    ) -> DeviceSummary: ...

    async def add_alert(
        self,
        *,
        gym_id: str,
        device_type: str,
        device_id: str,
        level: str,
        code: str,
        message: str,
        priority: str | None,
        triggered_at: str,
        payload: dict,
    ) -> AlertRecord: ...

    async def record_binding_event(
        self,
        *,
        gym_id: str,
        wristband_id: str,
        equipment_id: str,
        action: str,
        reason: str | None,
        ts: int | None,
    ) -> None: ...

    async def record_telemetry(
        self,
        *,
        gym_id: str,
        device_type: str,
        device_id: str,
        payload: dict,
    ) -> None: ...

    async def list_devices(
        self,
        device_type: str | None = None,
        status: str | None = None,
    ) -> list[DeviceSummary]: ...

    async def get_device(
        self,
        *,
        device_id: str,
    ) -> DeviceSummary | None: ...

    async def list_alerts(
        self,
        level: str | None = None,
        is_ack: bool | None = None,
    ) -> list[AlertRecord]: ...

    async def get_alert(
        self,
        *,
        alert_id: int,
    ) -> AlertRecord | None: ...

    async def ack_alert(
        self,
        *,
        alert_id: int,
    ) -> AlertRecord | None: ...

    async def batch_ack_alerts(
        self,
        *,
        alert_ids: list[int],
    ) -> list[AlertRecord]: ...

    async def list_telemetry(
        self,
        *,
        device_type: str,
        device_id: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[TelemetryRecord]: ...

    async def list_binding_events(
        self,
        *,
        wristband_id: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[BindingEventRecord]: ...

    async def aggregate_env_telemetry(
        self,
        *,
        device_id: str,
        interval: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[EnvTelemetryAggregateRecord]: ...

    async def upsert_gateway_health_report(
        self,
        *,
        report: GatewayHealthReportRequest,
    ) -> GatewayHealthDetail: ...

    async def list_gateway_health_summaries(
        self,
        *,
        gym_id: str | None = None,
        gateway_id: str | None = None,
        component_type: str | None = None,
        overall_status: str | None = None,
    ) -> list[GatewayHealthSummary]: ...

    async def get_gateway_health_detail(
        self,
        *,
        gateway_id: str,
    ) -> GatewayHealthDetail | None: ...

    async def create_device_config_command(
        self,
        *,
        gateway_id: str,
        gym_id: str,
        device_type: str,
        device_id: str,
        topic: str,
        qos: int,
        retain: bool,
        payload: dict,
        max_attempts: int,
        retry_backoff_s: int,
        next_retry_at: str,
        expires_at: str,
    ) -> DeviceConfigCommandRecord: ...

    async def list_pending_device_config_commands(
        self,
        *,
        gateway_id: str,
        limit: int = 100,
        delivery_lease_s: int = 15,
    ) -> list[DeviceConfigCommandRecord]: ...

    async def get_device_config_command(
        self,
        *,
        command_id: str,
    ) -> DeviceConfigCommandRecord | None: ...

    async def update_device_config_command_result(
        self,
        *,
        gateway_id: str,
        command_id: str,
        result: GatewayCommandResultRequest,
    ) -> DeviceConfigCommandRecord | None: ...
