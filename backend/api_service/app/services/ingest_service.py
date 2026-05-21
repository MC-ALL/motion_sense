from __future__ import annotations

from app.models.ingest import IngestBatch
from app.services.ops_service import BackendOpsService
from app.services.realtime_service import RealtimeService
from app.services.workout_aggregation_service import WorkoutAggregationService
from app.services.topic_parser import parse_topic
from app.storage.memory_store import coerce_online, payload_triggered_at, payload_ts
from app.storage.store import Store


class IngestService:
    def __init__(
        self,
        store: Store,
        realtime_service: RealtimeService,
        ops_service: BackendOpsService | None = None,
        workout_aggregation_service: WorkoutAggregationService | None = None,
    ) -> None:
        self._store = store
        self._realtime_service = realtime_service
        self._ops_service = ops_service
        self._workout_aggregation_service = workout_aggregation_service

    async def ingest_batch(self, batch: IngestBatch) -> int:
        if self._ops_service is not None:
            self._ops_service.record_ingest_batch(len(batch.items))

        for item in batch.items:
            parsed = parse_topic(item.topic)

            if item.kind == "alert":
                alert = await self._store.add_alert(
                    gym_id=parsed.gym_id,
                    device_type=parsed.device_type,
                    device_id=parsed.device_id,
                    level=str(item.payload.get("level", "warning")),
                    code=_alert_code(item.payload),
                    message=str(item.payload.get("message", "alert received")),
                    priority=item.payload.get("priority"),
                    triggered_at=payload_triggered_at(item.payload),
                    payload=item.payload,
                )
                await self._realtime_service.publish({"type": "alert", "data": alert.model_dump()})
                if self._ops_service is not None:
                    self._ops_service.record_realtime_message("alert")
                continue

            if item.kind in {"telemetry", "status", "binding"}:
                normalized_payload = _normalize_payload(parsed.device_type, item.payload)
                binding_action = None
                binding_wristband_id = None
                binding_equipment_id = None
                if item.kind == "binding":
                    binding_action = _binding_action(normalized_payload)
                    binding_wristband_id = str(normalized_payload.get("wristband_id", parsed.device_id))
                    binding_equipment_id = str(normalized_payload.get("equipment_id", ""))
                    inserted = await self._store.record_binding_event(
                        gym_id=parsed.gym_id,
                        wristband_id=binding_wristband_id,
                        equipment_id=binding_equipment_id,
                        action=binding_action,
                        reason=normalized_payload.get("reason"),
                        ts=payload_ts(normalized_payload),
                    )
                    binding_payload = {
                        **normalized_payload,
                        "action": binding_action,
                        "wristband_id": binding_wristband_id,
                        "current_equipment_id": (
                            binding_equipment_id if binding_action == "bind" and binding_equipment_id else None
                        ),
                        "gateway_id": batch.gateway_id,
                    }
                    device = await self._store.update_wristband_equipment_binding(
                        gym_id=parsed.gym_id,
                        wristband_id=binding_wristband_id,
                        equipment_id=binding_payload["current_equipment_id"],
                        payload=binding_payload,
                    )
                    if inserted and self._workout_aggregation_service is not None and binding_action == "unbind":
                        await self._workout_aggregation_service.aggregate_recent_wristband_activity(
                            wristband_id=binding_wristband_id,
                            gym_id=parsed.gym_id,
                            end=payload_triggered_at(normalized_payload),
                        )
                    if not inserted:
                        continue
                else:
                    if item.kind == "telemetry":
                        await self._store.record_telemetry(
                            gym_id=parsed.gym_id,
                            device_type=parsed.device_type,
                            device_id=parsed.device_id,
                            payload=normalized_payload,
                        )

                    device_payload = {
                        **normalized_payload,
                        "gateway_id": batch.gateway_id,
                    }
                    status = _derive_device_status(item.kind, normalized_payload)
                    device = await self._store.upsert_device(
                        gym_id=parsed.gym_id,
                        device_type=parsed.device_type,
                        device_id=parsed.device_id,
                        status=status,
                        online=coerce_online(status),
                        last_seen_ts=payload_ts(normalized_payload),
                        payload=device_payload,
                    )

                if item.kind == "telemetry":
                    await self._realtime_service.publish(
                        {
                            "type": "telemetry",
                            "data": {
                                "gym_id": parsed.gym_id,
                                "device_type": parsed.device_type,
                                "device_id": parsed.device_id,
                                **normalized_payload,
                            },
                        }
                    )
                    if self._ops_service is not None:
                        self._ops_service.record_realtime_message("telemetry")
                elif item.kind == "status":
                    await self._realtime_service.publish(
                        {
                            "type": "device_status",
                            "data": {
                                "gym_id": device.gym_id,
                                "device_type": device.device_type,
                                "device_id": device.device_id,
                                "online": device.online,
                                "ts": device.last_seen_ts,
                                "status": device.status,
                            },
                        }
                    )
                    if self._ops_service is not None:
                        self._ops_service.record_realtime_message("device_status")
                elif item.kind == "binding":
                    message_type = "binding_upsert" if binding_action == "bind" else "binding_remove"
                    await self._realtime_service.publish(
                        {
                            "type": message_type,
                            "data": {
                                "gym_id": device.gym_id,
                                "device_type": "wristband",
                                "device_id": binding_wristband_id,
                                "wristband_id": binding_wristband_id,
                                "equipment_id": binding_equipment_id or None,
                                "ts": payload_ts(normalized_payload),
                                "status": device.status,
                                "reason": normalized_payload.get("reason"),
                            },
                        }
                    )
                    if self._ops_service is not None:
                        self._ops_service.record_realtime_message(message_type)

        return len(batch.items)


def _derive_device_status(kind: str, payload: dict) -> str:
    raw_status = payload.get("status")
    if isinstance(raw_status, str) and raw_status:
        return raw_status

    return "online"


def _normalize_payload(device_type: str, payload: dict) -> dict:
    """Normalize backend display fields without losing raw device values."""
    if device_type != "wristband":
        return payload

    relayed_by = payload.get("relayed_by")
    current_equipment_id = payload.get("current_equipment_id")
    if not _is_unstable_equipment_id(current_equipment_id) or not _is_valid_equipment_id(relayed_by):
        return payload

    return {
        **payload,
        "raw_current_equipment_id": current_equipment_id,
        "current_equipment_id": relayed_by,
    }


def _is_unstable_equipment_id(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, int):
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return stripped == "" or stripped == "255" or stripped.isdigit() or stripped.lower() == "none"
    return False


def _is_valid_equipment_id(value: object) -> bool:
    return isinstance(value, str) and value.startswith("eq-") and len(value) > 3


def _alert_code(payload: dict) -> str:
    """Return the persisted alert code from schema rc1 or legacy payloads."""
    raw = payload.get("alert_type")
    if isinstance(raw, str) and raw:
        return raw
    raw = payload.get("code")
    if isinstance(raw, str) and raw:
        return raw
    return "UNKNOWN_ALERT"


def _binding_action(payload: dict) -> str:
    """Return ``bind`` or ``unbind`` from schema rc1 or legacy payloads."""
    raw_action = payload.get("action")
    if isinstance(raw_action, str) and raw_action.lower() in {"bind", "unbind"}:
        return raw_action.lower()
    raw_bound = payload.get("bound")
    if isinstance(raw_bound, bool):
        return "bind" if raw_bound else "unbind"
    return "bind"
