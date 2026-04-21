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

        overview_response = client.get(
            "/api/v1/user-wristband-bindings/overview",
            headers=headers,
        )
        assert overview_response.status_code == 200
        overview_payload = overview_response.json()
        assert len(overview_payload["active_bindings"]) == 1
        assert overview_payload["active_bindings"][0]["id"] == binding_payload["id"]
        assert any(item["id"] == binding_payload["id"] for item in overview_payload["binding_history"])

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

        after_unbind_overview_response = client.get(
            "/api/v1/user-wristband-bindings/overview",
            headers=headers,
        )
        assert after_unbind_overview_response.status_code == 200
        after_unbind_overview_payload = after_unbind_overview_response.json()
        assert after_unbind_overview_payload["active_bindings"] == []
        assert after_unbind_overview_payload["binding_history"][0]["id"] == binding_payload["id"]
        assert after_unbind_overview_payload["binding_history"][0]["is_active"] is False


def test_ingest_unbind_auto_aggregates_workout_sessions_and_supports_manual_backfill() -> None:
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
            device_ids=["wb-001", "eq-001", "eq-002"],
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
        binding_response = client.post(
            "/api/v1/user-wristband-bindings",
            json={
                "username": "student_one",
                "wristband_id": "wb-001",
                "gym_id": "gym-gz-01",
                "bound_at": "1970-01-01T00:00:00Z",
            },
            headers=headers,
        )
        assert binding_response.status_code == 201

        ingest_response = client.post(
            "/api/v1/ingest/batch",
            json={
                "gateway_id": "gw-001",
                "sent_at": "1970-01-01T00:02:10Z",
                "items": [
                    {
                        "kind": "telemetry",
                        "topic": "gym/gym-gz-01/wristband/wb-001/telemetry",
                        "payload": {"ts": 100, "heart_rate": 120, "step_count": 100},
                    },
                    {
                        "kind": "telemetry",
                        "topic": "gym/gym-gz-01/equipment/eq-001/telemetry",
                        "payload": {"ts": 100, "rep_count": 0, "energy_wh": 0.0},
                    },
                    {
                        "kind": "binding",
                        "topic": "gym/gym-gz-01/wristband/wb-001/binding",
                        "payload": {
                            "ts": 100,
                            "wristband_id": "wb-001",
                            "equipment_id": "eq-001",
                            "action": "bind",
                            "reason": "ble_connected",
                        },
                    },
                    {
                        "kind": "telemetry",
                        "topic": "gym/gym-gz-01/wristband/wb-001/telemetry",
                        "payload": {"ts": 105, "heart_rate": 130, "step_count": 120},
                    },
                    {
                        "kind": "telemetry",
                        "topic": "gym/gym-gz-01/equipment/eq-001/telemetry",
                        "payload": {"ts": 105, "rep_count": 12, "energy_wh": 1.25},
                    },
                    {
                        "kind": "telemetry",
                        "topic": "gym/gym-gz-01/equipment/eq-001/telemetry",
                        "payload": {"ts": 110, "rep_count": 12, "energy_wh": 1.25},
                    },
                    {
                        "kind": "binding",
                        "topic": "gym/gym-gz-01/wristband/wb-001/binding",
                        "payload": {
                            "ts": 110,
                            "wristband_id": "wb-001",
                            "equipment_id": "eq-001",
                            "action": "unbind",
                            "reason": "exercise_completed",
                        },
                    },
                    {
                        "kind": "binding",
                        "topic": "gym/gym-gz-01/wristband/wb-001/binding",
                        "payload": {
                            "ts": 112,
                            "wristband_id": "wb-001",
                            "equipment_id": "eq-002",
                            "action": "bind",
                            "reason": "ble_connected",
                        },
                    },
                    {
                        "kind": "telemetry",
                        "topic": "gym/gym-gz-01/equipment/eq-002/telemetry",
                        "payload": {"ts": 112, "rep_count": 0, "energy_wh": 0.0},
                    },
                    {
                        "kind": "telemetry",
                        "topic": "gym/gym-gz-01/wristband/wb-001/telemetry",
                        "payload": {"ts": 115, "heart_rate": 140, "step_count": 150},
                    },
                    {
                        "kind": "telemetry",
                        "topic": "gym/gym-gz-01/wristband/wb-001/telemetry",
                        "payload": {"ts": 120, "heart_rate": 138, "step_count": 160},
                    },
                    {
                        "kind": "telemetry",
                        "topic": "gym/gym-gz-01/equipment/eq-002/telemetry",
                        "payload": {"ts": 120, "rep_count": 8, "energy_wh": 0.75},
                    },
                    {
                        "kind": "binding",
                        "topic": "gym/gym-gz-01/wristband/wb-001/binding",
                        "payload": {
                            "ts": 120,
                            "wristband_id": "wb-001",
                            "equipment_id": "eq-002",
                            "action": "unbind",
                            "reason": "exercise_completed",
                        },
                    },
                ],
            },
        )
        assert ingest_response.status_code == 200

        sessions_response = client.get(
            "/api/v1/workout-sessions",
            params={"username": "student_one"},
            headers=headers,
        )
        assert sessions_response.status_code == 200
        sessions_payload = sessions_response.json()
        assert len(sessions_payload) == 1
        session = sessions_payload[0]
        assert session["source"] == "aggregated"
        assert session["status"] == "completed"
        assert session["duration_s"] == 20
        assert session["equipment_ids"] == ["eq-001", "eq-002"]
        assert len(session["segments"]) == 2
        assert session["segments"][0]["equipment_id"] == "eq-001"
        assert session["segments"][0]["duration_s"] == 10
        assert session["segments"][0]["rep_count"] == 12
        assert session["segments"][0]["energy_wh"] == 1.25
        assert session["segments"][1]["equipment_id"] == "eq-002"
        assert session["segments"][1]["duration_s"] == 8
        assert session["segments"][1]["rep_count"] == 8
        assert session["segments"][1]["energy_wh"] == 0.75
        assert session["metrics"]["avg_heart_rate"] == 132.0
        assert session["metrics"]["max_heart_rate"] == 140
        assert session["metrics"]["total_steps"] == 60
        assert session["metrics"]["total_rep_count"] == 20
        assert session["metrics"]["total_energy_wh"] == 2.0

        aggregate_response = client.post(
            "/api/v1/workout-sessions/aggregate",
            json={"username": "student_one", "wristband_id": "wb-001", "gym_id": "gym-gz-01"},
            headers=headers,
        )
        assert aggregate_response.status_code == 200
        aggregate_payload = aggregate_response.json()
        assert aggregate_payload["processed_bindings"] == 1
        assert aggregate_payload["created_sessions"] == 0
        assert aggregate_payload["updated_sessions"] == 1
        assert len(aggregate_payload["sessions"]) == 1
        assert aggregate_payload["sessions"][0]["session_id"] == session["session_id"]


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
