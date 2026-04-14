from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.models.device_command import (
    DeviceConfigCommandRecord,
    GatewayCommandResultRequest,
    GatewayPendingCommandList,
)
from app.models.ingest_item import IngestBatch, IngestItem
from app.models.system_health import GatewayHealthReportRequest
from app.settings import RuntimeSettings


class BackendClient:
    def __init__(self, settings: RuntimeSettings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.backend.base_url,
            timeout=settings.backend.request_timeout_s,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def post_batch(self, items: list[IngestItem]) -> httpx.Response:
        batch = IngestBatch(
            gateway_id=self._settings.gateway_id,
            sent_at=datetime.now(UTC).isoformat(),
            items=items,
        )
        return await self._client.post(self._settings.backend.ingest_path, json=batch.model_dump())

    async def fetch_pending_commands(self) -> list[DeviceConfigCommandRecord]:
        response = await self._client.get(
            self._settings.backend.gateway_command_pending_path.format(
                gateway_id=self._settings.gateway_id
            )
        )
        response.raise_for_status()
        payload = GatewayPendingCommandList.model_validate(response.json())
        return payload.items

    async def report_command_result(
        self,
        *,
        command_id: str,
        result: GatewayCommandResultRequest,
    ) -> DeviceConfigCommandRecord:
        response = await self._client.post(
            self._settings.backend.gateway_command_result_path.format(
                gateway_id=self._settings.gateway_id,
                command_id=command_id,
            ),
            json=result.model_dump(),
        )
        response.raise_for_status()
        return DeviceConfigCommandRecord.model_validate(response.json())

    async def post_system_health(
        self,
        report: GatewayHealthReportRequest,
    ) -> httpx.Response:
        return await self._client.post("/system/health/report", json=report.model_dump())
