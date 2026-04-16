from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_register_update_and_delete_device() -> None:
    with TestClient(create_app()) as client:
        register_response = client.post(
            "/api/v1/devices",
            json={
                "gym_id": "gym-gz-01",
                "device_type": "equipment",
                "device_id": "eq-010",
                "gateway_id": "gw-001",
                "display_name": "有氧椭圆机 10",
                "location": "二楼东侧",
                "metadata": {"vendor": "acme", "model": "e10"},
            },
        )

        assert register_response.status_code == 200
        register_body = register_response.json()
        assert register_body["status"] == "registered"
        assert register_body["online"] is False
        assert register_body["gateway_id"] == "gw-001"
        assert register_body["display_name"] == "有氧椭圆机 10"
        assert register_body["location"] == "二楼东侧"
        assert register_body["metadata"]["model"] == "e10"
        assert register_body["registered_at"] is not None
        assert register_body["updated_at"] is not None

        detail_response = client.get("/api/v1/devices/eq-010")
        assert detail_response.status_code == 200
        assert detail_response.json()["display_name"] == "有氧椭圆机 10"

        update_response = client.patch(
            "/api/v1/devices/eq-010",
            json={
                "display_name": "力量椭圆机 10",
                "location": "三楼西侧",
                "metadata": {"vendor": "acme", "model": "e10-pro"},
            },
        )
        assert update_response.status_code == 200
        update_body = update_response.json()
        assert update_body["display_name"] == "力量椭圆机 10"
        assert update_body["location"] == "三楼西侧"
        assert update_body["metadata"]["model"] == "e10-pro"

        delete_response = client.delete("/api/v1/devices/eq-010")
        assert delete_response.status_code == 200
        assert delete_response.json() == {"ok": True}

        missing_response = client.get("/api/v1/devices/eq-010")
        assert missing_response.status_code == 404


def test_registered_device_can_be_used_for_config_publish() -> None:
    with TestClient(create_app()) as client:
        register_response = client.post(
            "/api/v1/devices",
            json={
                "gym_id": "gym-gz-01",
                "device_type": "env",
                "device_id": "env-b",
                "gateway_id": "gw-009",
                "display_name": "环境节点 B",
            },
        )
        assert register_response.status_code == 200

        config_response = client.post(
            "/api/v1/devices/env-b/config",
            json={"config": {"telemetry_interval_s": 15}},
        )
        assert config_response.status_code == 200
        body = config_response.json()
        assert body["gateway_id"] == "gw-009"
        assert body["gym_id"] == "gym-gz-01"
        assert body["device_type"] == "env"
        assert body["topic"] == "gym/gym-gz-01/env/env-b/config"


def test_register_duplicate_device_id_with_different_scope_conflicts() -> None:
    with TestClient(create_app()) as client:
        first_response = client.post(
            "/api/v1/devices",
            json={
                "gym_id": "gym-gz-01",
                "device_type": "equipment",
                "device_id": "eq-030",
                "gateway_id": "gw-001",
            },
        )
        assert first_response.status_code == 200

        second_response = client.post(
            "/api/v1/devices",
            json={
                "gym_id": "gym-sz-01",
                "device_type": "env",
                "device_id": "eq-030",
                "gateway_id": "gw-002",
            },
        )
        assert second_response.status_code == 409
        assert "device_id already exists" in second_response.json()["detail"]


def test_ingest_preserves_registered_device_metadata() -> None:
    with TestClient(create_app()) as client:
        register_response = client.post(
            "/api/v1/devices",
            json={
                "gym_id": "gym-gz-01",
                "device_type": "equipment",
                "device_id": "eq-020",
                "gateway_id": "gw-020",
                "display_name": "划船机 20",
                "location": "一楼北侧",
                "metadata": {"vendor": "acme"},
            },
        )
        assert register_response.status_code == 200

        ingest_response = client.post(
            "/api/v1/ingest/batch",
            json={
                "gateway_id": "gw-020",
                "sent_at": "2026-04-16T10:00:00Z",
                "items": [
                    {
                        "kind": "telemetry",
                        "topic": "gym/gym-gz-01/equipment/eq-020/telemetry",
                        "payload": {
                            "ts": 1713261600,
                            "device_id": "eq-020",
                            "gateway_id": "gw-020",
                            "power_w": 410.5,
                        },
                    }
                ],
            },
        )
        assert ingest_response.status_code == 200

        detail_response = client.get("/api/v1/devices/eq-020")
        assert detail_response.status_code == 200
        body = detail_response.json()
        assert body["online"] is True
        assert body["status"] == "online"
        assert body["gateway_id"] == "gw-020"
        assert body["display_name"] == "划船机 20"
        assert body["location"] == "一楼北侧"
        assert body["metadata"]["vendor"] == "acme"
        assert body["last_payload"]["power_w"] == 410.5
