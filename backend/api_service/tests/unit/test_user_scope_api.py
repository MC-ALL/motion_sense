from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.auth_service import generate_password_hash
from app.services.websocket_manager import WebSocketAccessScope, _has_ai_report_access
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
            "access_secret": "access-secret-for-scope-tests",
            "refresh_secret": "refresh-secret-for-scope-tests",
        },
    }


def _login(client: TestClient, username: str, password: str) -> dict:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_user(
    client: TestClient,
    *,
    admin_token: str,
    username: str,
    password: str,
    role: str,
    gym_ids: list[str],
    device_ids: list[str],
) -> None:
    response = client.post(
        "/api/v1/users",
        json={
            "username": username,
            "password": password,
            "role": role,
            "gym_ids": gym_ids,
            "device_ids": device_ids,
        },
        headers=_headers(admin_token),
    )
    assert response.status_code == 201


def _seed_business_data(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ingest/batch",
        json={
            "gateway_id": "gw-001",
            "sent_at": "2026-04-16T09:00:00Z",
            "items": [
                {
                    "kind": "telemetry",
                    "topic": "gym/gym-gz-01/equipment/eq-001/telemetry",
                    "payload": {"ts": 1713258000, "device_id": "eq-001", "gateway_id": "gw-001", "power_w": 365.0},
                },
                {
                    "kind": "telemetry",
                    "topic": "gym/gym-gz-02/equipment/eq-002/telemetry",
                    "payload": {"ts": 1713258001, "device_id": "eq-002", "gateway_id": "gw-002", "power_w": 410.0},
                },
                {
                    "kind": "alert",
                    "topic": "gym/gym-gz-01/equipment/eq-001/alert",
                    "payload": {"ts": 1713258002, "code": "OVERLOAD", "level": "warning", "message": "overload warning"},
                },
                {
                    "kind": "alert",
                    "topic": "gym/gym-gz-02/equipment/eq-002/alert",
                    "payload": {"ts": 1713258003, "code": "CO2_HIGH", "level": "critical", "message": "co2 high"},
                },
                {
                    "kind": "binding",
                    "topic": "gym/gym-gz-01/wristband/wb-001/binding",
                    "payload": {
                        "ts": 1713258004,
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


def test_scope_filters_rest_queries_for_teacher_and_student() -> None:
    settings = RuntimeSettings(auth=_build_auth_settings())

    with TestClient(create_app(settings)) as client:
        admin_token = _login(client, "admin", "admin123")["access_token"]
        _create_user(
            client,
            admin_token=admin_token,
            username="teacher_gz1",
            password="teacher123",
            role="teacher",
            gym_ids=["gym-gz-01"],
            device_ids=[],
        )
        _create_user(
            client,
            admin_token=admin_token,
            username="student_eq1",
            password="student123",
            role="student",
            gym_ids=["gym-gz-01"],
            device_ids=["eq-001", "wb-001"],
        )
        _seed_business_data(client)

        teacher_token = _login(client, "teacher_gz1", "teacher123")["access_token"]
        student_token = _login(client, "student_eq1", "student123")["access_token"]

        teacher_devices = client.get("/api/v1/devices", headers=_headers(teacher_token))
        assert teacher_devices.status_code == 200
        assert [item["device_id"] for item in teacher_devices.json()] == ["eq-001", "wb-001"]

        teacher_alerts = client.get("/api/v1/alerts", headers=_headers(teacher_token))
        assert teacher_alerts.status_code == 200
        assert [item["device_id"] for item in teacher_alerts.json()] == ["eq-001"]

        teacher_other = client.get("/api/v1/devices/eq-002", headers=_headers(teacher_token))
        assert teacher_other.status_code == 403

        student_devices = client.get("/api/v1/devices", headers=_headers(student_token))
        assert student_devices.status_code == 200
        assert [item["device_id"] for item in student_devices.json()] == ["eq-001", "wb-001"]

        student_telemetry = client.get("/api/v1/telemetry/equipment/eq-001", headers=_headers(student_token))
        assert student_telemetry.status_code == 200
        assert student_telemetry.json()[0]["device_id"] == "eq-001"

        student_forbidden_telemetry = client.get("/api/v1/telemetry/equipment/eq-002", headers=_headers(student_token))
        assert student_forbidden_telemetry.status_code == 403

        student_bindings = client.get("/api/v1/wristband/wb-001/bindings", headers=_headers(student_token))
        assert student_bindings.status_code == 200
        assert student_bindings.json()[0]["equipment_id"] == "eq-001"

        student_alerts = client.get("/api/v1/alerts", headers=_headers(student_token))
        assert student_alerts.status_code == 200
        assert [item["device_id"] for item in student_alerts.json()] == ["eq-001"]

        student_alert_detail = client.get("/api/v1/alerts/2", headers=_headers(student_token))
        assert student_alert_detail.status_code == 403


def test_scope_filters_business_websocket_stream() -> None:
    settings = RuntimeSettings(auth=_build_auth_settings())

    with TestClient(create_app(settings)) as client:
        admin_token = _login(client, "admin", "admin123")["access_token"]
        _create_user(
            client,
            admin_token=admin_token,
            username="student_ws",
            password="student123",
            role="student",
            gym_ids=["gym-gz-01"],
            device_ids=["eq-001"],
        )
        student_token = _login(client, "student_ws", "student123")["access_token"]

        with client.websocket_connect(f"/api/ws?token={student_token}") as websocket:
            response_forbidden = client.post(
                "/api/v1/ingest/batch",
                json={
                    "gateway_id": "gw-002",
                    "sent_at": "2026-04-16T10:00:00Z",
                    "items": [
                        {
                            "kind": "telemetry",
                            "topic": "gym/gym-gz-02/equipment/eq-002/telemetry",
                            "payload": {"ts": 1713261600, "device_id": "eq-002", "gateway_id": "gw-002", "power_w": 410.0},
                        }
                    ],
                },
            )
            assert response_forbidden.status_code == 200

            response_allowed = client.post(
                "/api/v1/ingest/batch",
                json={
                    "gateway_id": "gw-001",
                    "sent_at": "2026-04-16T10:00:01Z",
                    "items": [
                        {
                            "kind": "telemetry",
                            "topic": "gym/gym-gz-01/equipment/eq-001/telemetry",
                            "payload": {"ts": 1713261601, "device_id": "eq-001", "gateway_id": "gw-001", "power_w": 365.0},
                        }
                    ],
                },
            )
            assert response_allowed.status_code == 200

            pushed = websocket.receive_json()
            assert pushed["type"] == "telemetry"
            assert pushed["data"]["device_id"] == "eq-001"
            assert pushed["data"]["gym_id"] == "gym-gz-01"


def test_ai_report_scope_matches_teacher_and_student_rules() -> None:
    student_scope = WebSocketAccessScope(
        username="student_a",
        role="student",
        gym_ids={"gym-gz-01"},
        device_ids={"wb-001"},
    )
    teacher_scope = WebSocketAccessScope(
        username="teacher_a",
        role="teacher",
        gym_ids={"gym-gz-01"},
        device_ids=set(),
    )
    unrelated_teacher_scope = WebSocketAccessScope(
        username="teacher_b",
        role="teacher",
        gym_ids={"gym-sz-01"},
        device_ids={"wb-888"},
    )

    assert _has_ai_report_access(
        student_scope,
        target_username="student_a",
        target_gym_ids={"gym-gz-01"},
        target_device_ids={"wb-001"},
    )
    assert not _has_ai_report_access(
        student_scope,
        target_username="student_b",
        target_gym_ids={"gym-gz-01"},
        target_device_ids={"wb-002"},
    )
    assert _has_ai_report_access(
        teacher_scope,
        target_username="student_a",
        target_gym_ids={"gym-gz-01"},
        target_device_ids={"wb-001"},
    )
    assert not _has_ai_report_access(
        unrelated_teacher_scope,
        target_username="student_a",
        target_gym_ids={"gym-gz-01"},
        target_device_ids={"wb-001"},
    )
