from __future__ import annotations

import asyncio
import contextlib
import logging

from app.services.backend_client import BackendClient
from app.services.batch_uploader import batch_uploader_loop
from app.services.influx_event_buffer import InfluxEventBuffer
from app.services.mqtt_ingest import mqtt_ingest_loop
from app.services.runtime_config import RuntimeConfigManager
from app.settings import RuntimeSettings


LOGGER = logging.getLogger(__name__)


class EdgeProcessorRunner:
    def __init__(self, settings: RuntimeSettings) -> None:
        self._settings = settings
        self._supervisor_task: asyncio.Task[None] | None = None
        self._runtime_config_manager = RuntimeConfigManager(settings)
        self._backend_client = BackendClient(settings)
        self._event_buffer = InfluxEventBuffer(settings)

    async def start(self) -> None:
        if self._supervisor_task is not None:
            return

        LOGGER.info("starting edge processor runner", extra={"gateway_id": self._settings.gateway_id})
        await self._event_buffer.initialize()
        self._supervisor_task = asyncio.create_task(self._run(), name="edge-processor-runner")

    async def stop(self) -> None:
        if self._supervisor_task is None:
            return

        self._supervisor_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._supervisor_task
        self._supervisor_task = None
        await self._backend_client.close()
        await self._event_buffer.close()
        LOGGER.info("edge processor runner stopped", extra={"gateway_id": self._settings.gateway_id})

    async def _run(self) -> None:
        async with asyncio.TaskGroup() as task_group:
            task_group.create_task(
                mqtt_ingest_loop(self._settings, self._event_buffer, self._runtime_config_manager),
                name="mqtt-ingest-loop",
            )
            task_group.create_task(
                batch_uploader_loop(self._settings, self._backend_client, self._event_buffer),
                name="batch-uploader-loop",
            )
            task_group.create_task(self._device_offline_monitor_loop(), name="device-offline-loop")
            task_group.create_task(self._rules_reload_loop(), name="rules-reload-loop")

    async def _device_offline_monitor_loop(self) -> None:
        while True:
            LOGGER.debug("device offline monitor heartbeat", extra={"gateway_id": self._settings.gateway_id})
            await asyncio.sleep(self._settings.health_interval_s)

    async def _rules_reload_loop(self) -> None:
        while True:
            self._runtime_config_manager.poll_rules_reload()
            await asyncio.sleep(self._settings.rules_reload_interval_s)
