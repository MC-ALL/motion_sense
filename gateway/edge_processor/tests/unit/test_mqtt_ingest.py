import asyncio
from dataclasses import dataclass

import pytest

from app.services import mqtt_ingest as mqtt_ingest_module
from app.services.mqtt_ingest import _is_internal_edge_event, mqtt_ingest_loop
from app.settings import RuntimeSettings
from app.utils.topic_parser import parse_topic


def test_internal_edge_alert_or_status_is_ignored() -> None:
    alert_topic = parse_topic("gym/gym-gz-01/equipment/eq-001/alert")
    status_topic = parse_topic("gym/gym-gz-01/equipment/eq-001/status")
    telemetry_topic = parse_topic("gym/gym-gz-01/equipment/eq-001/telemetry")

    assert _is_internal_edge_event(alert_topic, {"source": "edge_processor"}) is True
    assert _is_internal_edge_event(status_topic, {"source": "edge_processor"}) is True
    assert _is_internal_edge_event(telemetry_topic, {"source": "edge_processor"}) is False
    assert _is_internal_edge_event(alert_topic, {"source": "device"}) is False


@dataclass
class _FakeMessage:
    topic: str
    payload: bytes


class _FakeMessages:
    def __init__(self, items: list[_FakeMessage]) -> None:
        self._items = list(items)

    def __aiter__(self) -> "_FakeMessages":
        return self

    async def __anext__(self) -> _FakeMessage:
        if self._items:
            return self._items.pop(0)
        raise asyncio.CancelledError


class _FakeClient:
    def __init__(self, *, fail_on_enter: bool = False) -> None:
        self._fail_on_enter = fail_on_enter
        self.subscriptions: list[tuple[str, int]] = []
        self.messages = _FakeMessages(
            [_FakeMessage(topic="gym/gym-gz-01/equipment/eq-001/telemetry", payload=b'{"ts": 1712640000, "power_w": 320.5}')]
        )

    async def __aenter__(self) -> "_FakeClient":
        if self._fail_on_enter:
            raise RuntimeError("mqtt connect failed")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def subscribe(self, topic: str, qos: int) -> None:
        self.subscriptions.append((topic, qos))


class _FakeEventBuffer:
    def __init__(self) -> None:
        self.items: list[tuple[object, object]] = []

    async def append(self, item, parsed_topic) -> None:
        self.items.append((item, parsed_topic))


class _FakeRuntimeConfigManager:
    def update_from_gateway_config(self, payload) -> None:
        raise AssertionError("gateway config topic should not be hit in this scenario")


def test_mqtt_ingest_loop_retries_and_resubscribes(monkeypatch) -> None:
    settings = RuntimeSettings()
    event_buffer = _FakeEventBuffer()
    runtime_config_manager = _FakeRuntimeConfigManager()
    received: list[tuple[str, dict]] = []
    sleep_calls: list[int] = []
    client_instances: list[_FakeClient] = []
    attempts = {"count": 0}

    def fake_client_factory(**kwargs) -> _FakeClient:
        attempts["count"] += 1
        client = _FakeClient(fail_on_enter=attempts["count"] == 1)
        client_instances.append(client)
        return client

    async def fake_sleep(seconds: int) -> None:
        sleep_calls.append(seconds)

    async def on_event_received(parsed_topic, payload) -> None:
        received.append((parsed_topic.device_id, payload))

    monkeypatch.setattr(mqtt_ingest_module, "Client", fake_client_factory)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            mqtt_ingest_loop(
                settings,
                event_buffer,
                runtime_config_manager,
                on_event_received=on_event_received,
            )
        )

    assert attempts["count"] == 2
    assert sleep_calls == [3]
    assert client_instances[1].subscriptions == [(topic, settings.mqtt.qos) for topic in settings.mqtt.topic_patterns]
    assert len(event_buffer.items) == 1
    assert received == [("eq-001", {"ts": 1712640000, "power_w": 320.5})]
