from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from contextlib import suppress
from time import time

from aiomqtt import MqttError

from app.device_profiles import build_device_profiles
from app.models import PublishedMessage, SimulatorProfiles
from app.mqtt_client import SimulatorMqttPublisher
from app.scenario_engine import ScenarioEngine
from app.settings import RuntimeSettings

LOGGER = logging.getLogger(__name__)
PUBLISH_GROUPS = ("equipment", "wristband", "env")


class DeviceSimulatorRunner:
    def __init__(self, settings: RuntimeSettings) -> None:
        self._settings = settings
        self._profiles: SimulatorProfiles = build_device_profiles(settings)
        self._engine = ScenarioEngine(settings, self._profiles)
        self._publish_queues = {
            group: asyncio.Queue[PublishedMessage](maxsize=settings.mqtt.publish_queue_size)
            for group in PUBLISH_GROUPS
        }

    async def run_forever(self) -> None:
        while True:
            try:
                async with AsyncExitStack() as stack:
                    publishers = {
                        group: await stack.enter_async_context(
                            SimulatorMqttPublisher(
                                self._settings.mqtt,
                                client_id_suffix=group,
                            )
                        )
                        for group in PUBLISH_GROUPS
                    }
                    LOGGER.info(
                        "connected to mqtt broker for device simulation",
                        extra={
                            "host": self._settings.mqtt.host,
                            "port": self._settings.mqtt.port,
                            "publish_groups": list(PUBLISH_GROUPS),
                            "equipment_count": len(self._profiles.equipment),
                            "wristband_count": len(self._profiles.wristbands),
                            "env_count": len(self._profiles.env_nodes),
                        },
                    )
                    await self._run_connected(publishers)
            except asyncio.CancelledError:
                raise
            except MqttError:
                LOGGER.exception("mqtt connection failed; retrying")
                await asyncio.sleep(2.0)

    async def _run_connected(self, publishers: dict[str, SimulatorMqttPublisher]) -> None:
        tasks = [
            asyncio.create_task(
                self._publish_loop(group, publisher),
                name=f"sim-publish-loop-{group}",
            )
            for group, publisher in publishers.items()
        ]
        tasks.extend(
            asyncio.create_task(self._equipment_loop(profile.identity.device_id), name=f"sim-equipment-{profile.identity.device_id}")
            for profile in self._profiles.equipment
        )
        tasks.extend(
            asyncio.create_task(self._wristband_loop(profile.identity.device_id), name=f"sim-wristband-{profile.identity.device_id}")
            for profile in self._profiles.wristbands
        )
        tasks.extend(
            asyncio.create_task(self._env_loop(profile.identity.device_id), name=f"sim-env-{profile.identity.device_id}")
            for profile in self._profiles.env_nodes
        )
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        try:
            for task in done:
                task.result()
        finally:
            for task in pending:
                task.cancel()
            for task in pending:
                with suppress(asyncio.CancelledError):
                    await task

    async def _equipment_loop(self, device_id: str) -> None:
        await self._sleep_startup_jitter(device_id)
        interval_s = self._settings.intervals.equipment_telemetry_ms / 1000.0
        while True:
            await self._enqueue_messages(self._engine.step_equipment(device_id, int(time())))
            await asyncio.sleep(interval_s)

    async def _wristband_loop(self, device_id: str) -> None:
        await self._sleep_startup_jitter(device_id)
        interval_s = self._settings.intervals.wristband_telemetry_ms / 1000.0
        while True:
            await self._enqueue_messages(self._engine.step_wristband(device_id, int(time())))
            await asyncio.sleep(interval_s)

    async def _env_loop(self, device_id: str) -> None:
        await self._sleep_startup_jitter(device_id)
        interval_s = self._settings.intervals.env_telemetry_ms / 1000.0
        while True:
            await self._enqueue_messages(self._engine.step_env(device_id, int(time())))
            await asyncio.sleep(interval_s)

    async def _enqueue_messages(self, messages: list[PublishedMessage]) -> None:
        for item in messages:
            await self._publish_queues[_publish_group_for_topic(item.topic)].put(item)

    async def _publish_loop(self, group: str, publisher: SimulatorMqttPublisher) -> None:
        queue = self._publish_queues[group]
        while True:
            item = await queue.get()
            await publisher.publish_json(topic=item.topic, payload=item.payload, retain=item.retain)
            queue.task_done()

    async def _sleep_startup_jitter(self, device_id: str) -> None:
        jitter_window_ms = self._settings.intervals.startup_jitter_ms
        if jitter_window_ms <= 0:
            return
        offset_ms = (sum(ord(char) for char in device_id) * 37) % jitter_window_ms
        await asyncio.sleep(offset_ms / 1000.0)


def _publish_group_for_topic(topic: str) -> str:
    parts = topic.split("/")
    if len(parts) < 4:
        raise ValueError(f"invalid mqtt topic for simulator publish routing: {topic}")
    device_type = parts[2]
    if device_type not in PUBLISH_GROUPS:
        raise ValueError(f"unsupported simulator publish group: {device_type}")
    return device_type
