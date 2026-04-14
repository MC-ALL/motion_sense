from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import RuntimeSettings


def test_websocket_ping_pong_and_subscription() -> None:
    with TestClient(create_app()) as client:
        with client.websocket_connect("/api/ws") as websocket:
            websocket.send_json({"type": "ping"})
            assert websocket.receive_json() == {"type": "pong"}

            websocket.send_json(
                {"type": "subscribe", "data": {"device_ids": ["eq-002"]}}
            )

            ingest_response = client.post(
                "/api/v1/ingest/batch",
                json={
                    "gateway_id": "gw-001",
                    "sent_at": "2026-04-14T15:30:00Z",
                    "items": [
                        {
                            "kind": "telemetry",
                            "topic": "gym/gym-gz-01/equipment/eq-002/telemetry",
                            "payload": {
                                "ts": 1712345680,
                                "device_id": "eq-002",
                                "power_w": 420.0,
                            },
                        }
                    ],
                },
            )

            assert ingest_response.status_code == 200
            pushed = websocket.receive_json()
            assert pushed["type"] == "telemetry"
            assert pushed["data"]["device_id"] == "eq-002"
            assert pushed["data"]["power_w"] == 420.0


def test_websocket_alert_broadcast_in_local_realtime_mode() -> None:
    settings = RuntimeSettings(realtime_backend="local")

    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/api/ws") as websocket:
            response = client.post(
                "/api/v1/ingest/batch",
                json={
                    "gateway_id": "gw-001",
                    "sent_at": "2026-04-14T16:30:00Z",
                    "items": [
                        {
                            "kind": "alert",
                            "topic": "gym/gym-gz-01/wristband/wb-009/alert",
                            "payload": {
                                "ts": 1712349000,
                                "code": "FALL_DETECTED",
                                "level": "critical",
                                "message": "fall detected",
                                "priority": "P0",
                            },
                        }
                    ],
                },
            )

            assert response.status_code == 200
            pushed = websocket.receive_json()
            assert pushed["type"] == "alert"
            assert pushed["data"]["device_id"] == "wb-009"
            assert pushed["data"]["code"] == "FALL_DETECTED"
