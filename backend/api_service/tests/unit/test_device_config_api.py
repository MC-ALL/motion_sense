from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.device_config_service import DeviceConfigService


class FakeConfigPublisher:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def publish(
        self,
        *,
        topic: str,
        payload: dict[str, Any],
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


def _install_fake_config_service(client: TestClient) -> FakeConfigPublisher:
    fake_publisher = FakeConfigPublisher()
    client.app.state.device_config_service = DeviceConfigService(
        store=client.app.state.event_store,
        publisher=fake_publisher,
        topic_prefix="gym",
        default_qos=1,
        default_retain=False,
    )
    return fake_publisher


def test_publish_device_config_from_existing_device_snapshot() -> None:
    with TestClient(create_app()) as client:
        fake_publisher = _install_fake_config_service(client)
        ingest_response = client.post(
            "/api/v1/ingest/batch",
            json={
                "gateway_id": "gw-001",
                "sent_at": "2026-04-14T17:00:00Z",
                "items": [
                    {
                        "kind": "telemetry",
                        "topic": "gym/gym-gz-01/equipment/eq-001/telemetry",
                        "payload": {"ts": 1712355600, "device_id": "eq-001"},
                    }
                ],
            },
        )
        assert ingest_response.status_code == 200

        response = client.post(
            "/api/v1/devices/eq-001/config",
            json={"config": {"target_reps": 15}},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["topic"] == "gym/gym-gz-01/equipment/eq-001/config"
        assert body["payload"]["target_reps"] == 15
        assert isinstance(body["payload"]["ts"], int)
        assert fake_publisher.messages[0]["topic"] == body["topic"]
        assert fake_publisher.messages[0]["qos"] == 1
        assert fake_publisher.messages[0]["retain"] is False


def test_publish_device_config_supports_explicit_gateway_target() -> None:
    with TestClient(create_app()) as client:
        fake_publisher = _install_fake_config_service(client)
        response = client.post(
            "/api/v1/devices/gw-001/config",
            json={
                "gym_id": "gym-gz-01",
                "device_type": "gateway",
                "config": {"batch_interval_s": 5},
                "qos": 1,
                "retain": False,
            },
        )
        assert response.status_code == 200
        assert response.json()["topic"] == "gym/gym-gz-01/gateway/gw-001/config"
        assert fake_publisher.messages[0]["payload"]["batch_interval_s"] == 5


def test_publish_device_config_requires_target_resolution() -> None:
    with TestClient(create_app()) as client:
        _install_fake_config_service(client)
        response = client.post(
            "/api/v1/devices/eq-999/config",
            json={"config": {"target_reps": 12}},
        )
        assert response.status_code == 404
        assert "device snapshot not found" in response.json()["detail"]


def test_publish_device_config_returns_503_when_mqtt_backend_disabled() -> None:
    with TestClient(create_app()) as client:
        ingest_response = client.post(
            "/api/v1/ingest/batch",
            json={
                "gateway_id": "gw-001",
                "sent_at": "2026-04-14T17:05:00Z",
                "items": [
                    {
                        "kind": "telemetry",
                        "topic": "gym/gym-gz-01/env/env-a/telemetry",
                        "payload": {"ts": 1712355900},
                    }
                ],
            },
        )
        assert ingest_response.status_code == 200

        response = client.post(
            "/api/v1/devices/env-a/config",
            json={"config": {"telemetry_interval_s": 20}},
        )
        assert response.status_code == 503
