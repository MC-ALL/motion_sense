from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.models.device_command import (
    DeviceConfigCommandRecord,
    GatewayCommandResultRequest,
    GatewayPendingCommandList,
)
from app.models.ingest_item import IngestBatch, IngestItem
from app.settings import RuntimeSettings


class BackendClient:
    """HTTP client for backend ingestion and gateway command APIs."""

    def __init__(self, settings: RuntimeSettings) -> None:
        """Create a backend HTTP client.

        :param settings: Runtime settings containing backend URL and timeout.
        """
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.backend.base_url,
            timeout=settings.backend.request_timeout_s,
        )

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()

    async def post_batch(self, items: list[IngestItem]) -> httpx.Response:
        """Post a batch of buffered MQTT events to the backend.

        :param items: Normalized ingest items selected from the local replay buffer.
        :return: Raw HTTP response so the caller can record status and decide acking.
        """
        batch = IngestBatch(
            gateway_id=self._settings.gateway_id,
            sent_at=datetime.now(UTC).isoformat(),
            items=items,
        )
        return await self._client.post(self._settings.backend.ingest_path, json=batch.model_dump())

    async def fetch_pending_commands(self) -> list[DeviceConfigCommandRecord]:
        """Fetch commands currently leased or pending for this gateway.

        :return: Backend command records that should be executed by the gateway.
        :raises httpx.HTTPStatusError: If the backend rejects the request.
        """
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
        """Report a command execution result to the backend.

        :param command_id: Backend command identifier being completed.
        :param result: Gateway execution status and diagnostic payload.
        :return: Updated command record returned by the backend.
        :raises httpx.HTTPStatusError: If the backend rejects the result.
        """
        response = await self._client.post(
            self._settings.backend.gateway_command_result_path.format(
                gateway_id=self._settings.gateway_id,
                command_id=command_id,
            ),
            json=result.model_dump(),
        )
        response.raise_for_status()
        return DeviceConfigCommandRecord.model_validate(response.json())
