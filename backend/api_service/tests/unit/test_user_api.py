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
            "access_secret": "access-secret-for-user-tests",
            "refresh_secret": "refresh-secret-for-user-tests",
        },
    }


def _login(client: TestClient, username: str, password: str) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()


def _admin_headers(client: TestClient) -> dict[str, str]:
    token_pair = _login(client, "admin", "admin12345")
    return {"Authorization": f"Bearer {token_pair['access_token']}"}


def test_admin_can_manage_users_and_teacher_cannot_call_admin_api() -> None:
    settings = RuntimeSettings(auth=_build_auth_settings())

    with TestClient(create_app(settings)) as client:
        headers = _admin_headers(client)

        create_response = client.post(
            "/api/v1/users",
            json={
                "username": "teacher_one",
                "password": "teacher123",
                "role": "teacher",
                "gym_ids": ["gym-gz-01"],
                "device_ids": [],
            },
            headers=headers,
        )
        assert create_response.status_code == 201
        assert create_response.json()["role"] == "teacher"
        assert create_response.json()["gym_ids"] == ["gym-gz-01"]

        list_response = client.get("/api/v1/users", headers=headers)
        assert list_response.status_code == 200
        assert [item["username"] for item in list_response.json()] == ["admin", "teacher_one"]

        teacher_login = _login(client, "teacher_one", "teacher123")
        assert teacher_login["user"]["username"] == "teacher_one"
        assert teacher_login["user"]["role"] == "teacher"
        assert teacher_login["user"]["gym_ids"] == ["gym-gz-01"]
        assert teacher_login["user"]["device_ids"] == []

        forbidden = client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {teacher_login['access_token']}"},
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["detail"] == "required roles: admin"


def test_refresh_token_reflects_latest_user_role_and_scope() -> None:
    settings = RuntimeSettings(auth=_build_auth_settings())

    with TestClient(create_app(settings)) as client:
        headers = _admin_headers(client)
        create_response = client.post(
            "/api/v1/users",
            json={
                "username": "role_switch",
                "password": "teacher123",
                "role": "teacher",
                "gym_ids": ["gym-gz-01"],
                "device_ids": ["eq-001"],
            },
            headers=headers,
        )
        assert create_response.status_code == 201

        first_login = _login(client, "role_switch", "teacher123")
        assert first_login["user"]["role"] == "teacher"
        assert first_login["user"]["gym_ids"] == ["gym-gz-01"]
        assert first_login["user"]["device_ids"] == ["eq-001"]

        patch_response = client.patch(
            "/api/v1/users/role_switch",
            json={"role": "student", "gym_ids": ["gym-gz-02"], "device_ids": ["wb-001"]},
            headers=headers,
        )
        assert patch_response.status_code == 200
        assert patch_response.json()["role"] == "student"
        assert patch_response.json()["gym_ids"] == ["gym-gz-02"]
        assert patch_response.json()["device_ids"] == ["wb-001"]

        refresh_response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": first_login["refresh_token"]},
        )
        assert refresh_response.status_code == 200
        assert refresh_response.json()["user"]["role"] == "student"
        assert refresh_response.json()["user"]["gym_ids"] == ["gym-gz-02"]
        assert refresh_response.json()["user"]["device_ids"] == ["wb-001"]


def test_bootstrap_admin_is_protected() -> None:
    settings = RuntimeSettings(auth=_build_auth_settings())

    with TestClient(create_app(settings)) as client:
        headers = _admin_headers(client)

        patch_password = client.patch(
            "/api/v1/users/admin",
            json={"password": "new-admin-password"},
            headers=headers,
        )
        assert patch_password.status_code == 409
        assert "deployment-managed" in patch_password.json()["detail"]

        patch_role = client.patch(
            "/api/v1/users/admin",
            json={"role": "teacher"},
            headers=headers,
        )
        assert patch_role.status_code == 409

        delete_response = client.delete("/api/v1/users/admin", headers=headers)
        assert delete_response.status_code == 409
        assert "cannot be deleted" in delete_response.json()["detail"]
