from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.auth_service import generate_password_hash
from app.settings import RuntimeSettings


def _build_auth_settings() -> dict:
    return {
        "enforce_rest": True,
        "enforce_ws": True,
        "admin": {
            "username": "admin",
            "password_hash": generate_password_hash("admin123"),
        },
        "jwt": {
            "access_secret": "access-secret-for-role-tests",
            "refresh_secret": "refresh-secret-for-role-tests",
        },
    }


def _login(client: TestClient, username: str, password: str) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_user(
    client: TestClient,
    admin_token: str,
    username: str,
    password: str,
    role: str,
    *,
    gym_ids: list[str] | None = None,
    device_ids: list[str] | None = None,
) -> None:
    response = client.post(
        "/api/v1/users",
        json={
            "username": username,
            "password": password,
            "role": role,
            "gym_ids": gym_ids or [],
            "device_ids": device_ids or [],
        },
        headers=_headers(admin_token),
    )
    assert response.status_code == 201



def test_role_boundaries_for_business_and_ops_routes() -> None:
    settings = RuntimeSettings(auth=_build_auth_settings())

    with TestClient(create_app(settings)) as client:
        admin_token = _login(client, "admin", "admin123")["access_token"]
        _create_user(
            client,
            admin_token,
            "teacher_one",
            "teacher123",
            "teacher",
            gym_ids=["gym-gz-01"],
        )
        _create_user(
            client,
            admin_token,
            "student_one",
            "student123",
            "student",
            gym_ids=["gym-gz-01"],
            device_ids=["eq-001"],
        )

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
                    },
                    {
                        "kind": "alert",
                        "topic": "gym/gym-gz-01/equipment/eq-001/alert",
                        "payload": {
                            "ts": 1713258001,
                            "code": "OVERLOAD",
                            "level": "warning",
                            "message": "overload warning",
                        },
                    },
                ],
            },
        )
        assert ingest_response.status_code == 200

        teacher_token = _login(client, "teacher_one", "teacher123")["access_token"]
        student_token = _login(client, "student_one", "student123")["access_token"]

        teacher_devices = client.get("/api/v1/devices", headers=_headers(teacher_token))
        assert teacher_devices.status_code == 200
        assert teacher_devices.json()[0]["device_id"] == "eq-001"

        teacher_alerts = client.get("/api/v1/alerts", headers=_headers(teacher_token))
        assert teacher_alerts.status_code == 200
        assert teacher_alerts.json()[0]["code"] == "OVERLOAD"

        teacher_ack = client.patch("/api/v1/alerts/1/ack", headers=_headers(teacher_token))
        assert teacher_ack.status_code == 200
        assert teacher_ack.json()["is_ack"] is True

        teacher_register = client.post(
            "/api/v1/devices",
            json={
                "gym_id": "gym-gz-01",
                "device_type": "env",
                "device_id": "env-a",
                "gateway_id": "gw-001",
            },
            headers=_headers(teacher_token),
        )
        assert teacher_register.status_code == 403
        assert teacher_register.json()["detail"] == "required roles: admin"

        teacher_publish = client.post(
            "/api/v1/devices/eq-001/config",
            json={
                "gym_id": "gym-gz-01",
                "gateway_id": "gw-001",
                "device_type": "equipment",
                "config": {"target_reps": 12},
            },
            headers=_headers(teacher_token),
        )
        assert teacher_publish.status_code == 403
        assert teacher_publish.json()["detail"] == "required roles: admin"

        teacher_ops = client.get("/ops/v1/health", headers=_headers(teacher_token))
        assert teacher_ops.status_code == 403
        assert teacher_ops.json()["detail"] == "required roles: admin"

        student_devices = client.get("/api/v1/devices", headers=_headers(student_token))
        assert student_devices.status_code == 200
        assert student_devices.json()[0]["device_id"] == "eq-001"

        student_ack = client.patch("/api/v1/alerts/1/ack", headers=_headers(student_token))
        assert student_ack.status_code == 403
        assert student_ack.json()["detail"] == "required roles: admin, teacher"

        student_ops = client.get("/ops/v1/health", headers=_headers(student_token))
        assert student_ops.status_code == 403
        assert student_ops.json()["detail"] == "required roles: admin"

        admin_ops = client.get("/ops/v1/health", headers=_headers(admin_token))
        assert admin_ops.status_code == 200
        assert admin_ops.json()["module_id"] == "backend:api-main"


def test_ai_report_scope_respects_teacher_and_student_boundaries() -> None:
    settings = RuntimeSettings(auth=_build_auth_settings())

    with TestClient(create_app(settings)) as client:
        admin_token = _login(client, "admin", "admin123")["access_token"]
        _create_user(
            client,
            admin_token,
            "teacher_ai",
            "teacher123",
            "teacher",
            gym_ids=["gym-gz-01"],
        )
        _create_user(
            client,
            admin_token,
            "student_ai_one",
            "student123",
            "student",
            gym_ids=["gym-gz-01"],
            device_ids=["wb-001"],
        )
        _create_user(
            client,
            admin_token,
            "student_ai_two",
            "student123",
            "student",
            gym_ids=["gym-sz-01"],
            device_ids=["wb-002"],
        )

        first_report = client.post(
            "/api/v1/ai/analyze",
            json={
                "user_id": "student_ai_one",
                "start": "2026-04-01T00:00:00Z",
                "end": "2026-04-07T23:59:59Z",
            },
            headers=_headers(admin_token),
        )
        assert first_report.status_code == 201

        second_report = client.post(
            "/api/v1/ai/analyze",
            json={
                "user_id": "student_ai_two",
                "start": "2026-04-01T00:00:00Z",
                "end": "2026-04-07T23:59:59Z",
            },
            headers=_headers(admin_token),
        )
        assert second_report.status_code == 201

        teacher_token = _login(client, "teacher_ai", "teacher123")["access_token"]
        student_token = _login(client, "student_ai_one", "student123")["access_token"]

        teacher_list = client.get("/api/v1/ai/reports", headers=_headers(teacher_token))
        assert teacher_list.status_code == 200
        assert [item["user_id"] for item in teacher_list.json()] == ["student_ai_one"]

        teacher_forbidden = client.get(
            f"/api/v1/ai/reports/{second_report.json()['report_id']}",
            headers=_headers(teacher_token),
        )
        assert teacher_forbidden.status_code == 403
        assert teacher_forbidden.json()["detail"] == "ai report access forbidden"

        student_list = client.get("/api/v1/ai/reports", headers=_headers(student_token))
        assert student_list.status_code == 200
        assert [item["user_id"] for item in student_list.json()] == ["student_ai_one"]

        student_forbidden = client.get(
            f"/api/v1/ai/reports/{second_report.json()['report_id']}",
            headers=_headers(student_token),
        )
        assert student_forbidden.status_code == 403
        assert student_forbidden.json()["detail"] == "ai report access forbidden"
