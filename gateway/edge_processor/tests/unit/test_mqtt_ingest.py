import asyncio
from dataclasses import dataclass

import pytest

from app.services import mqtt_ingest as mqtt_ingest_module
from app.services.mqtt_ingest import _is_internal_edge_event, mqtt_ingest_loop
from app.settings import RuntimeSettings
from app.utils.topic_parser import parse_topic


def test_internal_edge_alert_or_status_is_ignored() -> None:
    """Verify edge-generated alert/status messages are not re-ingested.

    :return: None. Assertions cover internal alert/status suppression while
        allowing telemetry and device-originated alerts.
    """
    alert_topic = parse_topic("gym/gym-gz-01/equipment/eq-001/alert")
    status_topic = parse_topic("gym/gym-gz-01/equipment/eq-001/status")
    telemetry_topic = parse_topic("gym/gym-gz-01/equipment/eq-001/telemetry")

    assert _is_internal_edge_event(alert_topic, {"published_by": "edge_processor"}) is True
    assert _is_internal_edge_event(status_topic, {"published_by": "edge_processor"}) is True
    assert _is_internal_edge_event(telemetry_topic, {"published_by": "edge_processor"}) is False
    assert _is_internal_edge_event(alert_topic, {"published_by": "device"}) is False


@dataclass
class _FakeMessage:
    """MQTT message fake with only the fields consumed by the ingest loop."""

    topic: str
    payload: bytes


class _FakeMessages:
    """Async iterator fake that yields messages then cancels the loop."""

    def __init__(self, items: list[_FakeMessage]) -> None:
        """Store messages that should be yielded to the ingest loop.

        :param items: MQTT messages returned by successive ``__anext__`` calls.
        :return: None.
        """
        self._items = list(items)

    def __aiter__(self) -> "_FakeMessages":
        """Return the iterator itself.

        :return: Async iterator used by ``async for`` in the ingest loop.
        """
        return self

    async def __anext__(self) -> _FakeMessage:
        """Return the next fake message or stop the test loop.

        :return: Next MQTT message.
        :raises asyncio.CancelledError: When all fake messages have been
            consumed, allowing the test to exit the infinite loop.
        """
        if self._items:
            return self._items.pop(0)
        raise asyncio.CancelledError


class _FakeClient:
    """aiomqtt client fake used to test reconnect and subscribe behavior."""

    def __init__(self, *, fail_on_enter: bool = False) -> None:
        """Create a fake MQTT client.

        :param fail_on_enter: When true, entering the async context raises a
            connection failure.
        :return: None.
        """
        self._fail_on_enter = fail_on_enter
        self.subscriptions: list[tuple[str, int]] = []
        self.messages = _FakeMessages(
            [
                _FakeMessage(
                    topic="gym/gym-gz-01/equipment/eq-001/telemetry",
                    payload=b'{"ts": 1712640000, "power_w": 320.5}',
                )
            ]
        )

    async def __aenter__(self) -> "_FakeClient":
        """Enter the fake MQTT connection.

        :return: Connected fake client.
        :raises RuntimeError: If this instance is configured to fail connect.
        """
        if self._fail_on_enter:
            raise RuntimeError("mqtt connect failed")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        """Leave the fake MQTT connection.

        :param exc_type: Exception type from the async context, if any.
        :param exc: Exception instance from the async context, if any.
        :param tb: Traceback from the async context, if any.
        :return: ``False`` so exceptions propagate normally.
        """
        return False

    async def subscribe(self, topic: str, qos: int) -> None:
        """Record a subscription request.

        :param topic: MQTT topic filter requested by the ingest loop.
        :param qos: QoS value requested for the subscription.
        :return: None.
        """
        self.subscriptions.append((topic, qos))


class _FakeEventBuffer:
    """Event buffer fake that records appended ingest items."""

    def __init__(self) -> None:
        """Initialize captured append calls.

        :return: None.
        """
        self.items: list[tuple[object, object]] = []

    async def append(self, item, parsed_topic) -> None:
        """Record an ingest append operation.

        :param item: Ingest item produced by the MQTT ingest loop.
        :param parsed_topic: Parsed topic attached to the ingest item.
        :return: None.
        """
        self.items.append((item, parsed_topic))


class _FakeRuntimeConfigManager:
    """Runtime config fake that fails if gateway config is unexpectedly parsed."""

    def update_from_gateway_config(self, payload) -> None:
        """Reject unexpected gateway config updates.

        :param payload: Gateway config payload passed by the ingest loop.
        :return: None.
        :raises AssertionError: Always, because this test uses telemetry only.
        """
        raise AssertionError("gateway config topic should not be hit in this scenario")


def test_mqtt_ingest_loop_retries_and_resubscribes(monkeypatch) -> None:
    """Verify MQTT ingest reconnects, resubscribes, and records telemetry.

    :param monkeypatch: Pytest fixture used to replace aiomqtt client, sleep,
        and time source.
    :return: None. Assertions validate retry count, subscriptions, buffered
        event count, and injected gateway receive timestamp.
    """
    settings = RuntimeSettings()
    event_buffer = _FakeEventBuffer()
    runtime_config_manager = _FakeRuntimeConfigManager()
    received: list[tuple[str, dict]] = []
    sleep_calls: list[int] = []
    client_instances: list[_FakeClient] = []
    attempts = {"count": 0}

    def fake_client_factory(**kwargs) -> _FakeClient:
        """Create fake MQTT clients, failing the first connection attempt.

        :param kwargs: aiomqtt constructor options supplied by the ingest loop.
        :return: Fake client for this connection attempt.
        """
        del kwargs
        attempts["count"] += 1
        client = _FakeClient(fail_on_enter=attempts["count"] == 1)
        client_instances.append(client)
        return client

    async def fake_sleep(seconds: int) -> None:
        """Record retry sleep duration without delaying the test.

        :param seconds: Requested retry delay.
        :return: None.
        """
        sleep_calls.append(seconds)

    async def on_event_received(parsed_topic, payload) -> None:
        """Capture received telemetry callback payloads.

        :param parsed_topic: Parsed topic associated with the MQTT message.
        :param payload: JSON payload after ingest-loop enrichment.
        :return: None.
        """
        received.append((parsed_topic.device_id, payload))

    monkeypatch.setattr(mqtt_ingest_module, "Client", fake_client_factory)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(mqtt_ingest_module.time, "time", lambda: 1712640009)

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
    assert received == [("eq-001", {"ts": 1712640000, "power_w": 320.5, "gateway_received_ts": 1712640009})]
