from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx


LOGGER = logging.getLogger(__name__)


BatchResultCallback = Callable[[int, bool, int | None, str | None], Awaitable[None]]


async def batch_uploader_loop(
    settings,
    backend_client,
    event_buffer,
    on_batch_result: BatchResultCallback | None = None,
) -> None:
    trigger_threshold = min(
        max(settings.batch_trigger_threshold, 1),
        settings.influxdb.replay_batch_size,
    )
    preview_limit = min(trigger_threshold, settings.influxdb.replay_batch_size)

    while True:
        event_triggered = await event_buffer.wait_for_pending(settings.batch_interval_s)
        aggregate_deadline = (
            asyncio.get_running_loop().time() + settings.batch_min_window_s
            if event_triggered
            else None
        )

        while True:
            pending_preview: list = []
            try:
                pending_preview = await event_buffer.list_pending(preview_limit)
            except Exception:
                LOGGER.exception("failed to query pending batch from influxdb")
                await asyncio.sleep(settings.batch_interval_s)
                break

            if not pending_preview:
                break

            if _should_wait_for_more_events(
                aggregate_deadline=aggregate_deadline,
                pending_count=len(pending_preview),
                trigger_threshold=trigger_threshold,
            ):
                await event_buffer.wait_for_pending(
                    max(aggregate_deadline - asyncio.get_running_loop().time(), 0.0)
                )
                continue

            pending: list = []
            try:
                pending = await event_buffer.list_pending(settings.influxdb.replay_batch_size)
            except Exception:
                LOGGER.exception("failed to query full pending batch from influxdb")
                await asyncio.sleep(settings.batch_interval_s)
                break

            try:
                LOGGER.info("uploading ingest batch", extra={"items": len(pending)})
                response = await backend_client.post_batch([event.item for event in pending])
                response.raise_for_status()
                await event_buffer.ack_delivered([event.event_id for event in pending])
                LOGGER.info("uploaded ingest batch", extra={"items": len(pending), "status_code": response.status_code})
                if on_batch_result is not None:
                    await on_batch_result(len(pending), True, response.status_code, None)
            except httpx.HTTPError:
                LOGGER.exception("failed to upload ingest batch; retaining batch in influxdb")
                if on_batch_result is not None:
                    await on_batch_result(len(pending), False, None, "http error")
                await asyncio.sleep(settings.batch_interval_s)
                break
            except Exception:
                LOGGER.exception("failed to acknowledge delivered batch; pending records will be replayed")
                if on_batch_result is not None:
                    await on_batch_result(len(pending), False, None, "ack failed")
                await asyncio.sleep(settings.batch_interval_s)
                break

            aggregate_deadline = None
            if len(pending) < settings.influxdb.replay_batch_size:
                break


def _should_wait_for_more_events(
    *,
    aggregate_deadline: float | None,
    pending_count: int,
    trigger_threshold: int,
) -> bool:
    if aggregate_deadline is None:
        return False
    if pending_count >= trigger_threshold:
        return False
    return asyncio.get_running_loop().time() < aggregate_deadline
