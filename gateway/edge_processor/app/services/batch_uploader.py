from __future__ import annotations

import asyncio
import logging

import httpx

from app.models.ingest_item import IngestItem


LOGGER = logging.getLogger(__name__)


async def batch_uploader_loop(settings, backend_client, ingest_queue) -> None:
    pending: list[IngestItem] = []

    while True:
        try:
            item = await asyncio.wait_for(ingest_queue.get(), timeout=settings.batch_interval_s)
            pending.append(item)

            while True:
                try:
                    pending.append(ingest_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
        except asyncio.TimeoutError:
            pass

        if not pending:
            continue

        try:
            LOGGER.info("uploading ingest batch", extra={"items": len(pending)})
            response = await backend_client.post_batch(pending)
            response.raise_for_status()
            LOGGER.info("uploaded ingest batch", extra={"items": len(pending), "status_code": response.status_code})
            pending = []
        except httpx.HTTPError:
            LOGGER.exception("failed to upload ingest batch; retaining batch in memory")
            await asyncio.sleep(settings.batch_interval_s)
