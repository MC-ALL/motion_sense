from __future__ import annotations

import asyncio
import logging

import httpx


LOGGER = logging.getLogger(__name__)


async def batch_uploader_loop(settings, backend_client, event_buffer) -> None:
    while True:
        try:
            pending = await event_buffer.list_pending(settings.influxdb.replay_batch_size)
        except Exception:
            LOGGER.exception("failed to query pending batch from influxdb")
            await asyncio.sleep(settings.batch_interval_s)
            continue

        if not pending:
            await asyncio.sleep(settings.batch_interval_s)
            continue

        try:
            LOGGER.info("uploading ingest batch", extra={"items": len(pending)})
            response = await backend_client.post_batch([event.item for event in pending])
            response.raise_for_status()
            await event_buffer.ack_delivered([event.event_id for event in pending])
            LOGGER.info("uploaded ingest batch", extra={"items": len(pending), "status_code": response.status_code})
        except httpx.HTTPError:
            LOGGER.exception("failed to upload ingest batch; retaining batch in influxdb")
            await asyncio.sleep(settings.batch_interval_s)
            continue
        except Exception:
            LOGGER.exception("failed to acknowledge delivered batch; pending records will be replayed")
            await asyncio.sleep(settings.batch_interval_s)
            continue

        if len(pending) < settings.influxdb.replay_batch_size:
            await asyncio.sleep(settings.batch_interval_s)
