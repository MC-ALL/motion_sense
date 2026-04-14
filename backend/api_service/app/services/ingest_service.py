from __future__ import annotations

from app.models.ingest import IngestBatch
from app.services.topic_parser import parse_topic
from app.services.websocket_manager import WebSocketManager
from app.storage.memory_store import coerce_online, payload_triggered_at, payload_ts
from app.storage.store import Store


class IngestService:
    def __init__(self, store: Store, websocket_manager: WebSocketManager) -> None:
        self._store = store
        self._websocket_manager = websocket_manager

    async def ingest_batch(self, batch: IngestBatch) -> int:
        for item in batch.items:
            parsed = parse_topic(item.topic)

            if item.kind == "alert":
                alert = await self._store.add_alert(
                    gym_id=parsed.gym_id,
                    device_type=parsed.device_type,
                    device_id=parsed.device_id,
                    level=str(item.payload.get("level", "warning")),
                    code=str(item.payload.get("code", "UNKNOWN_ALERT")),
                    message=str(item.payload.get("message", "alert received")),
                    priority=item.payload.get("priority"),
                    triggered_at=payload_triggered_at(item.payload),
                    payload=item.payload,
                )
                await self._websocket_manager.broadcast({"type": "alert", "data": alert.model_dump()})
                continue

            if item.kind in {"telemetry", "status", "binding"}:
                if item.kind == "binding":
                    await self._store.record_binding_event(
                        gym_id=parsed.gym_id,
                        wristband_id=str(item.payload.get("wristband_id", parsed.device_id)),
                        equipment_id=str(item.payload.get("equipment_id", "")),
                        action=str(item.payload.get("action", "bind")),
                        reason=item.payload.get("reason"),
                        ts=payload_ts(item.payload),
                    )

                if item.kind == "telemetry":
                    await self._store.record_telemetry(
                        gym_id=parsed.gym_id,
                        device_type=parsed.device_type,
                        device_id=parsed.device_id,
                        payload=item.payload,
                    )

                status = str(item.payload.get("status", "online" if item.kind != "binding" else "bound"))
                device = await self._store.upsert_device(
                    gym_id=parsed.gym_id,
                    device_type=parsed.device_type,
                    device_id=parsed.device_id,
                    status=status,
                    online=coerce_online(status),
                    last_seen_ts=payload_ts(item.payload),
                    payload=item.payload,
                )

                if item.kind == "telemetry":
                    await self._websocket_manager.broadcast(
                        {
                            "type": "telemetry",
                            "data": {
                                "device_type": parsed.device_type,
                                "device_id": parsed.device_id,
                                **item.payload,
                            },
                        }
                    )
                elif item.kind == "status":
                    await self._websocket_manager.broadcast(
                        {
                            "type": "device_status",
                            "data": {
                                "device_id": device.device_id,
                                "online": device.online,
                                "ts": device.last_seen_ts,
                                "status": device.status,
                            },
                        }
                    )

        return len(batch.items)
