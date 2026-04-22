from __future__ import annotations

import asyncio

import httpx

from app.models.ingest_item import IngestItem
from app.services.batch_uploader import batch_uploader_loop
from app.services.influx_event_buffer import BufferedEvent
from app.settings import RuntimeSettings


class _FakeBackendClient:
    def __init__(self) -> None:
        self.batches: list[list[IngestItem]] = []
        self.uploaded = asyncio.Event()

    async def post_batch(self, items: list[IngestItem]) -> httpx.Response:
        self.batches.append(items)
        self.uploaded.set()
        return httpx.Response(204, request=httpx.Request("POST", "http://backend.test/api/v1/ingest/batch"))


class _EventDrivenBuffer:
    def __init__(self, event: BufferedEvent) -> None:
        self._event = asyncio.Event()
        self._buffered = [event]
        self.acked_event_ids: list[str] = []

    async def wait_for_pending(self, timeout_s: float) -> bool:
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout_s)
            self._event.clear()
            return True
        except TimeoutError:
            return False

    async def list_pending(self, limit: int) -> list[BufferedEvent]:
        return self._buffered[:limit]

    async def ack_delivered(self, event_ids: list[str]) -> None:
        self.acked_event_ids.extend(event_ids)
        self._buffered = []

    def trigger(self) -> None:
        self._event.set()


class _FallbackBuffer:
    def __init__(self, event: BufferedEvent) -> None:
        self._buffered = [event]
        self.acked_event_ids: list[str] = []
        self.wait_calls = 0

    async def wait_for_pending(self, timeout_s: float) -> bool:
        self.wait_calls += 1
        await asyncio.sleep(0)
        return False

    async def list_pending(self, limit: int) -> list[BufferedEvent]:
        return self._buffered[:limit]

    async def ack_delivered(self, event_ids: list[str]) -> None:
        self.acked_event_ids.extend(event_ids)
        self._buffered = []


def _build_buffered_event(event_id: str) -> BufferedEvent:
    return BufferedEvent(
        event_id=event_id,
        item=IngestItem(
            kind="telemetry",
            topic="gym/gym-gz-01/equipment/eq-001/telemetry",
            payload={"ts": 1712345678, "power_w": 320.5},
        ),
    )


def test_batch_uploader_uploads_immediately_after_event_trigger() -> None:
    settings = RuntimeSettings(batch_interval_s=30, influxdb={"replay_batch_size": 10})
    backend_client = _FakeBackendClient()
    event_buffer = _EventDrivenBuffer(_build_buffered_event("evt-immediate"))

    async def scenario() -> None:
        task = asyncio.create_task(batch_uploader_loop(settings, backend_client, event_buffer))
        try:
            await asyncio.sleep(0)
            event_buffer.trigger()
            await asyncio.wait_for(backend_client.uploaded.wait(), timeout=0.2)
            assert event_buffer.acked_event_ids == ["evt-immediate"]
            assert len(backend_client.batches) == 1
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    asyncio.run(scenario())


def test_batch_uploader_replays_pending_batch_after_timeout_fallback() -> None:
    settings = RuntimeSettings(batch_interval_s=1, influxdb={"replay_batch_size": 10})
    backend_client = _FakeBackendClient()
    event_buffer = _FallbackBuffer(_build_buffered_event("evt-fallback"))

    async def scenario() -> None:
        task = asyncio.create_task(batch_uploader_loop(settings, backend_client, event_buffer))
        try:
            await asyncio.wait_for(backend_client.uploaded.wait(), timeout=0.2)
            assert event_buffer.wait_calls >= 1
            assert event_buffer.acked_event_ids == ["evt-fallback"]
            assert len(backend_client.batches) == 1
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    asyncio.run(scenario())
