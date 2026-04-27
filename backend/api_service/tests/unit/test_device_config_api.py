from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from app.settings import RuntimeSettings


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
        assert body["attempt_count"] == 0
        assert body["max_attempts"] == 3
        assert body["retry_backoff_s"] == 5
        assert body["last_attempt_at"] is None
        assert body["leased_until"] is None
        assert body["next_retry_at"] is not None
        assert body["expires_at"] is not None
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
        create_body = create_response.json()
        command_id = create_body["command_id"]
        first_reported_at = (
            datetime.fromisoformat(create_body["created_at"].replace("Z", "+00:00"))
            + timedelta(seconds=1)
        ).isoformat()
        second_reported_at = (
            datetime.fromisoformat(create_body["created_at"].replace("Z", "+00:00"))
            + timedelta(seconds=2)
        ).isoformat()

        pending_response = client.get("/api/v1/gateway/gw-002/commands/pending")
        assert pending_response.status_code == 200
        pending_body = pending_response.json()
        assert pending_body["gateway_id"] == "gw-002"
        assert len(pending_body["items"]) == 1
        assert pending_body["items"][0]["command_id"] == command_id
        assert pending_body["items"][0]["attempt_count"] == 1
        assert pending_body["items"][0]["last_attempt_at"] is not None
        assert pending_body["items"][0]["leased_until"] is not None

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
        assert detail_response.json()["next_retry_at"] is None


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


def test_gateway_command_websocket_receives_ready_event_for_matching_gateway() -> None:
    settings = RuntimeSettings(
        device_command={
            "gateway_channel_token": "gateway-command-token",
        }
    )

    with TestClient(create_app(settings)) as client:
        with client.websocket_connect(
            "/api/v1/gateway/gw-002/commands/ws?token=gateway-command-token"
        ) as websocket:
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

            ready_message = websocket.receive_json()
            assert ready_message == {
                "type": "command_ready",
                "data": {
                    "gateway_id": "gw-002",
                    "command_id": command_id,
                    "device_id": "env-a",
                    "device_type": "env",
                    "issued_at": create_response.json()["created_at"],
                },
            }


def test_gateway_command_websocket_rejects_invalid_token() -> None:
    settings = RuntimeSettings(
        device_command={
            "gateway_channel_token": "gateway-command-token",
        }
    )

    with TestClient(create_app(settings)) as client:
        try:
            with client.websocket_connect("/api/v1/gateway/gw-002/commands/ws?token=invalid"):
                pass
        except WebSocketDisconnect as exc:
            assert exc.code == 1008
        else:
            raise AssertionError("expected websocket connection to be rejected")


def test_failed_command_requeues_before_reaching_max_attempts() -> None:
    settings = RuntimeSettings(
        device_command={
            "max_attempts": 2,
            "retry_backoff_s": 0,
            "delivery_lease_s": 15,
            "expire_after_s": 300,
        }
    )

    with TestClient(create_app(settings)) as client:
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
        create_body = create_response.json()
        command_id = create_body["command_id"]
        first_reported_at = create_body["created_at"]
        second_reported_at = create_body["created_at"]

        first_pending = client.get("/api/v1/gateway/gw-002/commands/pending")
        assert first_pending.status_code == 200
        assert first_pending.json()["items"][0]["attempt_count"] == 1

        first_failed = client.post(
            f"/api/v1/gateway/gw-002/commands/{command_id}/result",
            json={
                "status": "failed",
                "reported_at": first_reported_at,
                "detail": "mqtt publish failed",
            },
        )
        assert first_failed.status_code == 200
        assert first_failed.json()["status"] == "pending"
        assert first_failed.json()["next_retry_at"] == first_reported_at

        second_pending = client.get("/api/v1/gateway/gw-002/commands/pending")
        assert second_pending.status_code == 200
        assert len(second_pending.json()["items"]) == 1
        assert second_pending.json()["items"][0]["attempt_count"] == 2

        second_failed = client.post(
            f"/api/v1/gateway/gw-002/commands/{command_id}/result",
            json={
                "status": "failed",
                "reported_at": second_reported_at,
                "detail": "mqtt publish failed again",
            },
        )
        assert second_failed.status_code == 200
        assert second_failed.json()["status"] == "failed"
        assert second_failed.json()["next_retry_at"] is None

        pending_after = client.get("/api/v1/gateway/gw-002/commands/pending")
        assert pending_after.status_code == 200
        assert pending_after.json()["items"] == []


def test_failed_command_becomes_timed_out_when_reported_after_expiry() -> None:
    settings = RuntimeSettings(
        device_command={
            "max_attempts": 3,
            "retry_backoff_s": 0,
            "delivery_lease_s": 15,
            "expire_after_s": 60,
        }
    )

    with TestClient(create_app(settings)) as client:
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
        create_body = create_response.json()
        command_id = create_body["command_id"]
        expires_at = create_body["expires_at"]

        pending_response = client.get("/api/v1/gateway/gw-002/commands/pending")
        assert pending_response.status_code == 200
        assert len(pending_response.json()["items"]) == 1

        reported_at = (
            datetime.fromisoformat(expires_at.replace("Z", "+00:00")) + timedelta(seconds=1)
        ).isoformat()
        failed_response = client.post(
            f"/api/v1/gateway/gw-002/commands/{command_id}/result",
            json={
                "status": "failed",
                "reported_at": reported_at,
                "detail": "delivery expired",
            },
        )
        assert failed_response.status_code == 200
        assert failed_response.json()["status"] == "timed_out"
        assert failed_response.json()["next_retry_at"] is None

        detail_response = client.get(f"/api/v1/gateway/commands/{command_id}")
        assert detail_response.status_code == 200
        assert detail_response.json()["status"] == "timed_out"
