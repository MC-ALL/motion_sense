from __future__ import annotations

import asyncio

import httpx

from app.models.ingest_item import IngestItem
from app.services.batch_uploader import batch_uploader_loop
from app.services.influx_event_buffer import BufferedEvent
from app.settings import RuntimeSettings


class _FakeBackendClient:
    """Capture uploaded batches without calling the real backend."""

    def __init__(self) -> None:
        """Initialize the fake backend state.

        :return: None.
        """
        self.batches: list[list[IngestItem]] = []
        self.uploaded = asyncio.Event()

    async def post_batch(self, items: list[IngestItem]) -> httpx.Response:
        """Record one uploaded ingest batch.

        :param items: Ingest items sent by ``batch_uploader_loop``.
        :return: Successful HTTP response compatible with the real client.
        """
        self.batches.append(items)
        self.uploaded.set()
        return httpx.Response(204, request=httpx.Request("POST", "http://backend.test/api/v1/ingest/batch"))


class _EventDrivenBuffer:
    """Buffer fake that wakes the uploader only after an explicit trigger."""

    def __init__(self, event: BufferedEvent) -> None:
        """Seed the buffer with a single pending event.

        :param event: Buffered event returned by ``list_pending`` until acked.
        :return: None.
        """
        self._event = asyncio.Event()
        self._buffered = [event]
        self.acked_event_ids: list[str] = []

    async def wait_for_pending(self, timeout_s: float) -> bool:
        """Wait until the test triggers pending data.

        :param timeout_s: Maximum wait duration used by the uploader loop.
        :return: ``True`` when triggered, otherwise ``False`` on timeout.
        """
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout_s)
            self._event.clear()
            return True
        except TimeoutError:
            return False

    async def list_pending(self, limit: int) -> list[BufferedEvent]:
        """Return buffered events up to the requested limit.

        :param limit: Maximum number of events requested by the uploader.
        :return: Pending events currently held by the fake buffer.
        """
        return self._buffered[:limit]

    async def ack_delivered(self, event_ids: list[str]) -> None:
        """Record acknowledged event IDs and clear the fake buffer.

        :param event_ids: Event IDs acknowledged by the uploader after upload.
        :return: None.
        """
        self.acked_event_ids.extend(event_ids)
        self._buffered = []

    def trigger(self) -> None:
        """Wake callers waiting in ``wait_for_pending``.

        :return: None.
        """
        self._event.set()


class _SequencedBuffer:
    """Buffer fake with deterministic wait results and pending batches."""

    def __init__(self, batches: list[list[BufferedEvent]], *, wait_results: list[bool]) -> None:
        """Initialize sequenced pending data for timing-sensitive tests.

        :param batches: Pending batches returned one at a time until acked.
        :param wait_results: Values returned by successive
            ``wait_for_pending`` calls.
        :return: None.
        """
        self._batches = batches
        self._wait_results = wait_results
        self._wait_calls = 0
        self.acked_event_ids: list[str] = []

    async def wait_for_pending(self, timeout_s: float) -> bool:
        """Return the next configured wait outcome.

        :param timeout_s: Uploader wait duration; ignored by this deterministic
            fake.
        :return: Next configured wait result, or ``False`` after the sequence
            is exhausted.
        """
        del timeout_s
        result = self._wait_results[self._wait_calls] if self._wait_calls < len(self._wait_results) else False
        self._wait_calls += 1
        await asyncio.sleep(0)
        return result

    async def list_pending(self, limit: int) -> list[BufferedEvent]:
        """Expose the current pending batch.

        :param limit: Maximum number of events requested by the uploader.
        :return: Current batch clipped to ``limit``, or an empty list.
        """
        if not self._batches:
            return []
        return self._batches[0][:limit]

    async def ack_delivered(self, event_ids: list[str]) -> None:
        """Acknowledge the current batch and advance the sequence.

        :param event_ids: Event IDs acknowledged by the uploader.
        :return: None.
        """
        self.acked_event_ids.extend(event_ids)
        if self._batches:
            self._batches.pop(0)


class _FallbackBuffer:
    """Buffer fake that never receives an event notification."""

    def __init__(self, event: BufferedEvent) -> None:
        """Seed fallback pending data.

        :param event: Buffered event returned when timeout fallback scans.
        :return: None.
        """
        self._buffered = [event]
        self.acked_event_ids: list[str] = []
        self.wait_calls = 0

    async def wait_for_pending(self, timeout_s: float) -> bool:
        """Pretend no pending notification arrived.

        :param timeout_s: Uploader wait duration; ignored by this fake.
        :return: Always ``False`` so the uploader uses timeout fallback.
        """
        self.wait_calls += 1
        await asyncio.sleep(0)
        return False

    async def list_pending(self, limit: int) -> list[BufferedEvent]:
        """Return fallback pending events.

        :param limit: Maximum number of events requested by the uploader.
        :return: Buffered events clipped to ``limit``.
        """
        return self._buffered[:limit]

    async def ack_delivered(self, event_ids: list[str]) -> None:
        """Record acknowledged fallback events.

        :param event_ids: Event IDs acknowledged by the uploader.
        :return: None.
        """
        self.acked_event_ids.extend(event_ids)
        self._buffered = []


def _build_buffered_event(event_id: str) -> BufferedEvent:
    """Build one buffered telemetry event for uploader tests.

    :param event_id: Stable event ID used for ack assertions.
    :return: Buffered telemetry event with a representative equipment payload.
    """
    return BufferedEvent(
        event_id=event_id,
        item=IngestItem(
            kind="telemetry",
            topic="gym/gym-gz-01/equipment/eq-001/telemetry",
            payload={"ts": 1712345678, "power_w": 320.5},
        ),
    )


def test_batch_uploader_uploads_immediately_after_event_trigger() -> None:
    """Verify that an explicit pending event wakes the uploader immediately.

    :return: None. Assertions confirm upload and ack side effects.
    """
    settings = RuntimeSettings(
        batch_interval_s=30,
        batch_min_window_s=0,
        influxdb={"replay_batch_size": 10},
    )
    backend_client = _FakeBackendClient()
    event_buffer = _EventDrivenBuffer(_build_buffered_event("evt-immediate"))

    async def scenario() -> None:
        """Run the uploader until one event-triggered upload completes.

        :return: None.
        """
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
    """Verify timeout fallback still replays pending buffered events.

    :return: None. Assertions confirm the fallback path polls and acks data.
    """
    settings = RuntimeSettings(batch_interval_s=1, influxdb={"replay_batch_size": 10})
    backend_client = _FakeBackendClient()
    event_buffer = _FallbackBuffer(_build_buffered_event("evt-fallback"))

    async def scenario() -> None:
        """Run the uploader until the fallback upload completes.

        :return: None.
        """
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


def test_batch_uploader_waits_for_min_window_before_small_batch_flush() -> None:
    """Verify small batches respect the configured minimum aggregation window.

    :return: None. Assertions confirm delayed flush and acked event IDs.
    """
    settings = RuntimeSettings(
        batch_interval_s=30,
        batch_min_window_s=0.05,
        batch_trigger_threshold=3,
        influxdb={"replay_batch_size": 10},
    )
    backend_client = _FakeBackendClient()
    event_buffer = _SequencedBuffer(
        [[_build_buffered_event("evt-small-1"), _build_buffered_event("evt-small-2")]],
        wait_results=[True, False],
    )

    async def scenario() -> None:
        """Run one uploader cycle and measure the delayed flush.

        :return: None.
        """
        start = asyncio.get_running_loop().time()
        task = asyncio.create_task(batch_uploader_loop(settings, backend_client, event_buffer))
        try:
            await asyncio.wait_for(backend_client.uploaded.wait(), timeout=0.2)
            elapsed = asyncio.get_running_loop().time() - start
            assert elapsed >= 0.045
            assert event_buffer.acked_event_ids == ["evt-small-1", "evt-small-2"]
            assert len(backend_client.batches) == 1
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    asyncio.run(scenario())


def test_batch_uploader_flushes_immediately_when_threshold_is_reached() -> None:
    """Verify threshold-sized batches bypass the minimum wait window.

    :return: None. Assertions confirm prompt upload and acked event IDs.
    """
    settings = RuntimeSettings(
        batch_interval_s=30,
        batch_min_window_s=30,
        batch_trigger_threshold=2,
        influxdb={"replay_batch_size": 10},
    )
    backend_client = _FakeBackendClient()
    event_buffer = _SequencedBuffer(
        [[_build_buffered_event("evt-threshold-1"), _build_buffered_event("evt-threshold-2")]],
        wait_results=[True],
    )

    async def scenario() -> None:
        """Run one uploader cycle and measure threshold-triggered flush timing.

        :return: None.
        """
        start = asyncio.get_running_loop().time()
        task = asyncio.create_task(batch_uploader_loop(settings, backend_client, event_buffer))
        try:
            await asyncio.wait_for(backend_client.uploaded.wait(), timeout=0.2)
            elapsed = asyncio.get_running_loop().time() - start
            assert elapsed < 0.05
            assert event_buffer.acked_event_ids == ["evt-threshold-1", "evt-threshold-2"]
            assert len(backend_client.batches) == 1
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    asyncio.run(scenario())
