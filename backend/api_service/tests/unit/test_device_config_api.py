from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_create_device_config_command_for_existing_device() -> None:
    with TestClient(create_app()) as client:
        ingest_response = client.post(
            "/api/v1/ingest/batch",
            json={
                "gateway_id": "gw-001",
                "sent_at": "2026-04-14T17:00:00Z",
                "items": [
                    {
                        "kind": "telemetry",
                        "topic": "gym/gym-gz-01/equipment/eq-001/telemetry",
                        "payload": {
                            "ts": 1712355600,
                            "device_id": "eq-001",
                            "gateway_id": "gw-001",
                        },
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
        assert body["gateway_id"] == "gw-001"
        assert body["gym_id"] == "gym-gz-01"
        assert body["device_type"] == "equipment"
        assert body["topic"] == "gym/gym-gz-01/equipment/eq-001/config"
        assert body["payload"]["target_reps"] == 15
        assert body["status"] == "pending"
        assert isinstance(body["command_id"], str)
        assert isinstance(body["payload"]["ts"], int)


def test_create_gateway_config_command_uses_gateway_device_id() -> None:
    with TestClient(create_app()) as client:
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
        body = response.json()
        assert body["gateway_id"] == "gw-001"
        assert body["topic"] == "gym/gym-gz-01/gateway/gw-001/config"
        assert body["payload"]["batch_interval_s"] == 5


def test_create_non_gateway_command_requires_gateway_id() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/devices/eq-999/config",
            json={
                "gym_id": "gym-gz-01",
                "device_type": "equipment",
                "config": {"target_reps": 12},
            },
        )

        assert response.status_code == 404
        assert "gateway_id is required" in response.json()["detail"]


def test_gateway_can_list_pending_commands_and_report_result() -> None:
    with TestClient(create_app()) as client:
        create_response = client.post(
            "/api/v1/devices/env-a/config",
            json={
                "gym_id": "gym-gz-01",
                "gateway_id": "gw-002",
                "device_type": "env",
                "config": {"telemetry_interval_s": 20},
            },
        )
        assert create_response.status_code == 200
        command_id = create_response.json()["command_id"]

        pending_response = client.get("/api/v1/gateway/gw-002/commands/pending")
        assert pending_response.status_code == 200
        pending_body = pending_response.json()
        assert pending_body["gateway_id"] == "gw-002"
        assert len(pending_body["items"]) == 1
        assert pending_body["items"][0]["command_id"] == command_id

        result_response = client.post(
            f"/api/v1/gateway/gw-002/commands/{command_id}/result",
            json={
                "status": "succeeded",
                "reported_at": "2026-04-15T09:00:00Z",
                "detail": "applied",
                "result_payload": {"applied": True},
            },
        )
        assert result_response.status_code == 200
        assert result_response.json()["status"] == "succeeded"
        assert result_response.json()["result_payload"]["applied"] is True

        pending_after_response = client.get("/api/v1/gateway/gw-002/commands/pending")
        assert pending_after_response.status_code == 200
        assert pending_after_response.json()["items"] == []

        detail_response = client.get(f"/api/v1/gateway/commands/{command_id}")
        assert detail_response.status_code == 200
        assert detail_response.json()["result_detail"] == "applied"


def test_gateway_result_rejects_wrong_gateway() -> None:
    with TestClient(create_app()) as client:
        create_response = client.post(
            "/api/v1/devices/env-a/config",
            json={
                "gym_id": "gym-gz-01",
                "gateway_id": "gw-002",
                "device_type": "env",
                "config": {"telemetry_interval_s": 20},
            },
        )
        assert create_response.status_code == 200
        command_id = create_response.json()["command_id"]

        result_response = client.post(
            f"/api/v1/gateway/gw-003/commands/{command_id}/result",
            json={
                "status": "failed",
                "reported_at": "2026-04-15T09:00:00Z",
                "detail": "wrong gateway",
            },
        )

        assert result_response.status_code == 409
        assert "does not belong to this gateway" in result_response.json()["detail"]
