import asyncio

from app.models.device_command import DeviceConfigCommandRecord, GatewayCommandResultRequest
from app.services.runner import EdgeProcessorRunner
from app.settings import RuntimeSettings


class FakeBackendClient:
    def __init__(self) -> None:
        self.reported: list[tuple[str, GatewayCommandResultRequest]] = []

    async def report_command_result(
        self,
        *,
        command_id: str,
        result: GatewayCommandResultRequest,
    ) -> DeviceConfigCommandRecord:
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
            created_at="2026-04-15T08:00:00Z",
            updated_at=result.reported_at,
            result_detail=result.detail,
            result_payload=result.result_payload,
        )


class FakeMqttPublisher:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def publish_json(
        self,
        *,
        topic: str,
        payload: dict[str, object],
        qos: int,
        retain: bool,
    ) -> None:
        self.messages.append(
            {
                "topic": topic,
                "payload": payload,
                "qos": qos,
                "retain": retain,
            }
        )


class FakeRuntimeConfigManager:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def update_from_gateway_config(self, payload: dict[str, object]) -> None:
        self.payloads.append(payload)


def test_runner_executes_gateway_and_device_commands() -> None:
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
        payload={"telemetry_interval_s": 20},
        status="pending",
        created_at="2026-04-15T08:01:00Z",
        updated_at="2026-04-15T08:01:00Z",
    )

    async def scenario() -> None:
        gateway_result = await runner._execute_command(gateway_command)
        assert gateway_result.status == "succeeded"
        assert fake_runtime_config.payloads[0]["alert_rules"]["DEVICE_OFFLINE"]["enabled"] is True

        device_result = await runner._execute_command(device_command)
        assert device_result.status == "succeeded"
        assert fake_mqtt.messages[0]["topic"] == "gym/gym-gz-01/env/env-a/config"

        runner._command_result_cache[gateway_command.command_id] = gateway_result
        runner._command_result_cache[device_command.command_id] = device_result
        await runner._flush_command_results()

        assert len(fake_backend.reported) == 2
        assert runner._command_result_cache == {}

    asyncio.run(scenario())
