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
            "password_hash": generate_password_hash("admin12345"),
        },
        "jwt": {
            "access_secret": "access-secret-for-workout-tests",
            "refresh_secret": "refresh-secret-for-workout-tests",
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


def _admin_headers(client: TestClient) -> dict[str, str]:
    return _headers(_login(client, "admin", "admin12345")["access_token"])


def _create_user(
    client: TestClient,
    *,
    headers: dict[str, str],
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
        headers=headers,
    )
    assert response.status_code == 201


def _register_device(
    client: TestClient,
    *,
    headers: dict[str, str],
    gym_id: str,
    device_type: str,
    device_id: str,
    gateway_id: str,
) -> None:
    response = client.post(
        "/api/v1/devices",
        json={
            "gym_id": gym_id,
            "device_type": device_type,
            "device_id": device_id,
            "gateway_id": gateway_id,
            "display_name": device_id,
            "location": "zone-a",
            "metadata": {},
        },
        headers=headers,
    )
    assert response.status_code == 200


def test_admin_can_manage_user_wristband_bindings_and_workout_sessions() -> None:
    settings = RuntimeSettings(auth=_build_auth_settings())

    with TestClient(create_app(settings)) as client:
        headers = _admin_headers(client)
        _create_user(
            client,
            headers=headers,
            username="student_one",
            password="student123",
            role="student",
            gym_ids=["gym-gz-01"],
            device_ids=["wb-001", "eq-001"],
        )
        _create_user(
            client,
            headers=headers,
            username="student_two",
            password="student123",
            role="student",
            gym_ids=["gym-gz-01"],
            device_ids=["wb-002", "eq-001"],
        )
        _register_device(
            client,
            headers=headers,
            gym_id="gym-gz-01",
            device_type="wristband",
            device_id="wb-001",
            gateway_id="gw-001",
        )
        _register_device(
            client,
            headers=headers,
            gym_id="gym-gz-01",
            device_type="equipment",
            device_id="eq-001",
            gateway_id="gw-001",
        )

        binding_response = client.post(
            "/api/v1/user-wristband-bindings",
            json={
                "username": "student_one",
                "wristband_id": "wb-001",
                "gym_id": "gym-gz-01",
                "bound_at": "2026-04-19T08:00:00Z",
            },
            headers=headers,
        )
        assert binding_response.status_code == 201
        binding_payload = binding_response.json()
        binding_payload = binding_response.json()
        assert binding_payload["is_active"] is True
        assert binding_payload["username"] == "student_one"

        conflict_response = client.post(
            "/api/v1/user-wristband-bindings",
            json={
                "username": "student_two",
                "wristband_id": "wb-001",
                "gym_id": "gym-gz-01",
            },
            headers=headers,
        )
        assert conflict_response.status_code == 409

        session_response = client.post(
            "/api/v1/workout-sessions",
            json={
                "username": "student_one",
                "wristband_id": "wb-001",
                "gym_id": "gym-gz-01",
                "status": "completed",
                "started_at": "2026-04-19T08:00:00Z",
                "ended_at": "2026-04-19T08:30:00Z",
                "segments": [
                    {
                        "equipment_id": "eq-001",
                        "started_at": "2026-04-19T08:00:00Z",
                        "ended_at": "2026-04-19T08:30:00Z",
                        "rep_count": 40,
                        "energy_wh": 12.5,
                    }
                ],
                "metrics": {
                    "avg_heart_rate": 128.5,
                    "max_heart_rate": 156,
                    "total_rep_count": 40,
                    "total_energy_wh": 12.5,
                },
            },
            headers=headers,
        )
        assert session_response.status_code == 201
        session_payload = session_response.json()
        assert session_payload["duration_s"] == 1800
        assert session_payload["equipment_ids"] == ["eq-001"]
        assert session_payload["segments"][0]["duration_s"] == 1800

        patch_response = client.patch(
            f"/api/v1/workout-sessions/{session_payload['session_id']}",
            json={
                "ended_at": "2026-04-19T08:35:00Z",
                "notes": "cool down included",
            },
            headers=headers,
        )
        assert patch_response.status_code == 200
        assert patch_response.json()["duration_s"] == 2100
        assert patch_response.json()["notes"] == "cool down included"

        unbind_response = client.post(
            f"/api/v1/user-wristband-bindings/{binding_payload['id']}/unbind",
            json={"unbound_at": "2026-04-19T09:00:00Z", "note": "class finished"},
            headers=headers,
        )
        assert unbind_response.status_code == 200
        assert unbind_response.json()["is_active"] is False
        assert unbind_response.json()["unbound_at"] == "2026-04-19T09:00:00+00:00"


def test_scope_filters_user_wristband_bindings_and_workout_sessions() -> None:
    settings = RuntimeSettings(auth=_build_auth_settings())

    with TestClient(create_app(settings)) as client:
        headers = _admin_headers(client)
        _create_user(
            client,
            headers=headers,
            username="teacher_gz1",
            password="teacher123",
            role="teacher",
            gym_ids=["gym-gz-01"],
            device_ids=[],
        )
        _create_user(
            client,
            headers=headers,
            username="student_one",
            password="student123",
            role="student",
            gym_ids=["gym-gz-01"],
            device_ids=["wb-001", "eq-001"],
        )
        _create_user(
            client,
            headers=headers,
            username="student_two",
            password="student123",
            role="student",
            gym_ids=["gym-gz-02"],
            device_ids=["wb-002", "eq-002"],
        )
        _register_device(
            client,
            headers=headers,
            gym_id="gym-gz-01",
            device_type="wristband",
            device_id="wb-001",
            gateway_id="gw-001",
        )
        _register_device(
            client,
            headers=headers,
            gym_id="gym-gz-01",
            device_type="equipment",
            device_id="eq-001",
            gateway_id="gw-001",
        )
        _register_device(
            client,
            headers=headers,
            gym_id="gym-gz-02",
            device_type="wristband",
            device_id="wb-002",
            gateway_id="gw-002",
        )
        _register_device(
            client,
            headers=headers,
            gym_id="gym-gz-02",
            device_type="equipment",
            device_id="eq-002",
            gateway_id="gw-002",
        )

        binding_one = client.post(
            "/api/v1/user-wristband-bindings",
            json={
                "username": "student_one",
                "wristband_id": "wb-001",
                "gym_id": "gym-gz-01",
                "bound_at": "2026-04-19T08:00:00Z",
            },
            headers=headers,
        )
        assert binding_one.status_code == 201
        binding_two = client.post(
            "/api/v1/user-wristband-bindings",
            json={
                "username": "student_two",
                "wristband_id": "wb-002",
                "gym_id": "gym-gz-02",
                "bound_at": "2026-04-19T10:00:00Z",
            },
            headers=headers,
        )
        assert binding_two.status_code == 201

        session_one = client.post(
            "/api/v1/workout-sessions",
            json={
                "username": "student_one",
                "wristband_id": "wb-001",
                "gym_id": "gym-gz-01",
                "status": "completed",
                "started_at": "2026-04-19T08:00:00Z",
                "ended_at": "2026-04-19T08:45:00Z",
                "segments": [
                    {
                        "equipment_id": "eq-001",
                        "started_at": "2026-04-19T08:00:00Z",
                        "ended_at": "2026-04-19T08:45:00Z",
                    }
                ],
            },
            headers=headers,
        )
        assert session_one.status_code == 201
        session_one_id = session_one.json()["session_id"]

        session_two = client.post(
            "/api/v1/workout-sessions",
            json={
                "username": "student_two",
                "wristband_id": "wb-002",
                "gym_id": "gym-gz-02",
                "status": "completed",
                "started_at": "2026-04-19T10:00:00Z",
                "ended_at": "2026-04-19T10:20:00Z",
                "segments": [
                    {
                        "equipment_id": "eq-002",
                        "started_at": "2026-04-19T10:00:00Z",
                        "ended_at": "2026-04-19T10:20:00Z",
                    }
                ],
            },
            headers=headers,
        )
        assert session_two.status_code == 201
        session_two_id = session_two.json()["session_id"]

        teacher_token = _login(client, "teacher_gz1", "teacher123")["access_token"]
        student_token = _login(client, "student_one", "student123")["access_token"]

        teacher_bindings = client.get(
            "/api/v1/user-wristband-bindings",
            headers=_headers(teacher_token),
        )
        assert teacher_bindings.status_code == 200
        assert [item["wristband_id"] for item in teacher_bindings.json()] == ["wb-001"]

        teacher_sessions = client.get(
            "/api/v1/workout-sessions",
            headers=_headers(teacher_token),
        )
        assert teacher_sessions.status_code == 200
        assert [item["session_id"] for item in teacher_sessions.json()] == [session_one_id]

        student_bindings = client.get(
            "/api/v1/user-wristband-bindings",
            headers=_headers(student_token),
        )
        assert student_bindings.status_code == 200
        assert [item["username"] for item in student_bindings.json()] == ["student_one"]

        student_sessions = client.get(
            "/api/v1/workout-sessions",
            headers=_headers(student_token),
        )
        assert student_sessions.status_code == 200
        assert [item["session_id"] for item in student_sessions.json()] == [session_one_id]

        forbidden_detail = client.get(
            f"/api/v1/workout-sessions/{session_two_id}",
            headers=_headers(student_token),
        )
        assert forbidden_detail.status_code == 403


def test_training_profile_aggregates_sessions_and_enforces_scope() -> None:
    settings = RuntimeSettings(auth=_build_auth_settings())

    with TestClient(create_app(settings)) as client:
        headers = _admin_headers(client)
        _create_user(
            client,
            headers=headers,
            username="teacher_gz1",
            password="teacher123",
            role="teacher",
            gym_ids=["gym-gz-01"],
            device_ids=[],
        )
        _create_user(
            client,
            headers=headers,
            username="student_one",
            password="student123",
            role="student",
            gym_ids=["gym-gz-01"],
            device_ids=["wb-001", "eq-001", "eq-002"],
        )
        _create_user(
            client,
            headers=headers,
            username="student_two",
            password="student123",
            role="student",
            gym_ids=["gym-gz-02"],
            device_ids=["wb-002", "eq-003"],
        )
        _register_device(
            client,
            headers=headers,
            gym_id="gym-gz-01",
            device_type="wristband",
            device_id="wb-001",
            gateway_id="gw-001",
        )
        _register_device(
            client,
            headers=headers,
            gym_id="gym-gz-01",
            device_type="equipment",
            device_id="eq-001",
            gateway_id="gw-001",
        )
        _register_device(
            client,
            headers=headers,
            gym_id="gym-gz-01",
            device_type="equipment",
            device_id="eq-002",
            gateway_id="gw-001",
        )
        _register_device(
            client,
            headers=headers,
            gym_id="gym-gz-02",
            device_type="wristband",
            device_id="wb-002",
            gateway_id="gw-002",
        )
        _register_device(
            client,
            headers=headers,
            gym_id="gym-gz-02",
            device_type="equipment",
            device_id="eq-003",
            gateway_id="gw-002",
        )

        binding_response = client.post(
            "/api/v1/user-wristband-bindings",
            json={
                "username": "student_one",
                "wristband_id": "wb-001",
                "gym_id": "gym-gz-01",
                "bound_at": "2026-04-19T08:00:00Z",
            },
            headers=headers,
        )
        assert binding_response.status_code == 201
        binding_payload = binding_response.json()

        first_session = client.post(
            "/api/v1/workout-sessions",
            json={
                "username": "student_one",
                "wristband_id": "wb-001",
                "gym_id": "gym-gz-01",
                "status": "completed",
                "started_at": "2026-04-19T08:00:00Z",
                "ended_at": "2026-04-19T08:30:00Z",
                "segments": [
                    {
                        "equipment_id": "eq-001",
                        "started_at": "2026-04-19T08:00:00Z",
                        "ended_at": "2026-04-19T08:30:00Z",
                        "rep_count": 40,
                        "energy_wh": 12.5,
                    }
                ],
                "metrics": {
                    "avg_heart_rate": 128.0,
                    "max_heart_rate": 156,
                    "total_rep_count": 40,
                    "total_energy_wh": 12.5,
                },
            },
            headers=headers,
        )
        assert first_session.status_code == 201

        second_session = client.post(
            "/api/v1/workout-sessions",
            json={
                "username": "student_one",
                "wristband_id": "wb-001",
                "gym_id": "gym-gz-01",
                "status": "completed",
                "started_at": "2026-04-20T09:00:00Z",
                "ended_at": "2026-04-20T09:20:00Z",
                "segments": [
                    {
                        "equipment_id": "eq-002",
                        "started_at": "2026-04-20T09:00:00Z",
                        "ended_at": "2026-04-20T09:20:00Z",
                        "rep_count": 24,
                        "energy_wh": 8.0,
                    }
                ],
                "metrics": {
                    "avg_heart_rate": 140.0,
                    "max_heart_rate": 165,
                    "total_rep_count": 24,
                    "total_energy_wh": 8.0,
                },
            },
            headers=headers,
        )
        assert second_session.status_code == 201

        client.post(
            "/api/v1/workout-sessions",
            json={
                "username": "student_two",
                "wristband_id": "wb-002",
                "gym_id": "gym-gz-02",
                "status": "completed",
                "started_at": "2026-04-20T10:00:00Z",
                "ended_at": "2026-04-20T10:10:00Z",
                "segments": [
                    {
                        "equipment_id": "eq-003",
                        "started_at": "2026-04-20T10:00:00Z",
                        "ended_at": "2026-04-20T10:10:00Z",
                    }
                ],
            },
            headers=headers,
        )

        teacher_token = _login(client, "teacher_gz1", "teacher123")["access_token"]
        student_token = _login(client, "student_one", "student123")["access_token"]

        teacher_profile = client.get(
            "/api/v1/users/student_one/training-profile",
            headers=_headers(teacher_token),
        )
        assert teacher_profile.status_code == 200
        teacher_payload = teacher_profile.json()
        assert teacher_payload["user"]["username"] == "student_one"
        assert teacher_payload["active_binding"]["wristband_id"] == "wb-001"
        assert teacher_payload["summary"]["total_sessions"] == 2
        assert teacher_payload["summary"]["completed_sessions"] == 2
        assert teacher_payload["summary"]["total_duration_s"] == 3000
        assert teacher_payload["summary"]["total_rep_count"] == 64
        assert teacher_payload["summary"]["total_energy_wh"] == 20.5
        assert teacher_payload["summary"]["max_heart_rate"] == 165
        assert teacher_payload["summary"]["avg_heart_rate"] == 132.8
        assert teacher_payload["summary"]["equipment_ids"] == ["eq-002", "eq-001"]

        student_self_profile = client.get(
            "/api/v1/users/student_one/training-profile",
            headers=_headers(student_token),
        )
        assert student_self_profile.status_code == 200
        assert student_self_profile.json()["summary"]["total_sessions"] == 2

        client.post(
            f"/api/v1/user-wristband-bindings/{binding_payload['id']}/unbind",
            json={"unbound_at": "2026-04-20T12:00:00Z"},
            headers=headers,
        )
        profile_after_unbind = client.get(
            "/api/v1/users/student_one/training-profile",
            headers=_headers(teacher_token),
        )
        assert profile_after_unbind.status_code == 200
        assert "active_binding" in profile_after_unbind.json()
        assert profile_after_unbind.json()["active_binding"] is None

        forbidden_other_profile = client.get(
            "/api/v1/users/student_two/training-profile",
            headers=_headers(student_token),
        )
        assert forbidden_other_profile.status_code == 403
