from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_backend_ops_endpoints_return_snapshot_and_stats() -> None:
    with TestClient(create_app()) as client:
        health_response = client.get("/ops/v1/health")
        assert health_response.status_code == 200
        health_payload = health_response.json()
        assert health_payload["module_id"] == "backend:api-main"
        assert health_payload["component_total"] >= 3
        assert health_payload["health_status"] == "healthy"

        components_response = client.get("/ops/v1/health/components")
        assert components_response.status_code == 200
        component_ids = {item["component_id"] for item in components_response.json()}
        assert {"api_service", "database", "redis", "websocket_hub"}.issubset(component_ids)

        ingest_response = client.post(
            "/api/v1/ingest/batch",
            json={
                "gateway_id": "gw-001",
                "sent_at": "2026-04-15T12:00:00Z",
                "items": [
                    {
                        "kind": "telemetry",
                        "topic": "gym/gym-gz-01/equipment/eq-001/telemetry",
                        "payload": {"ts": 1712345678, "device_id": "eq-001", "power_w": 380.0},
                    },
                    {
                        "kind": "alert",
                        "topic": "gym/gym-gz-01/wristband/wb-001/alert",
                        "payload": {
                            "ts": 1712345679,
                            "code": "HR_HIGH",
                            "level": "critical",
                            "message": "heart rate high",
                            "priority": "P0",
                        },
                    },
                ],
            },
        )
        assert ingest_response.status_code == 200

        stats_response = client.get("/ops/v1/stats")
        assert stats_response.status_code == 200
        stats_payload = stats_response.json()
        assert stats_payload["module_id"] == "backend:api-main"
        assert stats_payload["ingest_batches_total"] >= 1
        assert stats_payload["ingest_items_total"] >= 2
        assert stats_payload["published_telemetry_total"] >= 1
        assert stats_payload["published_alert_total"] >= 1


def test_backend_ops_websocket_ping_pong() -> None:
    with TestClient(create_app()) as client:
        with client.websocket_connect("/ops/ws") as websocket:
            initial = websocket.receive_json()
            assert initial["type"] == "ops_snapshot"
            assert initial["data"]["module_id"] == "backend:api-main"

            websocket.send_json({"type": "ping"})
            assert websocket.receive_json() == {"type": "pong"}
