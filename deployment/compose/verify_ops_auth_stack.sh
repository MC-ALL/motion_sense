#!/bin/sh
set -eu

compose_file="${COMPOSE_FILE_PATH:-deployment/compose/docker-compose.yaml}"
backend_service="${BACKEND_SERVICE_NAME:-backend_api_service}"
gateway_service="${GATEWAY_SERVICE_NAME:-gateway_edge_processor}"
ops_service="${OPS_SERVICE_NAME:-ops_observer_api_service}"
teacher_username="ops_auth_teacher_$(date +%s)"
teacher_password="${TEACHER_PASSWORD:-teacher123}"

require_running_service() {
  service_name="$1"
  container_id="$(docker compose -f "${compose_file}" ps -q "${service_name}")"
  if [ -z "${container_id}" ]; then
    echo "service not found in compose stack: ${service_name}" >&2
    exit 1
  fi

  running_state="$(docker inspect -f '{{.State.Running}}' "${container_id}")"
  if [ "${running_state}" != "true" ]; then
    echo "service is not running: ${service_name}" >&2
    exit 1
  fi
}

require_running_service "${backend_service}"
require_running_service "${gateway_service}"
require_running_service "${ops_service}"

backend_bootstrap="$(
  docker compose -f "${compose_file}" exec -T "${backend_service}" \
    sh -lc 'cat /runtime/config/backend/api_service/bootstrap_admin.txt'
)"

gateway_ops_token="$(
  docker compose -f "${compose_file}" exec -T "${gateway_service}" \
    sh -lc 'cat /runtime/secrets/edge_processor_ops_token.txt'
)"

backend_admin_username="$(printf '%s\n' "${backend_bootstrap}" | sed -n 's/^username: //p' | head -n 1)"
backend_admin_password="$(printf '%s\n' "${backend_bootstrap}" | sed -n 's/^password: //p' | head -n 1)"
gateway_ops_token="$(printf '%s\n' "${gateway_ops_token}" | tr -d '\r\n')"

if [ -z "${backend_admin_username}" ] || [ -z "${backend_admin_password}" ]; then
  echo "failed to read backend bootstrap admin credentials from running container" >&2
  exit 1
fi

if [ -z "${gateway_ops_token}" ]; then
  echo "failed to read gateway ops token from running container" >&2
  exit 1
fi

docker compose -f "${compose_file}" exec -T \
  -e "BACKEND_ADMIN_USERNAME=${backend_admin_username}" \
  -e "BACKEND_ADMIN_PASSWORD=${backend_admin_password}" \
  -e "GATEWAY_OPS_TOKEN=${gateway_ops_token}" \
  -e "TEACHER_USERNAME=${teacher_username}" \
  -e "TEACHER_PASSWORD=${teacher_password}" \
  -e "GATEWAY_SERVICE_HOST=${gateway_service}" \
  -e "OPS_SERVICE_HOST=${ops_service}" \
  "${backend_service}" python - <<'PY'
from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request

import websockets


BACKEND_BASE_URL = "http://127.0.0.1:8000"
GATEWAY_BASE_URL = f"http://{os.environ['GATEWAY_SERVICE_HOST']}:8080"
OPS_BASE_URL = f"http://{os.environ['OPS_SERVICE_HOST']}:8090"


def request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: dict[str, object] | None = None,
) -> tuple[int, str]:
    payload = None
    actual_headers = dict(headers or {})
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        actual_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=payload, headers=actual_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def expect_status(
    name: str,
    url: str,
    expected_status: int,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: dict[str, object] | None = None,
) -> str:
    status, body = request(url, method=method, headers=headers, data=data)
    if status != expected_status:
        raise AssertionError(f"{name}: expected {expected_status}, got {status}, body={body}")
    print(f"{name}: {status}")
    return body


async def expect_ws_failure(name: str, url: str) -> None:
    try:
        async with websockets.connect(url) as websocket:
            try:
                await asyncio.wait_for(websocket.recv(), timeout=3)
            except websockets.ConnectionClosed:
                print(f"{name}: rejected")
                return
        raise AssertionError(f"{name}: expected websocket auth failure")
    except websockets.ConnectionClosed:
        print(f"{name}: rejected")
    except Exception as exc:
        exc_name = exc.__class__.__name__
        if exc_name in {"InvalidStatus", "InvalidStatusCode", "InvalidHandshake"}:
            print(f"{name}: rejected")
            return
        raise


async def expect_ws_snapshot(name: str, url: str) -> None:
    async with websockets.connect(url) as websocket:
        message = json.loads(await asyncio.wait_for(websocket.recv(), timeout=5))
        assert message["type"] == "ops_snapshot", message
        await websocket.send(json.dumps({"type": "ping"}))
        response = json.loads(await asyncio.wait_for(websocket.recv(), timeout=5))
        assert response == {"type": "pong"}, response
        print(f"{name}: snapshot")


async def main() -> None:
    admin_username = os.environ["BACKEND_ADMIN_USERNAME"]
    admin_password = os.environ["BACKEND_ADMIN_PASSWORD"]
    teacher_username = os.environ["TEACHER_USERNAME"]
    teacher_password = os.environ["TEACHER_PASSWORD"]
    gateway_ops_token = os.environ["GATEWAY_OPS_TOKEN"]

    expect_status("backend health", f"{BACKEND_BASE_URL}/healthz", 200)
    expect_status("gateway health", f"{GATEWAY_BASE_URL}/healthz", 200)
    expect_status("ops health", f"{OPS_BASE_URL}/healthz", 200)

    admin_login_body = expect_status(
        "backend admin login",
        f"{BACKEND_BASE_URL}/api/v1/auth/login",
        200,
        method="POST",
        data={"username": admin_username, "password": admin_password},
    )
    admin_access_token = json.loads(admin_login_body)["access_token"]
    admin_auth_header = {"Authorization": f"Bearer {admin_access_token}"}

    teacher_created = False
    try:
        expect_status(
            "create teacher user",
            f"{BACKEND_BASE_URL}/api/v1/users",
            201,
            method="POST",
            headers=admin_auth_header,
            data={
                "username": teacher_username,
                "password": teacher_password,
                "role": "teacher",
                "gym_ids": ["gym-gz-01"],
                "device_ids": [],
            },
        )
        teacher_created = True

        teacher_login_body = expect_status(
            "backend teacher login",
            f"{BACKEND_BASE_URL}/api/v1/auth/login",
            200,
            method="POST",
            data={"username": teacher_username, "password": teacher_password},
        )
        teacher_access_token = json.loads(teacher_login_body)["access_token"]
        teacher_auth_header = {"Authorization": f"Bearer {teacher_access_token}"}

        gateway_ops_body = expect_status(
            "gateway ops unauth",
            f"{GATEWAY_BASE_URL}/ops/v1/health",
            401,
        )
        assert "missing bearer token" in gateway_ops_body

        expect_status(
            "gateway ops invalid token",
            f"{GATEWAY_BASE_URL}/ops/v1/health",
            403,
            headers={"Authorization": "Bearer invalid-token"},
        )
        gateway_ops_ok_body = expect_status(
            "gateway ops valid token",
            f"{GATEWAY_BASE_URL}/ops/v1/health",
            200,
            headers={"Authorization": f"Bearer {gateway_ops_token}"},
        )
        assert json.loads(gateway_ops_ok_body)["module_id"].startswith("gateway:")

        ops_unauth_body = expect_status(
            "ops observer unauth",
            f"{OPS_BASE_URL}/api/v1/ops/health",
            401,
        )
        assert "missing bearer token" in ops_unauth_body

        expect_status(
            "ops observer teacher forbidden",
            f"{OPS_BASE_URL}/api/v1/ops/health",
            403,
            headers=teacher_auth_header,
        )
        ops_ok_body = expect_status(
            "ops observer admin access",
            f"{OPS_BASE_URL}/api/v1/ops/health",
            200,
            headers=admin_auth_header,
        )
        items = json.loads(ops_ok_body)["items"]
        module_ids = sorted(item["module_id"] for item in items)
        assert "backend:api-main" in module_ids
        assert "gateway:gw-001" in module_ids
        print("ops modules:", ",".join(module_ids))

        await expect_ws_failure("gateway ws unauth", f"ws://{os.environ['GATEWAY_SERVICE_HOST']}:8080/ops/ws")
        await expect_ws_snapshot(
            "gateway ws auth",
            f"ws://{os.environ['GATEWAY_SERVICE_HOST']}:8080/ops/ws?token={gateway_ops_token}",
        )
        await expect_ws_failure("ops ws unauth", f"ws://{os.environ['OPS_SERVICE_HOST']}:8090/api/ws/ops")
        await expect_ws_failure(
            "ops ws teacher forbidden",
            f"ws://{os.environ['OPS_SERVICE_HOST']}:8090/api/ws/ops?token={teacher_access_token}",
        )
        await expect_ws_snapshot(
            "ops ws admin",
            f"ws://{os.environ['OPS_SERVICE_HOST']}:8090/api/ws/ops?token={admin_access_token}",
        )
    finally:
        if teacher_created:
            expect_status(
                "delete teacher user",
                f"{BACKEND_BASE_URL}/api/v1/users/{teacher_username}",
                200,
                method="DELETE",
                headers=admin_auth_header,
            )


asyncio.run(main())
PY
