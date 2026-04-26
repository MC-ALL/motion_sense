import asyncio

import httpx

from app.services.health_reporter import GatewayHealthReporter
from app.settings import RuntimeSettings


def test_health_reporter_collects_component_statuses(monkeypatch) -> None:
    """Verify the reporter aggregates local and dependency health statuses.

    :param monkeypatch: Pytest fixture used to replace the MQTT socket check.
    :return: None. Assertions validate component count and health states.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        """Return mocked health responses for backend and InfluxDB checks.

        :param request: Outbound HTTP request issued by the health reporter.
        :return: HTTP response for the dependency endpoint under test.
        :raises AssertionError: If an unexpected endpoint is called.
        """
        if request.url.path == "/healthz":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/api/v3/query_sql":
            return httpx.Response(200, text='{"ready":1}')
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    class FakeWriter:
        """Minimal stream writer fake returned by ``open_connection``."""

        def close(self) -> None:
            """Accept close calls from the reporter.

            :return: None.
            """
            return None

        async def wait_closed(self) -> None:
            """Complete immediately after fake close.

            :return: None.
            """
            return None

    async def fake_open_connection(host: str, port: int):  # type: ignore[override]
        """Validate the MQTT host and return a fake TCP connection.

        :param host: Hostname passed to ``asyncio.open_connection``.
        :param port: Port passed to ``asyncio.open_connection``.
        :return: Reader placeholder and fake writer.
        """
        assert host == "mosquitto"
        assert port == 1883
        return object(), FakeWriter()

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)

    settings = RuntimeSettings(gateway_id="gw-test-001", gym_id="gym-gz-01")
    reporter = GatewayHealthReporter(settings)
    original_client = reporter._client
    reporter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5.0)

    async def scenario() -> None:
        """Collect one report with mocked dependencies.

        :return: None. Assertions validate report identity and component
            statuses.
        """
        await original_client.aclose()
        report = await reporter.collect_report()
        assert report.gateway_id == "gw-test-001"
        assert report.gym_id == "gym-gz-01"
        assert len(report.components) == 5
        components = {item.component_id: item for item in report.components}
        assert components["gateway_api"].health_status == "healthy"
        assert components["mqtt_broker"].health_status == "healthy"
        assert components["local_timeseries_db"].health_status == "healthy"
        assert components["backend_api"].health_status == "healthy"
        await reporter.close()

    asyncio.run(scenario())
