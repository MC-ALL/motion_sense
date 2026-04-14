from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.models.ingest_item import IngestBatch, IngestItem
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
