from fastapi.testclient import TestClient

from app.main import create_app


def test_auth_reserved_routes_return_501() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "admin",
                "password": "not-configured",
            },
        )

        assert response.status_code == 501
        detail = response.json()["detail"]
        assert detail["status"] == "reserved"
        assert detail["reserved_for"] == "phase_2_auth_integration"


def test_ai_reserved_routes_return_501() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/ai/analyze",
            json={
                "user_id": "user-001",
                "start": "2026-04-01T00:00:00Z",
                "end": "2026-04-07T23:59:59Z",
            },
        )

        assert response.status_code == 501
        detail = response.json()["detail"]
        assert detail["status"] == "reserved"
        assert detail["reserved_for"] == "phase_2_ai_integration"


def test_ota_reserved_routes_return_501() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/devices/env-a/ota",
            json={
                "firmware_url": "https://ota.example.com/fw/env-v1.0.0.bin",
                "version": "1.0.0",
                "sha256": "abc123",
                "force": False,
            },
        )

        assert response.status_code == 501
        detail = response.json()["detail"]
        assert detail["status"] == "reserved"
        assert detail["reserved_for"] == "phase_2_ota_integration"
