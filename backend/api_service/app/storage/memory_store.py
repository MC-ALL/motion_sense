from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.models.ingest import AlertRecord, DeviceSummary


class EventStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._devices: dict[str, DeviceSummary] = {}
        self._alerts: list[AlertRecord] = []
        self._next_alert_id = 1

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
        return None

    async def record_telemetry(
        self,
        *,
        gym_id: str,
        device_type: str,
        device_id: str,
        payload: dict,
    ) -> None:
        return None

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
