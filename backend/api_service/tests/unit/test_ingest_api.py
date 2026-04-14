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
                ],
            },
        )

        assert response.status_code == 200
        assert response.json() == {"accepted": 2}

        devices_response = client.get("/api/v1/devices")
        alerts_response = client.get("/api/v1/alerts")

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
            }
        ]

        assert alerts_response.status_code == 200
        assert alerts_response.json()[0]["device_id"] == "wb-001"
        assert alerts_response.json()[0]["code"] == "HR_HIGH"
        assert alerts_response.json()[0]["priority"] == "P0"
