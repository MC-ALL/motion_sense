import asyncio

import pytest

from app.models.device_command import DeviceConfigCommandRecord, GatewayCommandResultRequest
from app.services.device_presence import DeviceIdentity, DeviceTransition
from app.services.rule_engine import EmittedAlert
from app.services.runner import EdgeProcessorRunner
from app.settings import RuntimeSettings
from app.utils.topic_parser import parse_topic


class FakeBackendClient:
    """Backend client fake that records reported command results."""

    def __init__(self) -> None:
        """Initialize captured result reports.

        :return: None.
        """
        self.reported: list[tuple[str, GatewayCommandResultRequest]] = []

    async def report_command_result(
        self,
        *,
        command_id: str,
        result: GatewayCommandResultRequest,
    ) -> DeviceConfigCommandRecord:
        """Capture a command result and return the backend's updated record.

        :param command_id: Command ID reported by the runner.
        :param result: Result payload generated after command execution.
        :return: Updated command record mirroring backend API behavior.
        """
        self.reported.append((command_id, result))
        return DeviceConfigCommandRecord(
            command_id=command_id,
            gateway_id="gw-test-001",
            device_id="env-a",
            gym_id="gym-gz-01",
            device_type="env",
            topic="gym/gym-gz-01/env/env-a/config",
            qos=1,
            retain=False,
            payload={},
            status=result.status,
            attempt_count=1,
            max_attempts=3,
            retry_backoff_s=5,
            last_attempt_at="2026-04-15T08:00:01Z",
            next_retry_at=None,
            leased_until=None,
            expires_at="2026-04-15T08:05:00Z",
            created_at="2026-04-15T08:00:00Z",
            updated_at=result.reported_at,
            result_detail=result.detail,
            result_payload=result.result_payload,
        )


class FakeMqttPublisher:
    """MQTT publisher fake that records outbound device config messages."""

    def __init__(self) -> None:
        """Initialize captured MQTT publishes.

        :return: None.
        """
        self.messages: list[dict[str, object]] = []

    async def publish_json(
        self,
        *,
        topic: str,
        payload: dict[str, object],
        qos: int,
        retain: bool,
    ) -> None:
        """Record one JSON publish request.

        :param topic: MQTT topic used by the runner.
        :param payload: JSON payload sent to the device.
        :param qos: MQTT QoS selected by the command record.
        :param retain: MQTT retained flag selected by the command record.
        :return: None.
        """
        self.messages.append(
            {
                "topic": topic,
                "payload": payload,
                "qos": qos,
                "retain": retain,
            }
        )


class FakeEventBuffer:
    """Event buffer fake that records generated events."""

    def __init__(self) -> None:
        """Initialize captured events."""
        self.items: list[tuple[object, object]] = []

    async def append(self, item, parsed_topic) -> None:
        """Record one append call."""
        self.items.append((item, parsed_topic))


class FakeRuntimeConfigManager:
    """Runtime config fake that records gateway configuration payloads."""

    def __init__(self) -> None:
        """Initialize captured config updates.

        :return: None.
        """
        self.payloads: list[dict[str, object]] = []

    def update_from_gateway_config(self, payload: dict[str, object]) -> None:
        """Record a gateway runtime config update.

        :param payload: Config payload applied by a gateway command.
        :return: None.
        """
        self.payloads.append(payload)


class FakeGatewayCommandChannel:
    """Gateway command channel fake that invokes the wake callback once."""

    def __init__(self) -> None:
        """Initialize listen-call counter.

        :return: None.
        """
        self.listen_calls = 0

    async def listen(self, on_command_ready) -> None:
        """Invoke the runner wake callback then simulate channel closure.

        :param on_command_ready: Callback passed by the runner when commands
            are available.
        :return: None.
        :raises RuntimeError: Always, to end this test channel loop.
        """
        self.listen_calls += 1
        await on_command_ready()
        raise RuntimeError("channel closed")


def test_runner_executes_gateway_and_device_commands() -> None:
    """Verify runner command execution for gateway and device targets.

    :return: None. Assertions confirm gateway configs are applied locally,
        device configs are published to MQTT, and results flush to backend.
    """
    settings = RuntimeSettings(gateway_id="gw-test-001")
    runner = EdgeProcessorRunner(settings)
    asyncio.run(runner._backend_client.close())
    asyncio.run(runner._health_reporter.close())

    fake_backend = FakeBackendClient()
    fake_mqtt = FakeMqttPublisher()
    fake_runtime_config = FakeRuntimeConfigManager()
    runner._backend_client = fake_backend
    runner._mqtt_publisher = fake_mqtt
    runner._runtime_config_manager = fake_runtime_config

    gateway_command = DeviceConfigCommandRecord(
        command_id="cmd-gateway",
        gateway_id="gw-test-001",
        device_id="gw-test-001",
        gym_id="gym-gz-01",
        device_type="gateway",
        topic="gym/gym-gz-01/gateway/gw-test-001/config",
        qos=1,
        retain=False,
        payload={"alert_rules": {"DEVICE_OFFLINE": {"enabled": True}}},
        status="pending",
        attempt_count=1,
        max_attempts=3,
        retry_backoff_s=5,
        last_attempt_at="2026-04-15T08:00:01Z",
        next_retry_at="2026-04-15T08:00:00Z",
        leased_until="2026-04-15T08:00:16Z",
        expires_at="2026-04-15T08:05:00Z",
        created_at="2026-04-15T08:00:00Z",
        updated_at="2026-04-15T08:00:00Z",
    )
    device_command = DeviceConfigCommandRecord(
        command_id="cmd-device",
        gateway_id="gw-test-001",
        device_id="env-a",
        gym_id="gym-gz-01",
        device_type="env",
        topic="gym/gym-gz-01/env/env-a/config",
        qos=1,
        retain=False,
        payload={
            "telemetry_interval_s": 20,
            "co2_threshold_ppm": 1200,
            "pm25_threshold_ugm3": 75,
        },
        status="pending",
        attempt_count=1,
        max_attempts=3,
        retry_backoff_s=5,
        last_attempt_at="2026-04-15T08:01:01Z",
        next_retry_at="2026-04-15T08:01:00Z",
        leased_until="2026-04-15T08:01:16Z",
        expires_at="2026-04-15T08:06:00Z",
        created_at="2026-04-15T08:01:00Z",
        updated_at="2026-04-15T08:01:00Z",
    )

    async def scenario() -> None:
        """Execute sample commands and flush cached results.

        :return: None.
        """
        gateway_result = await runner._execute_command(gateway_command)
        assert gateway_result.status == "succeeded"
        assert fake_runtime_config.payloads[0]["alert_rules"]["DEVICE_OFFLINE"]["enabled"] is True

        device_result = await runner._execute_command(device_command)
        assert device_result.status == "succeeded"
        assert fake_mqtt.messages[0]["topic"] == "gym/gym-gz-01/env/env-a/config"
        assert fake_mqtt.messages[0]["retain"] is False
        payload = fake_mqtt.messages[0]["payload"]
        assert isinstance(payload["ts"], int)
        assert payload["published_by"] == "edge_processor"

        runner._command_result_cache[gateway_command.command_id] = gateway_result
        runner._command_result_cache[device_command.command_id] = device_result
        await runner._flush_command_results()

        assert len(fake_backend.reported) == 2
        assert runner._command_result_cache == {}

    asyncio.run(scenario())


def test_runner_rejects_invalid_wristband_config_thresholds() -> None:
    """Verify wristband config commands enforce threshold ordering."""
    settings = RuntimeSettings(gateway_id="gw-test-001")
    runner = EdgeProcessorRunner(settings)
    asyncio.run(runner._backend_client.close())
    asyncio.run(runner._health_reporter.close())

    command = DeviceConfigCommandRecord(
        command_id="cmd-wristband",
        gateway_id="gw-test-001",
        device_id="wb-a",
        gym_id="gym-gz-01",
        device_type="wristband",
        topic="gym/gym-gz-01/wristband/wb-a/config",
        qos=1,
        retain=True,
        payload={
            "hr_alert_threshold_high": 80,
            "hr_alert_threshold_low": 90,
            "notify_interval_ms": 500,
            "fall_detect_enabled": True,
        },
        status="pending",
        attempt_count=1,
        max_attempts=3,
        retry_backoff_s=5,
        last_attempt_at=None,
        next_retry_at=None,
        leased_until=None,
        expires_at="2026-04-15T08:06:00Z",
        created_at="2026-04-15T08:01:00Z",
        updated_at="2026-04-15T08:01:00Z",
    )

    async def scenario() -> None:
        with pytest.raises(ValueError, match="hr_alert_threshold_low"):
            await runner._apply_command(command)

    asyncio.run(scenario())


def test_runner_rejects_incomplete_device_config() -> None:
    """Verify device config commands must carry the full schema payload."""
    settings = RuntimeSettings(gateway_id="gw-test-001")
    runner = EdgeProcessorRunner(settings)
    asyncio.run(runner._backend_client.close())
    asyncio.run(runner._health_reporter.close())

    command = DeviceConfigCommandRecord(
        command_id="cmd-env-incomplete",
        gateway_id="gw-test-001",
        device_id="env-a",
        gym_id="gym-gz-01",
        device_type="env",
        topic="gym/gym-gz-01/env/env-a/config",
        qos=1,
        retain=True,
        payload={"telemetry_interval_s": 20},
        status="pending",
        attempt_count=1,
        max_attempts=3,
        retry_backoff_s=5,
        last_attempt_at=None,
        next_retry_at=None,
        leased_until=None,
        expires_at="2026-04-15T08:06:00Z",
        created_at="2026-04-15T08:01:00Z",
        updated_at="2026-04-15T08:01:00Z",
    )

    async def scenario() -> None:
        with pytest.raises(ValueError, match="co2_threshold_ppm"):
            await runner._apply_command(command)

    asyncio.run(scenario())


def test_runner_emits_schema_compliant_offline_events() -> None:
    """Verify generated offline alert and status payloads match MQTT schema."""
    settings = RuntimeSettings(gateway_id="gw-test-001")
    runner = EdgeProcessorRunner(settings)
    asyncio.run(runner._backend_client.close())
    asyncio.run(runner._health_reporter.close())

    fake_mqtt = FakeMqttPublisher()
    fake_buffer = FakeEventBuffer()
    runner._mqtt_publisher = fake_mqtt
    runner._event_buffer = fake_buffer

    transition = DeviceTransition(
        identity=DeviceIdentity("gym-gz-01", "equipment", "eq-001"),
        observed_at_s=1712640090,
    )
    rule = runner._rule_engine.device_offline_rule()

    async def scenario() -> None:
        await runner._emit_offline_events(transition, rule)

    asyncio.run(scenario())

    assert fake_mqtt.messages[0]["payload"] == {
        "ts": 1712640090,
        "priority": "P1",
        "level": "warning",
        "alert_type": "device_offline",
        "message": "device offline: no heartbeat for 30s",
        "published_by": "edge_processor",
    }
    assert fake_mqtt.messages[1]["payload"] == {
        "ts": 1712640090,
        "status": "offline",
        "firmware_version": "edge-generated",
        "mac": "00:00:00:00:00:00",
        "published_by": "edge_processor",
    }


def test_runner_emits_schema_compliant_rule_alert() -> None:
    """Verify rule-generated alerts publish alert_type and internal marker."""
    settings = RuntimeSettings(gateway_id="gw-test-001")
    runner = EdgeProcessorRunner(settings)
    asyncio.run(runner._backend_client.close())
    asyncio.run(runner._health_reporter.close())

    fake_mqtt = FakeMqttPublisher()
    fake_buffer = FakeEventBuffer()
    runner._mqtt_publisher = fake_mqtt
    runner._event_buffer = fake_buffer
    alert = EmittedAlert(
        gym_id="gym-gz-01",
        device_type="env",
        device_id="env-001",
        alert_type="co2_critical",
        level="warning",
        value=1800,
        threshold=1500,
        observed_at_s=1712640090,
        message="CO2_CRITICAL triggered",
    )

    async def scenario() -> None:
        await runner._emit_rule_alert(alert)

    asyncio.run(scenario())

    assert fake_mqtt.messages[0]["payload"] == {
        "ts": 1712640090,
        "priority": "P0",
        "level": "critical",
        "alert_type": "co2_critical",
        "message": "CO2_CRITICAL triggered",
        "value": 1800,
        "threshold": 1500,
        "published_by": "edge_processor",
    }


def test_runner_does_not_publish_recovery_status() -> None:
    """Verify device recovery only updates presence and does not publish status."""
    settings = RuntimeSettings(gateway_id="gw-test-001")
    runner = EdgeProcessorRunner(settings)
    asyncio.run(runner._backend_client.close())
    asyncio.run(runner._health_reporter.close())

    fake_mqtt = FakeMqttPublisher()
    fake_buffer = FakeEventBuffer()
    runner._mqtt_publisher = fake_mqtt
    runner._event_buffer = fake_buffer
    topic = parse_topic("gym/gym-gz-01/equipment/eq-001/telemetry")
    runner._device_presence_tracker.mark_seen(topic, {"ts": 100}, now_s=100)
    assert runner._device_presence_tracker.collect_new_offline(timeout_s=30, now_s=131)

    async def scenario() -> None:
        await runner._on_ingest_event(topic, {"ts": 151, "power_w": 90.0})

    asyncio.run(scenario())

    assert fake_mqtt.messages == []


def test_runner_gateway_command_channel_wakes_poll_loop() -> None:
    """Verify the command WebSocket channel wakes the pending poll loop.

    :return: None. Assertions confirm the wake event is set after the fake
        channel receives ``command_ready``.
    """
    settings = RuntimeSettings(gateway_id="gw-test-001")
    runner = EdgeProcessorRunner(settings)
    asyncio.run(runner._backend_client.close())
    asyncio.run(runner._health_reporter.close())

    runner._gateway_command_channel = FakeGatewayCommandChannel()

    async def scenario() -> None:
        """Run the command channel loop until the wake callback fires.

        :return: None.
        """
        runner._command_wakeup_event.clear()
        task = asyncio.create_task(runner._command_channel_loop())
        await asyncio.sleep(0)
        assert runner._command_wakeup_event.is_set() is True
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())
