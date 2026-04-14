from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.models.ingest import (
    AlertRecord,
    BindingEventRecord,
    DeviceSummary,
    EnvTelemetryAggregateRecord,
    TelemetryRecord,
)
from app.models.system_health import (
    GatewayHealthComponentRecord,
    GatewayHealthDetail,
    GatewayHealthReportRequest,
    GatewayHealthSummary,
    derive_overall_status,
)
from app.storage.telemetry_aggregate import aggregate_env_records


class EventStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._devices: dict[str, DeviceSummary] = {}
        self._alerts: list[AlertRecord] = []
        self._bindings: list[BindingEventRecord] = []
        self._telemetry: list[TelemetryRecord] = []
        self._gateway_health_components: dict[tuple[str, str], GatewayHealthComponentRecord] = {}
        self._next_alert_id = 1
        self._next_binding_id = 1

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None

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
    ) -> DeviceSummary:
        async with self._lock:
            key = _device_key(gym_id, device_type, device_id)
            device = DeviceSummary(
                gym_id=gym_id,
                device_type=device_type,
                device_id=device_id,
                status=status,
                online=online,
                last_seen_ts=last_seen_ts,
                last_payload=payload,
            )
            self._devices[key] = device
            return device

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
    ) -> AlertRecord:
        async with self._lock:
            alert = AlertRecord(
                id=self._next_alert_id,
                gym_id=gym_id,
                device_type=device_type,
                device_id=device_id,
                level=level,
                code=code,
                message=message,
                priority=priority,
                triggered_at=triggered_at,
                payload=payload,
            )
            self._next_alert_id += 1
            self._alerts.insert(0, alert)
            return alert

    async def record_binding_event(
        self,
        *,
        gym_id: str,
        wristband_id: str,
        equipment_id: str,
        action: str,
        reason: str | None,
        ts: int | None,
    ) -> None:
        async with self._lock:
            duration_s = None
            event_time = _isoformat_from_ts(ts)

            if action == "unbind":
                for existing in self._bindings:
                    if (
                        existing.gym_id == gym_id
                        and existing.wristband_id == wristband_id
                        and existing.equipment_id == equipment_id
                        and existing.action == "bind"
                    ):
                        duration_s = int(
                            (
                                _parse_isoformat(event_time)
                                - _parse_isoformat(existing.ts)
                            ).total_seconds()
                        )
                        break

            event = BindingEventRecord(
                id=self._next_binding_id,
                wristband_id=wristband_id,
                equipment_id=equipment_id,
                gym_id=gym_id,
                action=action,
                reason=reason,
                ts=event_time,
                duration_s=duration_s,
            )
            self._next_binding_id += 1
            self._bindings.insert(0, event)

    async def record_telemetry(
        self,
        *,
        gym_id: str,
        device_type: str,
        device_id: str,
        payload: dict,
    ) -> None:
        async with self._lock:
            self._telemetry.insert(
                0,
                TelemetryRecord(
                    ts=_isoformat_from_ts(payload.get("ts")),
                    gym_id=gym_id,
                    device_type=device_type,
                    device_id=device_id,
                    payload=payload,
                ),
            )

    async def list_devices(
        self,
        device_type: str | None = None,
        status: str | None = None,
    ) -> list[DeviceSummary]:
        async with self._lock:
            devices = list(self._devices.values())

        if device_type is not None:
            devices = [item for item in devices if item.device_type == device_type]
        if status is not None:
            devices = [item for item in devices if item.status == status]

        return sorted(devices, key=lambda item: (item.device_type, item.device_id))

    async def get_device(self, *, device_id: str) -> DeviceSummary | None:
        async with self._lock:
            for device in self._devices.values():
                if device.device_id == device_id:
                    return device
        return None

    async def list_alerts(
        self,
        level: str | None = None,
        is_ack: bool | None = None,
    ) -> list[AlertRecord]:
        async with self._lock:
            alerts = list(self._alerts)

        if level is not None:
            alerts = [item for item in alerts if item.level == level]
        if is_ack is not None:
            alerts = [item for item in alerts if item.is_ack == is_ack]

        return alerts

    async def get_alert(self, *, alert_id: int) -> AlertRecord | None:
        async with self._lock:
            for alert in self._alerts:
                if alert.id == alert_id:
                    return alert
        return None

    async def ack_alert(self, *, alert_id: int) -> AlertRecord | None:
        async with self._lock:
            for index, alert in enumerate(self._alerts):
                if alert.id == alert_id:
                    updated = alert.model_copy(update={"is_ack": True})
                    self._alerts[index] = updated
                    return updated
        return None

    async def batch_ack_alerts(self, *, alert_ids: list[int]) -> list[AlertRecord]:
        updated: list[AlertRecord] = []
        async with self._lock:
            id_set = set(alert_ids)
            for index, alert in enumerate(self._alerts):
                if alert.id in id_set and not alert.is_ack:
                    patched = alert.model_copy(update={"is_ack": True})
                    self._alerts[index] = patched
                    updated.append(patched)
                elif alert.id in id_set:
                    updated.append(alert)
        return sorted(updated, key=lambda item: item.id)

    async def list_telemetry(
        self,
        *,
        device_type: str,
        device_id: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[TelemetryRecord]:
        async with self._lock:
            items = [
                item
                for item in self._telemetry
                if item.device_type == device_type and item.device_id == device_id
            ]

        if start is not None:
            start_ts = _parse_isoformat(start)
            items = [item for item in items if _parse_isoformat(item.ts) >= start_ts]
        if end is not None:
            end_ts = _parse_isoformat(end)
            items = [item for item in items if _parse_isoformat(item.ts) <= end_ts]

        return items[offset : offset + limit]

    async def list_binding_events(
        self,
        *,
        wristband_id: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[BindingEventRecord]:
        async with self._lock:
            items = [item for item in self._bindings if item.wristband_id == wristband_id]

        if start is not None:
            start_ts = _parse_isoformat(start)
            items = [item for item in items if _parse_isoformat(item.ts) >= start_ts]
        if end is not None:
            end_ts = _parse_isoformat(end)
            items = [item for item in items if _parse_isoformat(item.ts) <= end_ts]

        return items[offset : offset + limit]

    async def aggregate_env_telemetry(
        self,
        *,
        device_id: str,
        interval: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[EnvTelemetryAggregateRecord]:
        records = await self.list_telemetry(
            device_type="env",
            device_id=device_id,
            start=start,
            end=end,
            limit=100000,
            offset=0,
        )
        return aggregate_env_records(records, interval, limit=limit, offset=offset)

    async def upsert_gateway_health_report(
        self,
        *,
        report: GatewayHealthReportRequest,
    ) -> GatewayHealthDetail:
        async with self._lock:
            existing_keys = [
                key for key in self._gateway_health_components.keys() if key[0] == report.gateway_id
            ]
            incoming_keys = {
                (report.gateway_id, component.component_id) for component in report.components
            }
            for key in existing_keys:
                if key not in incoming_keys:
                    self._gateway_health_components.pop(key, None)

            for component in report.components:
                record = GatewayHealthComponentRecord(
                    gateway_id=report.gateway_id,
                    gym_id=report.gym_id,
                    reported_at=report.reported_at,
                    component_id=component.component_id,
                    component_type=component.component_type,
                    display_name=component.display_name,
                    online=component.online,
                    health_status=component.health_status,
                    checked_at=component.checked_at,
                    endpoint=component.endpoint,
                    latency_ms=component.latency_ms,
                    detail=component.detail,
                    extra=component.extra,
                )
                self._gateway_health_components[(report.gateway_id, component.component_id)] = record

            return self._build_gateway_health_detail(report.gateway_id)

    async def list_gateway_health_summaries(
        self,
        *,
        gym_id: str | None = None,
        gateway_id: str | None = None,
        component_type: str | None = None,
        overall_status: str | None = None,
    ) -> list[GatewayHealthSummary]:
        async with self._lock:
            gateway_ids = sorted({key[0] for key in self._gateway_health_components.keys()})

        summaries: list[GatewayHealthSummary] = []
        for current_gateway_id in gateway_ids:
            if gateway_id is not None and current_gateway_id != gateway_id:
                continue
            detail = await self.get_gateway_health_detail(gateway_id=current_gateway_id)
            if detail is None:
                continue
            if gym_id is not None and detail.gym_id != gym_id:
                continue
            if component_type is not None and not any(
                item.component_type == component_type for item in detail.components
            ):
                continue
            if overall_status is not None and detail.overall_status != overall_status:
                continue
            summaries.append(
                GatewayHealthSummary(
                    gateway_id=detail.gateway_id,
                    gym_id=detail.gym_id,
                    reported_at=detail.reported_at,
                    component_count=detail.component_count,
                    online_count=detail.online_count,
                    unhealthy_count=detail.unhealthy_count,
                    overall_status=detail.overall_status,
                )
            )

        return sorted(summaries, key=lambda item: item.gateway_id)

    async def get_gateway_health_detail(
        self,
        *,
        gateway_id: str,
    ) -> GatewayHealthDetail | None:
        async with self._lock:
            has_gateway = any(key[0] == gateway_id for key in self._gateway_health_components.keys())
        if not has_gateway:
            return None
        return self._build_gateway_health_detail(gateway_id)

    def _build_gateway_health_detail(self, gateway_id: str) -> GatewayHealthDetail:
        components = sorted(
            [
                item
                for (current_gateway_id, _), item in self._gateway_health_components.items()
                if current_gateway_id == gateway_id
            ],
            key=lambda item: (item.component_type, item.component_id),
        )
        latest_reported_at = max((item.reported_at for item in components), default=_isoformat_from_ts(None))
        online_count = sum(1 for item in components if item.online)
        unhealthy_count = sum(
            1 for item in components if (not item.online) or item.health_status != "healthy"
        )
        return GatewayHealthDetail(
            gateway_id=gateway_id,
            gym_id=components[0].gym_id if components else "",
            reported_at=latest_reported_at,
            component_count=len(components),
            online_count=online_count,
            unhealthy_count=unhealthy_count,
            overall_status=derive_overall_status(components),
            components=components,
        )


def coerce_online(status: str) -> bool:
    return status not in {"offline", "disconnected"}


def payload_ts(payload: dict) -> int | None:
    value = payload.get("ts")
    return value if isinstance(value, int) else None


def payload_triggered_at(payload: dict) -> str:
    if isinstance(payload.get("triggered_at"), str):
        return payload["triggered_at"]

    ts = payload_ts(payload)
    if ts is None:
        return datetime.now(UTC).isoformat()

    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def _device_key(gym_id: str, device_type: str, device_id: str) -> str:
    return f"{gym_id}:{device_type}:{device_id}"


def _isoformat_from_ts(value: int | None) -> str:
    if isinstance(value, int):
        return datetime.fromtimestamp(value, tz=UTC).isoformat()
    return datetime.now(UTC).isoformat()


def _parse_isoformat(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
