from __future__ import annotations

from app.models.ingest import IngestBatch
from app.services.event_store import EventStore, coerce_online, payload_triggered_at, payload_ts
from app.services.topic_parser import parse_topic
from app.services.websocket_manager import WebSocketManager


class IngestService:
    def __init__(self, store: EventStore, websocket_manager: WebSocketManager) -> None:
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
