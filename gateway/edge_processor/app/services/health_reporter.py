from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime

import httpx

from app.models.system_health import GatewayHealthComponentInput, GatewayHealthReportRequest
from app.settings import RuntimeSettings


class GatewayHealthReporter:
    """Collect local dependency health for ops_observer."""

    def __init__(self, settings: RuntimeSettings) -> None:
        """Create a health reporter.

        :param settings: Runtime settings for local and upstream health probes.
        """
        self._settings = settings
        self._client = httpx.AsyncClient(timeout=settings.backend.request_timeout_s)

    async def close(self) -> None:
        """Close the shared HTTP client used by health probes."""
        await self._client.aclose()

    async def collect_report(self) -> GatewayHealthReportRequest:
        """Collect a complete gateway health report.

        :return: Component-level health report for this gateway and gym.
        """
        reported_at = datetime.now(UTC).isoformat()
        return GatewayHealthReportRequest(
            gateway_id=self._settings.gateway_id,
            gym_id=self._settings.gym_id,
            reported_at=reported_at,
            components=[
                await self._check_gateway_api(reported_at),
                self._edge_processor_component(reported_at),
                await self._check_mqtt_broker(reported_at),
                await self._check_influxdb(reported_at),
                await self._check_backend_api(reported_at),
            ],
        )

    async def _check_gateway_api(self, checked_at: str) -> GatewayHealthComponentInput:
        """Check the edge processor's own HTTP health endpoint."""
        endpoint = f"http://127.0.0.1:{self._settings.port}/healthz"
        return await self._check_http_component(
            component_id="gateway_api",
            component_type="gateway_api",
            display_name="网关 API",
            endpoint=endpoint,
            checked_at=checked_at,
        )

    def _edge_processor_component(self, checked_at: str) -> GatewayHealthComponentInput:
        """Return the process-alive component record."""
        return GatewayHealthComponentInput(
            component_id="edge_processor",
            component_type="edge_processor",
            display_name="边缘处理服务",
            online=True,
            health_status="healthy",
            checked_at=checked_at,
            detail="process alive",
        )

    async def _check_mqtt_broker(self, checked_at: str) -> GatewayHealthComponentInput:
        """Check whether the local MQTT broker accepts TCP connections."""
        start = time.monotonic()
        detail = None
        online = False
        health_status = "offline"
        try:
            reader, writer = await asyncio.open_connection(
                host=self._settings.mqtt.host,
                port=self._settings.mqtt.port,
            )
            del reader
            writer.close()
            await writer.wait_closed()
            online = True
            health_status = "healthy"
            detail = "tcp connect ok"
        except Exception as exc:
            detail = str(exc)

        return GatewayHealthComponentInput(
            component_id="mqtt_broker",
            component_type="mqtt_broker",
            display_name="Mosquitto",
            online=online,
            health_status=health_status,
            checked_at=checked_at,
            endpoint=f"tcp://{self._settings.mqtt.host}:{self._settings.mqtt.port}",
            latency_ms=_latency_ms(start),
            detail=detail,
        )

    async def _check_influxdb(self, checked_at: str) -> GatewayHealthComponentInput:
        """Check whether InfluxDB accepts a minimal SQL query."""
        endpoint = f"{self._settings.influxdb.base_url}/api/v3/query_sql"
        start = time.monotonic()
        detail = None
        online = False
        health_status = "offline"
        headers = {"Content-Type": "application/json"}
        if self._settings.influxdb.auth_token:
            headers["Authorization"] = f"Bearer {self._settings.influxdb.auth_token}"

        try:
            response = await self._client.post(
                endpoint,
                headers=headers,
                json={
                    "db": self._settings.influxdb.database_name,
                    "q": "SELECT 1 AS ready",
                },
            )
            response.raise_for_status()
            body = response.text.strip()
            if body and "ready" in body:
                online = True
                health_status = "healthy"
                detail = "query ok"
            else:
                online = True
                health_status = "degraded"
                detail = "query returned unexpected payload"
        except Exception as exc:
            detail = str(exc)

        return GatewayHealthComponentInput(
            component_id="local_timeseries_db",
            component_type="local_timeseries_db",
            display_name="InfluxDB 3 Core",
            online=online,
            health_status=health_status,
            checked_at=checked_at,
            endpoint=endpoint,
            latency_ms=_latency_ms(start),
            detail=detail,
        )

    async def _check_backend_api(self, checked_at: str) -> GatewayHealthComponentInput:
        """Check the backend health endpoint configured for this gateway."""
        return await self._check_http_component(
            component_id="backend_api",
            component_type="backend_api",
            display_name="后台 API",
            endpoint=self._backend_health_url(),
            checked_at=checked_at,
        )

    async def _check_http_component(
        self,
        *,
        component_id: str,
        component_type: str,
        display_name: str,
        endpoint: str,
        checked_at: str,
    ) -> GatewayHealthComponentInput:
        """Check an HTTP component and normalize the result.

        :param component_id: Stable component identifier for ops views.
        :param component_type: Component type enum value used by ops_observer.
        :param display_name: Human-readable component name.
        :param endpoint: HTTP URL to probe.
        :param checked_at: ISO timestamp shared by this health report.
        :return: Component health record.
        """
        start = time.monotonic()
        detail = None
        online = False
        health_status = "offline"
        try:
            response = await self._client.get(endpoint)
            response.raise_for_status()
            online = True
            health_status = "healthy"
            detail = _response_summary(response)
        except Exception as exc:
            detail = str(exc)

        return GatewayHealthComponentInput(
            component_id=component_id,
            component_type=component_type,
            display_name=display_name,
            online=online,
            health_status=health_status,
            checked_at=checked_at,
            endpoint=endpoint,
            latency_ms=_latency_ms(start),
            detail=detail,
        )

    def _backend_health_url(self) -> str:
        """Resolve backend health URL from an API base URL."""
        base_url = self._settings.backend.base_url.rstrip("/")
        if base_url.endswith("/api/v1"):
            return f"{base_url[:-7]}{self._settings.backend.health_path}"
        return f"{base_url}{self._settings.backend.health_path}"


def _latency_ms(start: float) -> int:
    """Return elapsed milliseconds since a monotonic start time."""
    return max(int((time.monotonic() - start) * 1000), 0)


def _response_summary(response: httpx.Response) -> str:
    """Return a short diagnostic string for a successful HTTP response."""
    if not response.content:
        return f"http {response.status_code}"
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return f"http {response.status_code}"
    if isinstance(payload, dict) and "status" in payload:
        return f"status={payload['status']}"
    return f"http {response.status_code}"
