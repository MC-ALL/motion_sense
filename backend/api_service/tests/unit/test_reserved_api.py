from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.auth_service import generate_password_hash
from app.settings import RuntimeSettings


def test_auth_login_refresh_logout_and_rest_protection() -> None:
    settings = RuntimeSettings(
        auth={
            "enforce_rest": True,
            "admin": {
                "username": "admin",
                "password_hash": generate_password_hash("admin123"),
            },
            "jwt": {
                "access_secret": "access-secret-for-tests",
                "refresh_secret": "refresh-secret-for-tests",
            },
        }
    )

    with TestClient(create_app(settings)) as client:
        unauthorized = client.get("/api/v1/devices")
        assert unauthorized.status_code == 401

        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert login.status_code == 200
        token_pair = login.json()
        assert token_pair["token_type"] == "bearer"
        assert token_pair["user"]["username"] == "admin"

        authorized = client.get(
            "/api/v1/devices",
            headers={"Authorization": f"Bearer {token_pair['access_token']}"},
        )
        assert authorized.status_code == 200
        assert authorized.json() == []

        refreshed = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": token_pair["refresh_token"]},
        )
        assert refreshed.status_code == 200
        refreshed_body = refreshed.json()
        assert refreshed_body["refresh_token"] != token_pair["refresh_token"]

        logout = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refreshed_body["refresh_token"]},
        )
        assert logout.status_code == 200
        assert logout.json() == {"ok": True}

        refresh_after_logout = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refreshed_body["refresh_token"]},
        )
        assert refresh_after_logout.status_code == 401


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
