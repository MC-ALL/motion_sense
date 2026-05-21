from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import Any

from app.models.device_command import DeviceConfigCommandRecord, GatewayCommandResultRequest
from app.models.ingest_item import IngestItem
from app.models.ops import GatewayOpsHealthSummary, GatewayOpsStats
from app.services.backend_client import BackendClient
from app.services.batch_uploader import batch_uploader_loop
from app.services.device_presence import DeviceTransition, DevicePresenceTracker
from app.services.gateway_command_channel import GatewayCommandChannel
from app.services.health_reporter import GatewayHealthReporter
from app.services.influx_event_buffer import InfluxEventBuffer
from app.services.mqtt_ingest import mqtt_ingest_loop
from app.services.mqtt_publisher import MqttPublisher
from app.services.ops_websocket_manager import OpsWebSocketManager
from app.services.rule_engine import DeviceOfflineRule, EmittedAlert, RuleEngine
from app.services.runtime_config import RuntimeConfigManager
from app.settings import RuntimeSettings
from app.utils.topic_parser import ParsedTopic, parse_topic


LOGGER = logging.getLogger(__name__)
EDGE_INTERNAL_PUBLISHER = "edge_processor"
EDGE_GENERATED_FIRMWARE_VERSION = "edge-generated"
EDGE_GENERATED_MAC = "00:00:00:00:00:00"
DEVICE_CONFIG_REQUIRED_FIELDS: dict[str, dict[str, type | tuple[type, ...]]] = {
    "equipment": {
        "target_reps": int,
    },
    "wristband": {
        "hr_alert_threshold_high": int,
        "hr_alert_threshold_low": int,
        "notify_interval_ms": int,
        "fall_detect_enabled": bool,
    },
    "env": {
        "telemetry_interval_s": int,
        "co2_threshold_ppm": (int, float),
        "pm25_threshold_ugm3": (int, float),
    },
}

ALERT_PRIORITY_BY_TYPE = {
    "device_offline": "P1",
    "overload": "P1",
    "co2_high": "P1",
    "co2_critical": "P0",
    "pm25_high": "P1",
    "temperature_high": "P1",
}

ALERT_LEVEL_BY_TYPE = {
    "device_offline": "warning",
    "overload": "critical",
    "co2_high": "warning",
    "co2_critical": "critical",
    "pm25_high": "warning",
    "temperature_high": "warning",
}


class EdgeProcessorRunner:
    """Own and coordinate all long-running edge processor services."""

    def __init__(self, settings: RuntimeSettings) -> None:
        """Create a runner and all owned service clients.

        :param settings: Validated runtime settings for the edge processor.
        """
        self._settings = settings
        self._supervisor_task: asyncio.Task[None] | None = None
        self._runtime_config_manager = RuntimeConfigManager(settings)
        self._backend_client = BackendClient(settings)
        self._gateway_command_channel = GatewayCommandChannel(settings)
        self._event_buffer = InfluxEventBuffer(settings)
        self._health_reporter = GatewayHealthReporter(settings)
        self._mqtt_publisher = MqttPublisher(settings)
        self._rule_engine = RuleEngine(self._runtime_config_manager.rules_path)
        self._device_presence_tracker = DevicePresenceTracker()
        self._command_result_cache: dict[str, GatewayCommandResultRequest] = {}
        self._ops_websocket_manager: OpsWebSocketManager | None = None
        self._started_at = datetime.now(UTC)
        self._latest_health_report = None
        self._latest_health_error: str | None = None
        self._last_health_checked_at: str | None = None
        self._mqtt_events_received_total = 0
        self._telemetry_events_total = 0
        self._alert_events_total = 0
        self._binding_events_total = 0
        self._status_events_total = 0
        self._generated_alerts_total = 0
        self._generated_status_total = 0
        self._command_polls_total = 0
        self._commands_executed_total = 0
        self._command_failures_total = 0
        self._batch_upload_success_total = 0
        self._batch_upload_failure_total = 0
        self._last_batch_size = 0
        self._last_batch_uploaded_at: str | None = None
        self._last_batch_error: str | None = None
        self._health_check_success_total = 0
        self._health_check_failure_total = 0
        self._command_wakeup_event = asyncio.Event()
        self._command_wakeup_event.set()

    def set_ops_websocket_manager(self, manager: OpsWebSocketManager) -> None:
        """Attach the WebSocket manager used for ops snapshot broadcasts.

        :param manager: Manager created by the FastAPI application.
        """
        self._ops_websocket_manager = manager

    async def start(self) -> None:
        """Initialize dependencies and start the supervisor task."""
        if self._supervisor_task is not None:
            return

        LOGGER.info("starting edge processor runner", extra={"gateway_id": self._settings.gateway_id})
        self._rule_engine.reload_rules()
        self._runtime_config_manager.sync_rules_reload_state()
        await self._event_buffer.initialize()
        self._supervisor_task = asyncio.create_task(self._run(), name="edge-processor-runner")

    async def stop(self) -> None:
        """Cancel background tasks and close owned network clients."""
        if self._supervisor_task is None:
            return

        self._supervisor_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._supervisor_task
        self._supervisor_task = None
        await self._backend_client.close()
        await self._health_reporter.close()
        await self._mqtt_publisher.close()
        await self._event_buffer.close()
        LOGGER.info("edge processor runner stopped", extra={"gateway_id": self._settings.gateway_id})

    async def _run(self) -> None:
        """Run all background loops under one task group."""
        async with asyncio.TaskGroup() as task_group:
            task_group.create_task(
                mqtt_ingest_loop(
                    self._settings,
                    self._event_buffer,
                    self._runtime_config_manager,
                    on_event_received=self._on_ingest_event,
                ),
                name="mqtt-ingest-loop",
            )
            task_group.create_task(
                batch_uploader_loop(
                    self._settings,
                    self._backend_client,
                    self._event_buffer,
                    on_batch_result=self._on_batch_result,
                ),
                name="batch-uploader-loop",
            )
            task_group.create_task(self._device_offline_monitor_loop(), name="device-offline-loop")
            task_group.create_task(self._rules_reload_loop(), name="rules-reload-loop")
            task_group.create_task(self._command_poll_loop(), name="command-poll-loop")
            task_group.create_task(self._command_channel_loop(), name="command-channel-loop")
            task_group.create_task(self._health_check_loop(), name="health-check-loop")

    async def _device_offline_monitor_loop(self) -> None:
        """Poll presence state and emit offline transitions when rules enable it."""
        while True:
            rule = self._rule_engine.device_offline_rule()
            if rule.enabled:
                for transition in self._device_presence_tracker.collect_new_offline(timeout_s=rule.timeout_s):
                    await self._emit_offline_events(transition, rule)
            await asyncio.sleep(self._rule_engine.check_interval_s())

    async def _rules_reload_loop(self) -> None:
        """Reload alert rules after config updates or filesystem changes."""
        while True:
            if await self._runtime_config_manager.wait_for_rules_reload(self._settings.rules_reload_interval_s):
                self._rule_engine.reload_rules()

    async def _command_poll_loop(self) -> None:
        """Fetch pending backend commands and execute them with result caching."""
        while True:
            should_wait = not self._command_wakeup_event.is_set()
            self._command_wakeup_event.clear()
            if should_wait:
                try:
                    await asyncio.wait_for(
                        self._command_wakeup_event.wait(),
                        timeout=self._settings.command_poll_interval_s,
                    )
                except TimeoutError:
                    pass
                self._command_wakeup_event.clear()
            await self._flush_command_results()
            try:
                self._command_polls_total += 1
                commands = await self._backend_client.fetch_pending_commands()
            except Exception:
                LOGGER.exception(
                    "failed to fetch pending gateway commands",
                    extra={"gateway_id": self._settings.gateway_id},
                )
                await asyncio.sleep(self._settings.command_poll_interval_s)
                continue

            for command in commands:
                if command.command_id in self._command_result_cache:
                    continue

                result = await self._execute_command(command)
                self._command_result_cache[command.command_id] = result
                await self._flush_command_result(command.command_id)

    async def _command_channel_loop(self) -> None:
        """Maintain the backend command-ready WebSocket as a low-latency wakeup."""
        while True:
            try:
                await self._gateway_command_channel.listen(self._wake_command_fetch)
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception(
                    "gateway command channel disconnected",
                    extra={"gateway_id": self._settings.gateway_id},
                )
            await asyncio.sleep(self._settings.backend.gateway_command_ws_reconnect_interval_s)

    async def _health_check_loop(self) -> None:
        """Periodically refresh cached infrastructure health and ops counters."""
        while True:
            try:
                report = await self._health_reporter.collect_report()
                await self._cache_health_report(report)
                self._health_check_success_total += 1
                self._latest_health_error = None
            except Exception:
                self._health_check_failure_total += 1
                self._latest_health_error = "failed to collect gateway health snapshot"
                LOGGER.exception(
                    "failed to collect gateway infrastructure health",
                    extra={"gateway_id": self._settings.gateway_id},
                )
            await asyncio.sleep(self._settings.health_interval_s)

    async def _on_ingest_event(self, parsed_topic: ParsedTopic, payload: dict[str, Any]) -> None:
        """Update counters and local rules for one accepted MQTT event.

        :param parsed_topic: Parsed topic for the event stored in the buffer.
        :param payload: Enriched MQTT payload.
        """
        self._mqtt_events_received_total += 1
        if parsed_topic.action == "telemetry":
            self._telemetry_events_total += 1
        elif parsed_topic.action == "alert":
            self._alert_events_total += 1
        elif parsed_topic.action == "binding":
            self._binding_events_total += 1
        elif parsed_topic.action == "status":
            self._status_events_total += 1

        if parsed_topic.action != "binding":
            self._device_presence_tracker.mark_seen(parsed_topic, payload)

        if parsed_topic.action != "telemetry":
            return

        for alert in self._rule_engine.evaluate_telemetry(parsed_topic, payload):
            await self._emit_rule_alert(alert)

    async def _emit_rule_alert(self, alert: EmittedAlert) -> None:
        """Publish and buffer an alert generated by the rule engine.

        :param alert: Edge-generated alert payload fields.
        """
        self._generated_alerts_total += 1
        topic = f"gym/{alert.gym_id}/{alert.device_type}/{alert.device_id}/alert"
        priority = ALERT_PRIORITY_BY_TYPE.get(alert.alert_type, "P1")
        level = ALERT_LEVEL_BY_TYPE.get(alert.alert_type, alert.level)
        payload = {
            "ts": alert.observed_at_s,
            "priority": priority,
            "level": level,
            "alert_type": alert.alert_type,
            "message": alert.message,
            "value": alert.value,
            "threshold": alert.threshold,
            "published_by": EDGE_INTERNAL_PUBLISHER,
        }
        await self._emit_generated_event(kind="alert", topic=topic, payload=payload, retain=False)

    async def _emit_offline_events(self, transition: DeviceTransition, rule: DeviceOfflineRule) -> None:
        """Emit both alert and retained status events for a device timeout.

        :param transition: Device identity and timestamp for the offline edge.
        :param rule: Active offline rule that supplied timeout and severity.
        """
        identity = transition.identity
        alert_topic = f"gym/{identity.gym_id}/{identity.device_type}/{identity.device_id}/alert"
        alert_payload = {
            "ts": transition.observed_at_s,
            "priority": "P1",
            "level": ALERT_LEVEL_BY_TYPE["device_offline"],
            "alert_type": "device_offline",
            "message": f"device offline: no heartbeat for {rule.timeout_s}s",
            "published_by": EDGE_INTERNAL_PUBLISHER,
        }
        await self._emit_generated_event(kind="alert", topic=alert_topic, payload=alert_payload, retain=False)
        await self._emit_offline_status_event(transition)

    async def _emit_offline_status_event(self, transition: DeviceTransition) -> None:
        """Publish and buffer a retained edge-generated offline status event.

        :param transition: Device identity and transition timestamp.
        """
        self._generated_status_total += 1
        identity = transition.identity
        status_topic = f"gym/{identity.gym_id}/{identity.device_type}/{identity.device_id}/status"
        status_payload = {
            "ts": transition.observed_at_s,
            "status": "offline",
            "firmware_version": EDGE_GENERATED_FIRMWARE_VERSION,
            "mac": EDGE_GENERATED_MAC,
            "published_by": EDGE_INTERNAL_PUBLISHER,
        }
        await self._emit_generated_event(kind="status", topic=status_topic, payload=status_payload, retain=True)

    async def _emit_generated_event(
        self,
        *,
        kind: str,
        topic: str,
        payload: dict[str, Any],
        retain: bool,
    ) -> None:
        """Store a locally generated event and publish it to MQTT.

        :param kind: Backend ingest kind, usually ``alert`` or ``status``.
        :param topic: MQTT topic for both local publish and backend ingest.
        :param payload: JSON payload to persist and publish.
        :param retain: MQTT retained flag for the publish operation.
        """
        parsed = parse_topic(topic)
        item = IngestItem(kind=kind, topic=topic, payload=payload)

        try:
            await self._event_buffer.append(item, parsed)
        except Exception:
            LOGGER.exception("failed to append generated event", extra={"topic": topic, "kind": kind})

        try:
            await self._mqtt_publisher.publish_json(
                topic=topic,
                payload=payload,
                qos=self._settings.mqtt.qos,
                retain=retain,
            )
        except Exception:
            LOGGER.exception("failed to publish generated mqtt event", extra={"topic": topic, "kind": kind})

    async def _execute_command(
        self,
        command: DeviceConfigCommandRecord,
    ) -> GatewayCommandResultRequest:
        """Execute a backend command and convert the outcome into a result record.

        :param command: Command fetched from the backend queue.
        :return: Result payload ready to report back to the backend.
        """
        try:
            detail = await self._apply_command(command)
            self._commands_executed_total += 1
            return GatewayCommandResultRequest(
                status="succeeded",
                reported_at=datetime.now(UTC).isoformat(),
                detail=detail,
            )
        except Exception as exc:
            self._command_failures_total += 1
            LOGGER.exception(
                "failed to execute gateway command",
                extra={
                    "gateway_id": self._settings.gateway_id,
                    "command_id": command.command_id,
                    "topic": command.topic,
                },
            )
            return GatewayCommandResultRequest(
                status="failed",
                reported_at=datetime.now(UTC).isoformat(),
                detail=str(exc),
            )

    async def _on_batch_result(
        self,
        item_count: int,
        succeeded: bool,
        status_code: int | None,
        error: str | None,
    ) -> None:
        """Update upload counters after one batch upload attempt.

        :param item_count: Number of items included in the attempted batch.
        :param succeeded: Whether the backend accepted and acking succeeded.
        :param status_code: Backend HTTP status if available.
        :param error: Short failure reason used by ops stats.
        """
        del status_code
        self._last_batch_size = item_count
        if succeeded:
            self._batch_upload_success_total += 1
            self._last_batch_uploaded_at = datetime.now(UTC).isoformat()
            self._last_batch_error = None
        else:
            self._batch_upload_failure_total += 1
            self._last_batch_error = error or "upload failed"

    async def _cache_health_report(self, report) -> None:
        """Cache the latest health report and broadcast its summary."""
        self._latest_health_report = report
        self._last_health_checked_at = report.reported_at
        if self._ops_websocket_manager is not None:
            summary = self._build_health_summary(report)
            await self._ops_websocket_manager.broadcast(
                {"type": "ops_snapshot", "data": summary.model_dump()}
            )

    async def get_ops_health_summary(self) -> GatewayOpsHealthSummary:
        """Return the current gateway health summary for ops endpoints."""
        report = await self._latest_or_collect_health_report()
        return self._build_health_summary(report)

    async def get_ops_components(self):
        """Return current component-level health records for ops endpoints."""
        report = await self._latest_or_collect_health_report()
        return report.components

    async def get_ops_stats(self) -> GatewayOpsStats:
        """Return runtime counters and current health metadata for ops endpoints."""
        active_connections = 0
        if self._ops_websocket_manager is not None:
            active_connections = await self._ops_websocket_manager.connection_count()

        last_known_health_status = "unknown"
        if self._latest_health_report is not None:
            last_known_health_status = self._build_health_summary(self._latest_health_report).health_status

        return GatewayOpsStats(
            module_id=f"gateway:{self._settings.gateway_id}",
            gateway_id=self._settings.gateway_id,
            gym_id=self._settings.gym_id,
            started_at=self._started_at.isoformat(),
            uptime_s=max(int((datetime.now(UTC) - self._started_at).total_seconds()), 0),
            active_ops_ws_connections=active_connections,
            mqtt_events_received_total=self._mqtt_events_received_total,
            telemetry_events_total=self._telemetry_events_total,
            alert_events_total=self._alert_events_total,
            binding_events_total=self._binding_events_total,
            status_events_total=self._status_events_total,
            generated_alerts_total=self._generated_alerts_total,
            generated_status_total=self._generated_status_total,
            command_polls_total=self._command_polls_total,
            commands_executed_total=self._commands_executed_total,
            command_failures_total=self._command_failures_total,
            batch_upload_success_total=self._batch_upload_success_total,
            batch_upload_failure_total=self._batch_upload_failure_total,
            last_batch_size=self._last_batch_size,
            last_batch_uploaded_at=self._last_batch_uploaded_at,
            last_batch_error=self._last_batch_error,
            health_check_success_total=self._health_check_success_total,
            health_check_failure_total=self._health_check_failure_total,
            last_health_checked_at=self._last_health_checked_at,
            last_health_error=self._latest_health_error,
            last_known_health_status=last_known_health_status,
            batch_interval_s=self._settings.batch_interval_s,
            command_poll_interval_s=self._settings.command_poll_interval_s,
            health_interval_s=self._settings.health_interval_s,
            replay_batch_size=self._settings.influxdb.replay_batch_size,
        )

    async def _latest_or_collect_health_report(self):
        """Return cached health report or collect one on first access."""
        if self._latest_health_report is None:
            report = await self._health_reporter.collect_report()
            await self._cache_health_report(report)
        assert self._latest_health_report is not None
        return self._latest_health_report

    def _build_health_summary(self, report) -> GatewayOpsHealthSummary:
        """Build the gateway-level health summary from component states."""
        component_total = len(report.components)
        healthy_components = sum(1 for item in report.components if item.online and item.health_status == "healthy")
        degraded_components = sum(1 for item in report.components if item.online and item.health_status == "degraded")
        offline_components = sum(
            1
            for item in report.components
            if (not item.online) or item.health_status == "offline"
        )

        if component_total == 0:
            health_status = "unknown"
            online = False
        elif offline_components > 0:
            health_status = "offline"
            online = False
        elif degraded_components > 0:
            health_status = "degraded"
            online = True
        else:
            health_status = "healthy"
            online = True

        return GatewayOpsHealthSummary(
            module_id=f"gateway:{self._settings.gateway_id}",
            gateway_id=self._settings.gateway_id,
            gym_id=self._settings.gym_id,
            online=online,
            health_status=health_status,
            checked_at=report.reported_at,
            component_total=component_total,
            healthy_components=healthy_components,
            degraded_components=degraded_components,
            offline_components=offline_components,
        )

    async def _apply_command(self, command: DeviceConfigCommandRecord) -> str:
        """Apply a command locally or forward it to the local MQTT broker.

        :param command: Backend command record to execute.
        :return: Human-readable execution detail for backend result storage.
        :raises ValueError: If a gateway-targeted command is not for this gateway.
        """
        if command.device_type == "gateway":
            if command.device_id != self._settings.gateway_id:
                raise ValueError("gateway config command target does not match current gateway")
            self._runtime_config_manager.update_from_gateway_config(command.payload)
            return "gateway config applied locally"

        await self._mqtt_publisher.publish_json(
            topic=command.topic,
            payload=self._build_device_config_payload(command),
            qos=command.qos,
            retain=False,
        )
        return "forwarded to local mqtt broker"

    def _build_device_config_payload(self, command: DeviceConfigCommandRecord) -> dict[str, Any]:
        """Build a schema-compliant device config MQTT payload."""
        payload = dict(command.payload)
        payload["ts"] = int(datetime.now(UTC).timestamp())
        payload["published_by"] = EDGE_INTERNAL_PUBLISHER

        self._validate_device_config_payload(command.device_type, payload)
        if command.device_type == "wristband":
            low = payload["hr_alert_threshold_low"]
            high = payload["hr_alert_threshold_high"]
            if low >= high:
                raise ValueError("hr_alert_threshold_low must be less than hr_alert_threshold_high")
        return payload

    def _validate_device_config_payload(self, device_type: str, payload: dict[str, Any]) -> None:
        """Validate device config commands before publishing them to MQTT.

        :param device_type: Target device type from the backend command.
        :param payload: Config payload after gateway outbound enrichment.
        :return: None.
        :raises ValueError: If required schema fields are missing or invalid.
        """
        required_fields = DEVICE_CONFIG_REQUIRED_FIELDS.get(device_type)
        if required_fields is None:
            raise ValueError(f"unsupported device config target type: {device_type}")

        for field_name, expected_type in required_fields.items():
            if field_name not in payload:
                raise ValueError(f"{device_type} config requires field: {field_name}")
            value = payload[field_name]
            if isinstance(value, bool) and expected_type is not bool:
                raise ValueError(f"{device_type} config field {field_name} has invalid type")
            if not isinstance(value, expected_type):
                raise ValueError(f"{device_type} config field {field_name} has invalid type")

    async def _flush_command_results(self) -> None:
        """Retry all cached command results that were not yet reported."""
        for command_id in list(self._command_result_cache.keys()):
            await self._flush_command_result(command_id)

    async def _flush_command_result(self, command_id: str) -> None:
        """Report one cached command result if it exists.

        :param command_id: Command id stored in the local result cache.
        """
        result = self._command_result_cache.get(command_id)
        if result is None:
            return

        try:
            await self._backend_client.report_command_result(command_id=command_id, result=result)
        except Exception:
            LOGGER.exception(
                "failed to report gateway command result",
                extra={"gateway_id": self._settings.gateway_id, "command_id": command_id},
            )
            return

        self._command_result_cache.pop(command_id, None)

    async def _wake_command_fetch(self) -> None:
        """Wake the command polling loop after a WebSocket notification."""
        self._command_wakeup_event.set()
