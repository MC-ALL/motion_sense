from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.auth_service import AuthService, generate_password_hash
from app.settings import RuntimeSettings
from app.storage.memory_store import EventStore


def _build_auth_settings() -> dict:
    return {
        "enforce_rest": True,
        "enforce_ws": True,
        "admin": {
            "username": "admin",
            "password_hash": generate_password_hash("admin123"),
        },
        "jwt": {
            "access_secret": "access-secret-for-tests",
            "refresh_secret": "refresh-secret-for-tests",
        },
    }


def _login_and_get_access_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_auth_login_refresh_logout_and_rest_protection() -> None:
    settings = RuntimeSettings(auth=_build_auth_settings())

    with TestClient(create_app(settings)) as client:
        unauthorized = client.get("/api/v1/devices")
        assert unauthorized.status_code == 401

        unauthorized_ops = client.get("/ops/v1/health")
        assert unauthorized_ops.status_code == 401

        login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
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

        authorized_ops = client.get(
            "/ops/v1/health",
            headers={"Authorization": f"Bearer {token_pair['access_token']}"},
        )
        assert authorized_ops.status_code == 200
        assert authorized_ops.json()["module_id"] == "backend:api-main"

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


def test_gateway_internal_routes_remain_available_when_rest_auth_enabled() -> None:
    settings = RuntimeSettings(auth=_build_auth_settings())

    with TestClient(create_app(settings)) as client:
        ingest_response = client.post(
            "/api/v1/ingest/batch",
            json={
                "gateway_id": "gw-001",
                "sent_at": "2026-04-16T09:00:00Z",
                "items": [
                    {
                        "kind": "telemetry",
                        "topic": "gym/gym-gz-01/equipment/eq-001/telemetry",
                        "payload": {
                            "ts": 1713258000,
                            "device_id": "eq-001",
                            "gateway_id": "gw-001",
                            "power_w": 365.0,
                        },
                    }
                ],
            },
        )
        assert ingest_response.status_code == 200
        assert ingest_response.json() == {"accepted": 1}

        access_token = _login_and_get_access_token(client)
        create_response = client.post(
            "/api/v1/devices/env-a/config",
            json={
                "gym_id": "gym-gz-01",
                "gateway_id": "gw-001",
                "device_type": "env",
                "config": {"telemetry_interval_s": 30},
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert create_response.status_code == 200
        command_id = create_response.json()["command_id"]

        pending_response = client.get("/api/v1/gateway/gw-001/commands/pending")
        assert pending_response.status_code == 200
        assert pending_response.json()["items"][0]["command_id"] == command_id

        result_response = client.post(
            f"/api/v1/gateway/gw-001/commands/{command_id}/result",
            json={
                "status": "succeeded",
                "reported_at": "2026-04-16T09:00:05Z",
                "detail": "mqtt forwarded",
                "result_payload": {"forwarded": True},
            },
        )
        assert result_response.status_code == 200
        assert result_response.json()["status"] == "succeeded"

        report_response = client.post(
            "/api/v1/system/health/report",
            json={
                "gateway_id": "gw-001",
                "gym_id": "gym-gz-01",
                "reported_at": "2026-04-16T09:01:00Z",
                "components": [
                    {
                        "component_id": "mqtt-main",
                        "component_type": "mqtt_broker",
                        "display_name": "mqtt broker",
                        "online": True,
                        "health_status": "healthy",
                        "checked_at": "2026-04-16T09:01:00Z",
                        "endpoint": "mqtt://gw-001:1883",
                    }
                ],
            },
        )
        assert report_response.status_code == 200
        assert report_response.json()["overall_status"] == "healthy"

        unauthorized_health_query = client.get("/api/v1/system/health")
        assert unauthorized_health_query.status_code == 401

        authorized_health_query = client.get(
            "/api/v1/system/health",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert authorized_health_query.status_code == 200
        assert authorized_health_query.json()[0]["gateway_id"] == "gw-001"


def test_refresh_session_survives_auth_service_recreation() -> None:
    settings = RuntimeSettings(auth=_build_auth_settings())

    async def scenario() -> None:
        store = EventStore()
        await store.initialize()

        first_service = AuthService(settings.auth, store)
        await first_service.initialize()
        token_pair = await first_service.login("admin", "admin123")

        second_service = AuthService(settings.auth, store)
        refreshed = await second_service.refresh(token_pair.refresh_token)
        assert refreshed.user.username == "admin"
        assert refreshed.refresh_token != token_pair.refresh_token

        await second_service.logout(refreshed.refresh_token)
        await store.close()

    asyncio.run(scenario())


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
