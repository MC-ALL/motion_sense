#!/bin/sh
set -eu

network_name="${CONTAINER_NETWORK:-motion-sense-local}"
backend_host_port="${BACKEND_HOST_PORT:-18000}"
gateway_host_port="${GATEWAY_HOST_PORT:-18080}"
ops_host_port="${OPS_OBSERVER_HOST_PORT:-18090}"
gateway_ops_token_path="${GATEWAY_OPS_TOKEN_PATH:-${PWD}/gateway/deployment/compose/runtime/secrets/edge_processor_ops_token.txt}"
backend_bootstrap_admin_path="${BACKEND_BOOTSTRAP_ADMIN_PATH:-${PWD}/backend/deployment/compose/runtime/config/backend/api_service/bootstrap_admin.txt}"
backend_admin_username="${BACKEND_ADMIN_USERNAME:-}"
backend_admin_password="${BACKEND_ADMIN_PASSWORD:-}"
teacher_username="ops_auth_teacher_$(date +%s)"
teacher_password="teacher123"

request_status() {
  url="$1"
  auth_header="${2:-}"
  if [ -n "${auth_header}" ]; then
    curl -sS -o /dev/null -w '%{http_code}' -H "${auth_header}" "${url}" || true
    return
  fi
  curl -sS -o /dev/null -w '%{http_code}' "${url}" || true
}

wait_for_http_ok() {
  url="$1"
  max_attempts="${2:-60}"
  attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    attempt=$((attempt + 1))
  done
  echo "timeout waiting for ${url}" >&2
  return 1
}

cleanup() {
  if [ -n "${admin_auth_header:-}" ]; then
    curl -fsS -X DELETE \
      -H "${admin_auth_header}" \
      "http://127.0.0.1:${backend_host_port}/api/v1/users/${teacher_username}" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

wait_for_http_ok "http://127.0.0.1:${backend_host_port}/healthz" 30
wait_for_http_ok "http://127.0.0.1:${gateway_host_port}/healthz" 30
wait_for_http_ok "http://127.0.0.1:${ops_host_port}/healthz" 30

if [ ! -f "${gateway_ops_token_path}" ]; then
  echo "missing gateway ops token: ${gateway_ops_token_path}" >&2
  exit 1
fi

gateway_ops_token="$(tr -d '\r\n' < "${gateway_ops_token_path}")"

if [ -z "${backend_admin_username}" ] && [ -f "${backend_bootstrap_admin_path}" ]; then
  backend_admin_username="$(sed -n 's/^username: //p' "${backend_bootstrap_admin_path}" | head -n 1)"
fi

if [ -z "${backend_admin_password}" ] && [ -f "${backend_bootstrap_admin_path}" ]; then
  backend_admin_password="$(sed -n 's/^password: //p' "${backend_bootstrap_admin_path}" | head -n 1)"
fi

backend_admin_username="${backend_admin_username:-admin}"

if [ -z "${backend_admin_password}" ]; then
  echo "missing backend admin password; set BACKEND_ADMIN_PASSWORD or ensure bootstrap_admin.txt exists" >&2
  exit 1
fi

admin_login_json="$(curl -fsS -X POST "http://127.0.0.1:${backend_host_port}/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"${backend_admin_username}\",\"password\":\"${backend_admin_password}\"}")"
admin_access_token="$(BODY_JSON="${admin_login_json}" python3 -c 'import json, os; print(json.loads(os.environ["BODY_JSON"])["access_token"])')"
admin_auth_header="Authorization: Bearer ${admin_access_token}"

curl -fsS -X POST "http://127.0.0.1:${backend_host_port}/api/v1/users" \
  -H "${admin_auth_header}" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"${teacher_username}\",\"password\":\"${teacher_password}\",\"role\":\"teacher\",\"gym_ids\":[\"gym-gz-01\"],\"device_ids\":[]}" >/dev/null

teacher_login_json="$(curl -fsS -X POST "http://127.0.0.1:${backend_host_port}/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"${teacher_username}\",\"password\":\"${teacher_password}\"}")"
teacher_access_token="$(BODY_JSON="${teacher_login_json}" python3 -c 'import json, os; print(json.loads(os.environ["BODY_JSON"])["access_token"])')"
teacher_auth_header="Authorization: Bearer ${teacher_access_token}"

[ "$(request_status "http://127.0.0.1:${gateway_host_port}/ops/v1/health")" = "401" ]
[ "$(request_status "http://127.0.0.1:${gateway_host_port}/ops/v1/health" "Authorization: Bearer invalid-token")" = "403" ]
gateway_ops_json="$(curl -fsS -H "Authorization: Bearer ${gateway_ops_token}" "http://127.0.0.1:${gateway_host_port}/ops/v1/health")"
BODY_JSON="${gateway_ops_json}" python3 -c 'import json, os; body=json.loads(os.environ["BODY_JSON"]); assert body["module_id"].startswith("gateway:")'

[ "$(request_status "http://127.0.0.1:${ops_host_port}/api/v1/ops/health")" = "401" ]
[ "$(request_status "http://127.0.0.1:${ops_host_port}/api/v1/ops/health" "${teacher_auth_header}")" = "403" ]
ops_health_json="$(curl -fsS -H "${admin_auth_header}" "http://127.0.0.1:${ops_host_port}/api/v1/ops/health")"
BODY_JSON="${ops_health_json}" python3 -c 'import json, os; body=json.loads(os.environ["BODY_JSON"]); assert len(body["items"]) >= 2'

container run --remove --network "${network_name}" \
  --entrypoint python \
  --env "GATEWAY_WS_BAD_URL=ws://edge_processor:8080/ops/ws" \
  --env "GATEWAY_WS_OK_URL=ws://edge_processor:8080/ops/ws?token=${gateway_ops_token}" \
  motion-sense-backend-api-local \
  - <<'PY'
from __future__ import annotations

import asyncio
import json
import os

import websockets


async def expect_failure(url: str) -> None:
    try:
        async with websockets.connect(url) as websocket:
            try:
                await asyncio.wait_for(websocket.recv(), timeout=3)
            except websockets.ConnectionClosed:
                return
            raise AssertionError(f"expected auth failure: {url}")
    except Exception:
        return


async def expect_snapshot(url: str) -> None:
    async with websockets.connect(url) as websocket:
        message = json.loads(await asyncio.wait_for(websocket.recv(), timeout=5))
        assert message["type"] == "ops_snapshot"
        await websocket.send(json.dumps({"type": "ping"}))
        assert json.loads(await asyncio.wait_for(websocket.recv(), timeout=5)) == {"type": "pong"}


async def main() -> None:
    await expect_failure(os.environ["GATEWAY_WS_BAD_URL"])
    await expect_snapshot(os.environ["GATEWAY_WS_OK_URL"])


asyncio.run(main())
PY

container run --remove --network "${network_name}" \
  --entrypoint python \
  --env "OPS_WS_BAD_URL=ws://ops_observer:8090/api/ws/ops" \
  --env "OPS_WS_TEACHER_URL=ws://ops_observer:8090/api/ws/ops?token=${teacher_access_token}" \
  --env "OPS_WS_ADMIN_URL=ws://ops_observer:8090/api/ws/ops?token=${admin_access_token}" \
  motion-sense-backend-api-local \
  - <<'PY'
from __future__ import annotations

import asyncio
import json
import os

import websockets


async def expect_failure(url: str) -> None:
    try:
        async with websockets.connect(url) as websocket:
            try:
                await asyncio.wait_for(websocket.recv(), timeout=3)
            except websockets.ConnectionClosed:
                return
            raise AssertionError(f"expected auth failure: {url}")
    except Exception:
        return


async def expect_snapshot(url: str) -> None:
    async with websockets.connect(url) as websocket:
        message = json.loads(await asyncio.wait_for(websocket.recv(), timeout=5))
        assert message["type"] == "ops_snapshot"
        await websocket.send(json.dumps({"type": "ping"}))
        assert json.loads(await asyncio.wait_for(websocket.recv(), timeout=5)) == {"type": "pong"}


async def main() -> None:
    await expect_failure(os.environ["OPS_WS_BAD_URL"])
    await expect_failure(os.environ["OPS_WS_TEACHER_URL"])
    await expect_snapshot(os.environ["OPS_WS_ADMIN_URL"])


asyncio.run(main())
PY

printf 'gateway ops 鉴权验证通过: %s\n' "${gateway_ops_json}"
printf 'ops_observer 鉴权验证通过: %s\n' "${ops_health_json}"
