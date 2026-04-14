from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime

import httpx

from app.models.system_health import GatewayHealthComponentInput, GatewayHealthReportRequest
from app.settings import RuntimeSettings


class GatewayHealthReporter:
    def __init__(self, settings: RuntimeSettings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(timeout=settings.backend.request_timeout_s)

    async def close(self) -> None:
        await self._client.aclose()

    async def collect_report(self) -> GatewayHealthReportRequest:
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
        endpoint = f"http://127.0.0.1:{self._settings.port}/healthz"
        return await self._check_http_component(
            component_id="gateway_api",
            component_type="gateway_api",
            display_name="网关 API",
            endpoint=endpoint,
            checked_at=checked_at,
        )

    def _edge_processor_component(self, checked_at: str) -> GatewayHealthComponentInput:
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
        base_url = self._settings.backend.base_url.rstrip("/")
        if base_url.endswith("/api/v1"):
            return f"{base_url[:-7]}{self._settings.backend.health_path}"
        return f"{base_url}{self._settings.backend.health_path}"


def _latency_ms(start: float) -> int:
    return max(int((time.monotonic() - start) * 1000), 0)


def _response_summary(response: httpx.Response) -> str:
    if not response.content:
        return f"http {response.status_code}"
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return f"http {response.status_code}"
    if isinstance(payload, dict) and "status" in payload:
        return f"status={payload['status']}"
    return f"http {response.status_code}"
