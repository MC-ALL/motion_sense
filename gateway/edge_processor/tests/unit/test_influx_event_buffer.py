import asyncio
import json

import httpx

from app.models.ingest_item import IngestItem
from app.services.influx_event_buffer import InfluxEventBuffer
from app.settings import RuntimeSettings
from app.utils.topic_parser import parse_topic


def test_influx_event_buffer_uses_write_and_query_endpoints() -> None:
    """Verify Influx buffer writes, queries, and delivery acknowledgements.

    :return: None. Assertions validate endpoint usage, line protocol content,
        pending-event parsing, and ack write format.
    """
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Mock InfluxDB query and line protocol endpoints.

        :param request: Outbound HTTP request issued by ``InfluxEventBuffer``.
        :return: HTTP response representing readiness, pending rows, or writes.
        :raises AssertionError: If an unexpected endpoint is called.
        """
        requests.append(request)

        if request.url.path == "/api/v3/query_sql":
            query_payload = json.loads(request.content.decode("utf-8"))
            if query_payload["q"] == "SELECT 1 AS ready":
                return httpx.Response(200, text=json.dumps({"ready": 1}))
            if "FROM edge_delivery_log" in query_payload["q"]:
                return httpx.Response(200, text="")
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
        """Run append, pending query, and ack operations.

        :return: None. Assertions validate the pending event parsed from the
            mocked query response.
        """
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
    assert any("FROM edge_ingest_events" in payload["q"] for payload in query_payloads)
    assert any("FROM edge_delivery_log" in payload["q"] for payload in query_payloads)

    ack_body = write_requests[1].content.decode("utf-8")
    assert ack_body.startswith("edge_delivery_log,")
    assert "delivered=true" in ack_body


def test_influx_event_buffer_treats_missing_tables_as_empty_pending() -> None:
    """Verify a missing ingest table is treated as no pending data.

    :return: None. Assertions confirm table-not-found responses do not fail
        replay scans.
    """
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Mock readiness and missing-table query responses.

        :param request: Outbound HTTP request issued by ``InfluxEventBuffer``.
        :return: Successful readiness response or missing-table error.
        :raises AssertionError: If an unexpected endpoint is called.
        """
        requests.append(request)

        if request.url.path == "/api/v3/query_sql":
            query_payload = json.loads(request.content.decode("utf-8"))
            if query_payload["q"] == "SELECT 1 AS ready":
                return httpx.Response(200, text=json.dumps({"ready": 1}))
            return httpx.Response(400, text="Error during planning: table 'public.iox.edge_ingest_events' not found")

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
        """Initialize the buffer and query pending rows.

        :return: None. Assertion validates that missing tables yield an empty
            pending list.
        """
        await original_client.aclose()
        await buffer.initialize()
        pending = await buffer.list_pending(10)
        await buffer.close()
        assert pending == []

    asyncio.run(scenario())


def test_influx_event_buffer_wait_for_pending_is_notified_by_append() -> None:
    """Verify appending an event wakes pending-data waiters.

    :return: None. Assertions confirm ``wait_for_pending`` observes the append
        notification.
    """
    settings = RuntimeSettings(influxdb={"base_url": "http://influxdb.test:8181"})
    buffer = InfluxEventBuffer(settings)

    async def scenario() -> None:
        """Start a waiter, append an event, and assert notification delivery.

        :return: None.
        """
        waiter = asyncio.create_task(buffer.wait_for_pending(1.0))
        await asyncio.sleep(0)
        await buffer.append(
            IngestItem(
                kind="telemetry",
                topic="gym/gym-gz-01/equipment/eq-003/telemetry",
                payload={"ts": 1712345678, "power_w": 301.1},
            ),
            parse_topic("gym/gym-gz-01/equipment/eq-003/telemetry"),
        )
        assert await waiter is True
        await buffer._client.aclose()

    asyncio.run(scenario())


def test_influx_event_buffer_treats_missing_delivery_log_as_empty_ack_set() -> None:
    """Verify a missing delivery log does not hide pending ingest rows.

    :return: None. Assertions confirm replay candidates are returned when only
        the ack table is absent.
    """
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Mock pending-row query with a missing delivery-log table.

        :param request: Outbound HTTP request issued by ``InfluxEventBuffer``.
        :return: HTTP response for readiness, delivery-log lookup, or pending
            events.
        :raises AssertionError: If an unexpected endpoint is called.
        """
        requests.append(request)

        if request.url.path == "/api/v3/query_sql":
            query_payload = json.loads(request.content.decode("utf-8"))
            if query_payload["q"] == "SELECT 1 AS ready":
                return httpx.Response(200, text=json.dumps({"ready": 1}))
            if "FROM edge_delivery_log" in query_payload["q"]:
                return httpx.Response(400, text="Error during planning: table 'public.iox.edge_delivery_log' not found")
            body = json.dumps(
                {
                    "event_id": "evt-002",
                    "kind": "telemetry",
                    "topic": "gym/gym-gz-01/equipment/eq-002/telemetry",
                    "payload_json": json.dumps(
                        {"ts": 1712345678, "power_w": 318.2},
                        separators=(",", ":"),
                    ),
                    "first_seen": "2026-04-14T18:00:00Z",
                }
            )
            return httpx.Response(200, text=body)

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
        """Query pending rows while the delivery log is absent.

        :return: None. Assertions validate that the ingest row remains pending.
        """
        await original_client.aclose()
        await buffer.initialize()
        pending = await buffer.list_pending(10)
        await buffer.close()
        assert len(pending) == 1
        assert pending[0].event_id == "evt-002"

    asyncio.run(scenario())


def test_influx_event_buffer_batches_pending_writes_before_query() -> None:
    """Verify queued appends are batched before a pending query executes.

    :return: None. Assertions confirm a single line protocol write contains
        all queued events.
    """
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Mock InfluxDB responses for batched-write verification.

        :param request: Outbound HTTP request issued by ``InfluxEventBuffer``.
        :return: HTTP response for readiness, delivery-log lookup, pending
            query, or write.
        :raises AssertionError: If an unexpected endpoint is called.
        """
        requests.append(request)

        if request.url.path == "/api/v3/query_sql":
            query_payload = json.loads(request.content.decode("utf-8"))
            if query_payload["q"] == "SELECT 1 AS ready":
                return httpx.Response(200, text=json.dumps({"ready": 1}))
            if "FROM edge_delivery_log" in query_payload["q"]:
                return httpx.Response(200, text="")
            return httpx.Response(200, text="")

        if request.url.path == "/api/v3/write_lp":
            return httpx.Response(204)

        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    settings = RuntimeSettings(
        influxdb={
            "base_url": "http://influxdb.test:8181",
            "write_batch_size": 8,
            "write_queue_size": 32,
        }
    )
    buffer = InfluxEventBuffer(settings)
    original_client = buffer._client
    buffer._client = httpx.AsyncClient(
        base_url=settings.influxdb.base_url,
        transport=transport,
        headers={},
    )

    async def scenario() -> None:
        """Append multiple events and force the write queue to flush.

        :return: None.
        """
        await original_client.aclose()
        await buffer.initialize()
        for index in range(3):
            await buffer.append(
                IngestItem(
                    kind="telemetry",
                    topic=f"gym/gym-gz-01/equipment/eq-00{index + 1}/telemetry",
                    payload={"ts": 1712345678 + index, "power_w": 300 + index},
                ),
                parse_topic(f"gym/gym-gz-01/equipment/eq-00{index + 1}/telemetry"),
            )
        await buffer.list_pending(10)
        await buffer.close()

    asyncio.run(scenario())

    write_requests = [request for request in requests if request.url.path == "/api/v3/write_lp"]
    assert len(write_requests) == 1
    write_body = write_requests[0].content.decode("utf-8")
    assert write_body.count("edge_ingest_events") == 3
    assert write_body.count("\ntelemetry,") == 3


def test_influx_event_buffer_prefers_recent_pending_rows_and_restores_order() -> None:
    """Verify pending queries fetch recent rows then restore chronological order.

    :return: None. Assertions confirm delivered rows are skipped and remaining
        rows are ordered oldest-first for replay.
    """
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Mock pending and delivered row query responses.

        :param request: Outbound HTTP request issued by ``InfluxEventBuffer``.
        :return: HTTP response for readiness, delivered IDs, or candidate
            pending rows.
        :raises AssertionError: If an unexpected endpoint is called.
        """
        requests.append(request)

        if request.url.path == "/api/v3/query_sql":
            query_payload = json.loads(request.content.decode("utf-8"))
            if query_payload["q"] == "SELECT 1 AS ready":
                return httpx.Response(200, text=json.dumps({"ready": 1}))
            if "FROM edge_delivery_log" in query_payload["q"]:
                return httpx.Response(200, text=json.dumps({"event_id": "evt-delivered"}))
            body = "\n".join(
                [
                    json.dumps(
                        {
                            "event_id": "evt-new-2",
                            "kind": "telemetry",
                            "topic": "gym/gym-gz-01/equipment/eq-002/telemetry",
                            "payload_json": json.dumps({"ts": 1712345682, "power_w": 322.0}, separators=(",", ":")),
                            "first_seen": "2026-04-16T18:00:02Z",
                        }
                    ),
                    json.dumps(
                        {
                            "event_id": "evt-delivered",
                            "kind": "telemetry",
                            "topic": "gym/gym-gz-01/equipment/eq-001/telemetry",
                            "payload_json": json.dumps({"ts": 1712345681, "power_w": 321.0}, separators=(",", ":")),
                            "first_seen": "2026-04-16T18:00:01Z",
                        }
                    ),
                    json.dumps(
                        {
                            "event_id": "evt-new-1",
                            "kind": "telemetry",
                            "topic": "gym/gym-gz-01/equipment/eq-003/telemetry",
                            "payload_json": json.dumps({"ts": 1712345680, "power_w": 320.0}, separators=(",", ":")),
                            "first_seen": "2026-04-16T18:00:00Z",
                        }
                    ),
                ]
            )
            return httpx.Response(200, text=body)

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
        """Collect pending events from mocked out-of-order query rows.

        :return: None. Assertions validate the final replay order.
        """
        await original_client.aclose()
        await buffer.initialize()
        pending = await buffer.list_pending(2)
        await buffer.close()
        assert [item.event_id for item in pending] == ["evt-new-1", "evt-new-2"]

    asyncio.run(scenario())

    pending_query = next(
        json.loads(request.content.decode("utf-8"))["q"]
        for request in requests
        if request.url.path == "/api/v3/query_sql" and "FROM edge_ingest_events" in request.content.decode("utf-8")
    )
    assert "ORDER BY first_seen DESC" in pending_query
