from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
import asyncio

import httpx

from app.models.ingest_item import IngestItem
from app.settings import RuntimeSettings
from app.utils.topic_parser import ParsedTopic


@dataclass(slots=True)
class BufferedEvent:
    event_id: str
    item: IngestItem


@dataclass(slots=True)
class PendingInfluxWrite:
    event_id: str
    body: str


class InfluxEventBuffer:
    def __init__(self, settings: RuntimeSettings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.influxdb.base_url,
            timeout=settings.influxdb.request_timeout_s,
            headers=_build_headers(settings),
        )
        self._pending_writes: asyncio.Queue[PendingInfluxWrite] = asyncio.Queue(
            maxsize=settings.influxdb.write_queue_size
        )
        self._flush_lock = asyncio.Lock()
        self._pending_notifications: asyncio.Queue[None] = asyncio.Queue(maxsize=1)

    async def initialize(self) -> None:
        response = await self._client.post(
            "/api/v3/query_sql",
            json={
                "db": self._settings.influxdb.database_name,
                "q": "SELECT 1 AS ready",
                "format": "jsonl",
            },
        )
        response.raise_for_status()

    async def close(self) -> None:
        await self._flush_pending()
        await self._client.aclose()

    async def append(self, item: IngestItem, parsed_topic: ParsedTopic) -> str:
        payload_json = _canonical_payload(item.payload)
        event_id = _event_id(item.kind, item.topic, payload_json)
        received_at = datetime.now(UTC)
        received_at_ms = _to_millis(received_at)
        payload_ts_s = _payload_ts_seconds(item)

        body = "\n".join(
            [
                _build_queue_line(
                    gateway_id=self._settings.gateway_id,
                    event_id=event_id,
                    item=item,
                    parsed_topic=parsed_topic,
                    payload_json=payload_json,
                    payload_ts_s=payload_ts_s,
                    received_at_ms=received_at_ms,
                ),
                _build_kind_line(
                    gateway_id=self._settings.gateway_id,
                    event_id=event_id,
                    item=item,
                    parsed_topic=parsed_topic,
                    payload_json=payload_json,
                    payload_ts_s=payload_ts_s,
                    received_at_ms=received_at_ms,
                ),
            ]
        )
        await self._pending_writes.put(PendingInfluxWrite(event_id=event_id, body=body))
        try:
            self._pending_notifications.put_nowait(None)
        except asyncio.QueueFull:
            pass
        return event_id

    async def list_pending(self, limit: int) -> list[BufferedEvent]:
        await self._flush_pending()
        response = await self._query_sql(_pending_events_query(limit * 8))
        if response.status_code >= 500 or _is_missing_table_response(response):
            return []
        response.raise_for_status()

        delivered_response = await self._query_sql(_delivered_events_query(limit * 8))
        if delivered_response.status_code >= 500 or _is_missing_table_response(delivered_response):
            delivered_event_ids: set[str] = set()
        else:
            delivered_response.raise_for_status()
            delivered_event_ids = {
                str(row["event_id"])
                for row in _parse_jsonl_rows(delivered_response.text)
                if row.get("event_id")
            }

        events: list[BufferedEvent] = []
        for row in _parse_jsonl_rows(response.text):
            payload_json = row.get("payload_json")
            if not isinstance(payload_json, str):
                continue
            event_id = str(row["event_id"])
            if event_id in delivered_event_ids:
                continue
            events.append(
                BufferedEvent(
                    event_id=event_id,
                    item=IngestItem(
                        kind=str(row["kind"]),
                        topic=str(row["topic"]),
                        payload=json.loads(payload_json),
                    ),
                )
            )
            if len(events) >= limit:
                break
        events.reverse()
        return events

    async def ack_delivered(self, event_ids: list[str]) -> None:
        if not event_ids:
            return

        delivered_at_ms = _to_millis(datetime.now(UTC))
        lines = [
            (
                f"edge_delivery_log,gateway_id={_escape_tag_value(self._settings.gateway_id)},"
                f"event_id={_escape_tag_value(event_id)} "
                f"delivered=true,delivered_at_ms={delivered_at_ms}i {delivered_at_ms}"
            )
            for event_id in event_ids
        ]
        await self._write_lines("\n".join(lines))

    async def _flush_pending(self) -> None:
        async with self._flush_lock:
            batch: list[PendingInfluxWrite] = []
            max_batch_size = max(1, self._settings.influxdb.write_batch_size)

            while not self._pending_writes.empty():
                batch.append(self._pending_writes.get_nowait())
                if len(batch) < max_batch_size:
                    continue
                await self._write_lines("\n".join(item.body for item in batch))
                batch.clear()

            if batch:
                await self._write_lines("\n".join(item.body for item in batch))

    async def wait_for_pending(self, timeout_s: float) -> bool:
        if not self._pending_writes.empty():
            return True
        try:
            await asyncio.wait_for(self._pending_notifications.get(), timeout=timeout_s)
            return True
        except TimeoutError:
            return False

    async def _query_sql(self, query: str) -> httpx.Response:
        return await self._client.post(
            "/api/v3/query_sql",
            json={
                "db": self._settings.influxdb.database_name,
                "q": query,
                "format": "jsonl",
            },
        )

    async def _write_lines(self, body: str) -> None:
        response = await self._client.post(
            "/api/v3/write_lp",
            params={
                "db": self._settings.influxdb.database_name,
                "precision": "ms",
            },
            content=body.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )
        response.raise_for_status()


def _pending_events_query(limit: int) -> str:
    return f"""
SELECT
  event_id,
  kind,
  topic,
  payload_json,
  time AS first_seen
FROM edge_ingest_events
ORDER BY first_seen DESC
LIMIT {int(limit)}
""".strip()


def _delivered_events_query(limit: int) -> str:
    return f"""
SELECT
  event_id
FROM edge_delivery_log
ORDER BY time DESC
LIMIT {int(limit)}
""".strip()


def _parse_jsonl_rows(payload: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in payload.splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def _is_missing_table_response(response: httpx.Response) -> bool:
    if response.status_code != 400:
        return False
    body = response.text.lower()
    return "not found" in body and "table" in body


def _build_headers(settings: RuntimeSettings) -> dict[str, str]:
    if settings.influxdb.auth_token:
        return {"Authorization": f"Bearer {settings.influxdb.auth_token}"}
    return {}


def _canonical_payload(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _event_id(kind: str, topic: str, payload_json: str) -> str:
    digest = hashlib.sha1(f"{kind}\n{topic}\n{payload_json}".encode("utf-8")).hexdigest()
    return digest


def _payload_ts_seconds(item: IngestItem) -> int:
    raw = item.payload.get("ts")
    if isinstance(raw, bool):
        return _to_millis(datetime.now(UTC)) // 1000
    if isinstance(raw, (int, float)):
        return int(raw)
    return _to_millis(datetime.now(UTC)) // 1000


def _to_millis(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _build_queue_line(
    *,
    gateway_id: str,
    event_id: str,
    item: IngestItem,
    parsed_topic: ParsedTopic,
    payload_json: str,
    payload_ts_s: int,
    received_at_ms: int,
) -> str:
    tags = {
        "gateway_id": gateway_id,
        "gym_id": parsed_topic.gym_id,
        "device_type": parsed_topic.device_type,
        "device_id": parsed_topic.device_id,
        "kind": item.kind,
        "event_id": event_id,
    }
    fields = {
        "topic": item.topic,
        "payload_json": payload_json,
        "payload_ts_s": payload_ts_s,
        "received_at_ms": received_at_ms,
    }
    return _build_line("edge_ingest_events", tags, fields, received_at_ms)


def _build_kind_line(
    *,
    gateway_id: str,
    event_id: str,
    item: IngestItem,
    parsed_topic: ParsedTopic,
    payload_json: str,
    payload_ts_s: int,
    received_at_ms: int,
) -> str:
    tags = {
        "gateway_id": gateway_id,
        "gym_id": parsed_topic.gym_id,
        "device_type": parsed_topic.device_type,
        "device_id": parsed_topic.device_id,
        "event_id": event_id,
    }
    fields = {
        "topic": item.topic,
        "payload_json": payload_json,
        "payload_ts_s": payload_ts_s,
    }
    return _build_line(item.kind, tags, fields, received_at_ms)


def _build_line(
    measurement: str,
    tags: dict[str, str],
    fields: dict[str, str | int | float | bool],
    timestamp_ms: int,
) -> str:
    tags_part = ",".join(
        f"{_escape_tag_key(key)}={_escape_tag_value(value)}" for key, value in tags.items() if value
    )
    fields_part = ",".join(
        f"{_escape_field_key(key)}={_format_field_value(value)}" for key, value in fields.items()
    )
    return f"{_escape_measurement(measurement)},{tags_part} {fields_part} {timestamp_ms}"


def _escape_measurement(value: str) -> str:
    return value.replace("\\", "\\\\").replace(",", "\\,").replace(" ", "\\ ")


def _escape_tag_key(value: str) -> str:
    return _escape_tag_value(value)


def _escape_tag_value(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(" ", "\\ ")
        .replace("=", "\\=")
    )


def _escape_field_key(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(" ", "\\ ")
        .replace("=", "\\=")
    )


def _format_field_value(value: str | int | float | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return f"{value}i"
    if isinstance(value, float):
        return f"{value}"
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
