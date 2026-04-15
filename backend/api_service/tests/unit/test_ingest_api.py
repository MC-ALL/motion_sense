from fastapi.testclient import TestClient

from app.main import create_app


def test_ingest_batch_updates_devices_and_alerts() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/ingest/batch",
            json={
                "gateway_id": "gw-001",
                "sent_at": "2026-04-14T15:30:00Z",
                "items": [
                    {
                        "kind": "telemetry",
                        "topic": "gym/gym-gz-01/equipment/eq-001/telemetry",
                        "payload": {
                            "ts": 1712345678,
                            "device_id": "eq-001",
                            "power_w": 350.5,
                        },
                    },
                    {
                        "kind": "alert",
                        "topic": "gym/gym-gz-01/wristband/wb-001/alert",
                        "payload": {
                            "ts": 1712345679,
                            "code": "HR_HIGH",
                            "level": "warning",
                            "message": "heart rate high",
                            "priority": "P0",
                        },
                    },
                    {
                        "kind": "binding",
                        "topic": "gym/gym-gz-01/wristband/wb-001/binding",
                        "payload": {
                            "ts": 1712345680,
                            "wristband_id": "wb-001",
                            "equipment_id": "eq-001",
                            "action": "bind",
                            "reason": "ble_connected",
                        },
                    },
                ],
            },
        )

        assert response.status_code == 200
        assert response.json() == {"accepted": 3}

        devices_response = client.get("/api/v1/devices")
        alerts_response = client.get("/api/v1/alerts")
        filtered_alerts_response = client.get(
            "/api/v1/alerts",
            params={"device_id": "wb-001"},
        )
        empty_filtered_alerts_response = client.get(
            "/api/v1/alerts",
            params={"device_id": "eq-999"},
        )

        assert devices_response.status_code == 200
        assert devices_response.json() == [
            {
                "gym_id": "gym-gz-01",
                "device_type": "equipment",
                "device_id": "eq-001",
                "status": "online",
                "online": True,
                "last_seen_ts": 1712345678,
                "last_payload": {
                    "ts": 1712345678,
                    "device_id": "eq-001",
                    "power_w": 350.5,
                },
            },
            {
                "gym_id": "gym-gz-01",
                "device_type": "wristband",
                "device_id": "wb-001",
                "status": "bound",
                "online": True,
                "last_seen_ts": 1712345680,
                "last_payload": {
                    "ts": 1712345680,
                    "wristband_id": "wb-001",
                    "equipment_id": "eq-001",
                    "action": "bind",
                    "reason": "ble_connected",
                },
            },
        ]

        assert alerts_response.status_code == 200
        assert alerts_response.json()[0]["device_id"] == "wb-001"
        assert alerts_response.json()[0]["code"] == "HR_HIGH"
        assert alerts_response.json()[0]["priority"] == "P0"
        assert filtered_alerts_response.status_code == 200
        assert len(filtered_alerts_response.json()) == 1
        assert filtered_alerts_response.json()[0]["device_id"] == "wb-001"
        assert empty_filtered_alerts_response.status_code == 200
        assert empty_filtered_alerts_response.json() == []

        device_detail_response = client.get("/api/v1/devices/eq-001")
        alert_detail_response = client.get("/api/v1/alerts/1")
        ack_response = client.patch("/api/v1/alerts/1/ack")
        equipment_telemetry_response = client.get("/api/v1/telemetry/equipment/eq-001")
        bindings_response = client.get("/api/v1/wristband/wb-001/bindings")
        batch_ack_response = client.post("/api/v1/alerts/batch-ack", json={"ids": [1]})

        assert device_detail_response.status_code == 200
        assert device_detail_response.json()["device_id"] == "eq-001"
        assert alert_detail_response.status_code == 200
        assert alert_detail_response.json()["id"] == 1
        assert ack_response.status_code == 200
        assert ack_response.json()["is_ack"] is True
        assert equipment_telemetry_response.status_code == 200
        assert equipment_telemetry_response.json()[0]["device_id"] == "eq-001"
        assert equipment_telemetry_response.json()[0]["payload"]["power_w"] == 350.5
        assert bindings_response.status_code == 200
        assert bindings_response.json()[0]["wristband_id"] == "wb-001"
        assert bindings_response.json()[0]["equipment_id"] == "eq-001"
        assert batch_ack_response.status_code == 200
        assert batch_ack_response.json()["updated"] == 1
        assert batch_ack_response.json()["items"][0]["id"] == 1


def test_env_telemetry_aggregate() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/ingest/batch",
            json={
                "gateway_id": "gw-001",
                "sent_at": "2026-04-14T16:00:00Z",
                "items": [
                    {
                        "kind": "telemetry",
                        "topic": "gym/gym-gz-01/env/env-a/telemetry",
                        "payload": {
                            "ts": 1712347200,
                            "temperature_c": 26.0,
                            "co2_ppm": 800,
                            "pm25_ugm3": 32.5,
                        },
                    },
                    {
                        "kind": "telemetry",
                        "topic": "gym/gym-gz-01/env/env-a/telemetry",
                        "payload": {
                            "ts": 1712347500,
                            "temperature_c": 28.0,
                            "co2_ppm": 1000,
                            "pm25_ugm3": 40.5,
                        },
                    },
                ],
            },
        )

        assert response.status_code == 200

        aggregate_response = client.get(
            "/api/v1/telemetry/env/env-a/aggregate",
            params={"interval": "1h"},
        )

        assert aggregate_response.status_code == 200
        payload = aggregate_response.json()
        assert payload[0]["count"] == 2
        assert "ts" not in payload[0]["metrics"]
        assert payload[0]["metrics"]["temperature_c"]["min"] == 26.0
        assert payload[0]["metrics"]["temperature_c"]["max"] == 28.0
        assert payload[0]["metrics"]["temperature_c"]["avg"] == 27.0
        assert payload[0]["metrics"]["co2_ppm"]["avg"] == 900.0
