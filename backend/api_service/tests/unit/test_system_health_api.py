from fastapi.testclient import TestClient

from app.main import create_app


def test_report_and_query_gateway_health() -> None:
    with TestClient(create_app()) as client:
        report_response = client.post(
            "/api/v1/system/health/report",
            json={
                "gateway_id": "gw-001",
                "gym_id": "gym-gz-01",
                "reported_at": "2026-04-15T09:00:00Z",
                "components": [
                    {
                        "component_id": "gateway_api",
                        "component_type": "gateway_api",
                        "display_name": "网关 API",
                        "online": True,
                        "health_status": "healthy",
                        "checked_at": "2026-04-15T09:00:00Z",
                        "endpoint": "http://127.0.0.1:8080/healthz",
                        "latency_ms": 8,
                    },
                    {
                        "component_id": "mqtt_broker",
                        "component_type": "mqtt_broker",
                        "display_name": "Mosquitto",
                        "online": False,
                        "health_status": "offline",
                        "checked_at": "2026-04-15T09:00:01Z",
                        "detail": "connection refused",
                    },
                ],
            },
        )

        assert report_response.status_code == 200
        detail = report_response.json()
        assert detail["gateway_id"] == "gw-001"
        assert detail["overall_status"] == "offline"
        assert detail["component_count"] == 2

        summary_response = client.get("/api/v1/system/health")
        assert summary_response.status_code == 200
        assert summary_response.json() == [
            {
                "gateway_id": "gw-001",
                "gym_id": "gym-gz-01",
                "reported_at": "2026-04-15T09:00:00Z",
                "component_count": 2,
                "online_count": 1,
                "unhealthy_count": 1,
                "overall_status": "offline",
            }
        ]

        filtered_response = client.get(
            "/api/v1/system/health",
            params={"overall_status": "offline"},
        )
        assert filtered_response.status_code == 200
        assert len(filtered_response.json()) == 1

        detail_response = client.get("/api/v1/system/health/gw-001")
        assert detail_response.status_code == 200
        assert detail_response.json()["components"][0]["component_id"] == "gateway_api"
        assert detail_response.json()["components"][1]["component_id"] == "mqtt_broker"


def test_gateway_health_report_replaces_previous_component_snapshot() -> None:
    with TestClient(create_app()) as client:
        initial_report = {
            "gateway_id": "gw-002",
            "gym_id": "gym-gz-01",
            "reported_at": "2026-04-15T09:10:00Z",
            "components": [
                {
                    "component_id": "edge_processor",
                    "component_type": "edge_processor",
                    "display_name": "边缘处理服务",
                    "online": True,
                    "health_status": "healthy",
                    "checked_at": "2026-04-15T09:10:00Z",
                },
                {
                    "component_id": "local_timeseries_db",
                    "component_type": "local_timeseries_db",
                    "display_name": "InfluxDB",
                    "online": True,
                    "health_status": "degraded",
                    "checked_at": "2026-04-15T09:10:00Z",
                },
            ],
        }
        update_report = {
            "gateway_id": "gw-002",
            "gym_id": "gym-gz-01",
            "reported_at": "2026-04-15T09:12:00Z",
            "components": [
                {
                    "component_id": "edge_processor",
                    "component_type": "edge_processor",
                    "display_name": "边缘处理服务",
                    "online": True,
                    "health_status": "healthy",
                    "checked_at": "2026-04-15T09:12:00Z",
                }
            ],
        }

        assert client.post("/api/v1/system/health/report", json=initial_report).status_code == 200
        update_response = client.post("/api/v1/system/health/report", json=update_report)
        assert update_response.status_code == 200

        detail_response = client.get("/api/v1/system/health/gw-002")
        assert detail_response.status_code == 200
        detail = detail_response.json()
        assert detail["component_count"] == 1
        assert detail["overall_status"] == "healthy"
        assert detail["components"][0]["component_id"] == "edge_processor"
