import asyncio
import json

import httpx

from app.models.ingest_item import IngestItem
from app.services.influx_event_buffer import InfluxEventBuffer
from app.settings import RuntimeSettings
from app.utils.topic_parser import parse_topic


def test_influx_event_buffer_uses_write_and_query_endpoints() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)

        if request.url.path == "/api/v3/query_sql":
            query_payload = json.loads(request.content.decode("utf-8"))
            if query_payload["q"] == "SELECT 1 AS ready":
                return httpx.Response(200, text=json.dumps({"ready": 1}))
            body = json.dumps(
                {
                    "event_id": "evt-001",
                    "kind": "telemetry",
                    "topic": "gym/gym-gz-01/equipment/eq-001/telemetry",
                    "payload_json": json.dumps(
                        {"ts": 1712345678, "power_w": 320.5},
                        separators=(",", ":"),
                    ),
                    "first_seen": "2026-04-14T18:00:00Z",
                }
            )
            return httpx.Response(200, text=body)

        if request.url.path == "/api/v3/write_lp":
            return httpx.Response(204)

        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    settings = RuntimeSettings(influxdb={"base_url": "http://influxdb.test:8181"})
    buffer = InfluxEventBuffer(settings)
    original_client = buffer._client
    buffer._client = httpx.AsyncClient(
        base_url=settings.influxdb.base_url,
        transport=transport,
        headers={},
    )

    async def scenario() -> None:
        await original_client.aclose()
        await buffer.initialize()
        event_id = await buffer.append(
            IngestItem(
                kind="telemetry",
                topic="gym/gym-gz-01/equipment/eq-001/telemetry",
                payload={"ts": 1712345678, "power_w": 320.5},
            ),
            parse_topic("gym/gym-gz-01/equipment/eq-001/telemetry"),
        )
        pending = await buffer.list_pending(10)
        await buffer.ack_delivered([event_id])
        await buffer.close()

        assert pending[0].event_id == "evt-001"
        assert pending[0].item.kind == "telemetry"
        assert pending[0].item.payload["power_w"] == 320.5

    asyncio.run(scenario())

    write_requests = [request for request in requests if request.url.path == "/api/v3/write_lp"]
    assert len(write_requests) == 2

    append_body = write_requests[0].content.decode("utf-8")
    assert "edge_ingest_events" in append_body
    assert ",event_id=" in append_body
    assert "\ntelemetry," in append_body

    query_payloads = [
        json.loads(request.content.decode("utf-8"))
        for request in requests
        if request.url.path == "/api/v3/query_sql"
    ]
    assert all(payload["db"] == "gym_local" for payload in query_payloads)
    assert any("edge_delivery_log" in payload["q"] for payload in query_payloads)

    ack_body = write_requests[1].content.decode("utf-8")
    assert ack_body.startswith("edge_delivery_log,")
    assert "delivered=true" in ack_body
