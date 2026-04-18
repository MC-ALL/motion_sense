#!/bin/sh
set -eu

compose_file="${COMPOSE_FILE_PATH:-deployment/compose/docker-compose.yaml}"
backend_service="${BACKEND_SERVICE_NAME:-backend_api_service}"
gateway_service="${GATEWAY_SERVICE_NAME:-gateway_edge_processor}"
ops_service="${OPS_SERVICE_NAME:-ops_observer_api_service}"
web_service="${WEB_SERVICE_NAME:-web_portal_app}"
gateway_id="${EDGE_PROCESSOR_GATEWAY_ID:-gw-001}"
gym_id="${EDGE_PROCESSOR_GYM_ID:-gym-gz-01}"
suffix="$(date +%s)"
eq_device_id="eq-system-${suffix}"
env_device_id="env-system-${suffix}"

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
require_running_service "${web_service}"

backend_bootstrap="$(
  docker compose -f "${compose_file}" exec -T "${backend_service}" \
    sh -lc 'cat /runtime/config/backend/api_service/bootstrap_admin.txt'
)"

backend_admin_username="$(printf '%s\n' "${backend_bootstrap}" | sed -n 's/^username: //p' | head -n 1)"
backend_admin_password="$(printf '%s\n' "${backend_bootstrap}" | sed -n 's/^password: //p' | head -n 1)"

if [ -z "${backend_admin_username}" ] || [ -z "${backend_admin_password}" ]; then
  echo "failed to read backend bootstrap admin credentials from running container" >&2
  exit 1
fi

sample_payload_file="$(mktemp)"
cleanup() {
  rm -f "${sample_payload_file}"
}
trap cleanup EXIT INT TERM

current_ts="$(date +%s)"

cat > "${sample_payload_file}" <<EOF
{"ts":${current_ts},"device_id":"${eq_device_id}","status":"active","rep_count":12,"power_w":350.5,"gateway_id":"${gateway_id}"}
EOF

sh deployment/compose/publish_sample_telemetry.sh \
  "gym/${gym_id}/equipment/${eq_device_id}/telemetry" \
  "${sample_payload_file}"

docker compose -f "${compose_file}" exec -T \
  -e "BACKEND_ADMIN_USERNAME=${backend_admin_username}" \
  -e "BACKEND_ADMIN_PASSWORD=${backend_admin_password}" \
  -e "GATEWAY_SERVICE_HOST=${gateway_service}" \
  -e "OPS_SERVICE_HOST=${ops_service}" \
  -e "WEB_SERVICE_HOST=${web_service}" \
  -e "GATEWAY_ID=${gateway_id}" \
  -e "GYM_ID=${gym_id}" \
  -e "EQ_DEVICE_ID=${eq_device_id}" \
  -e "ENV_DEVICE_ID=${env_device_id}" \
  -e "CURRENT_TS=${current_ts}" \
  "${backend_service}" python - <<'PY'
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request


BACKEND_BASE_URL = "http://127.0.0.1:8000"
GATEWAY_BASE_URL = f"http://{os.environ['GATEWAY_SERVICE_HOST']}:8080"
OPS_BASE_URL = f"http://{os.environ['OPS_SERVICE_HOST']}:8090"
WEB_BASE_URL = f"http://{os.environ['WEB_SERVICE_HOST']}:8080"

BACKEND_ADMIN_USERNAME = os.environ["BACKEND_ADMIN_USERNAME"]
BACKEND_ADMIN_PASSWORD = os.environ["BACKEND_ADMIN_PASSWORD"]
GATEWAY_ID = os.environ["GATEWAY_ID"]
GYM_ID = os.environ["GYM_ID"]
EQ_DEVICE_ID = os.environ["EQ_DEVICE_ID"]
ENV_DEVICE_ID = os.environ["ENV_DEVICE_ID"]
CURRENT_TS = int(os.environ["CURRENT_TS"])


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


def wait_for_json(
    name: str,
    url: str,
    validator,
    *,
    headers: dict[str, str] | None = None,
    max_attempts: int = 60,
) -> object:
    for _ in range(max_attempts):
        status, body = request(url, headers=headers)
        if status == 200 and body:
            try:
                parsed = json.loads(body)
                result = validator(parsed)
                if result is False:
                    raise AssertionError
                print(f"{name}: ok")
                return parsed
            except Exception:
                pass
        time.sleep(1)
    raise AssertionError(f"timeout waiting for {name}: {url}")


def wait_for_text(
    name: str,
    url: str,
    validator,
    *,
    max_attempts: int = 60,
) -> str:
    for _ in range(max_attempts):
        status, body = request(url)
        if status == 200 and body:
            try:
                result = validator(body)
                if result is False:
                    raise AssertionError
                print(f"{name}: ok")
                return body
            except Exception:
                pass
        time.sleep(1)
    raise AssertionError(f"timeout waiting for {name}: {url}")


for name, url in [
    ("backend health", f"{BACKEND_BASE_URL}/healthz"),
    ("gateway health", f"{GATEWAY_BASE_URL}/healthz"),
    ("ops health", f"{OPS_BASE_URL}/healthz"),
    ("web root", f"{WEB_BASE_URL}/"),
]:
    status, _ = request(url)
    if status != 200:
        raise AssertionError(f"{name}: expected 200, got {status}")
    print(f"{name}: {status}")

login_status, login_body = request(
    f"{BACKEND_BASE_URL}/api/v1/auth/login",
    method="POST",
    data={"username": BACKEND_ADMIN_USERNAME, "password": BACKEND_ADMIN_PASSWORD},
)
if login_status != 200:
    raise AssertionError(f"backend admin login failed: {login_status} {login_body}")
print("backend admin login: 200")
access_token = json.loads(login_body)["access_token"]
auth_headers = {"Authorization": f"Bearer {access_token}"}

device_json = wait_for_json(
    "device ingest",
    f"{BACKEND_BASE_URL}/api/v1/devices/{EQ_DEVICE_ID}",
    lambda body: (
        body["device_id"] == EQ_DEVICE_ID
        and body["online"] is True
        and isinstance(body["last_payload"].get("gateway_received_ts"), int)
    ),
    headers=auth_headers,
)

health_detail_json = wait_for_json(
    "gateway health detail",
    f"{BACKEND_BASE_URL}/api/v1/system/health/{GATEWAY_ID}",
    lambda body: body["gateway_id"] == GATEWAY_ID and len(body["components"]) >= 5,
    headers=auth_headers,
)

register_status, register_body = request(
    f"{BACKEND_BASE_URL}/api/v1/devices",
    method="POST",
    headers=auth_headers,
    data={
        "gym_id": GYM_ID,
        "device_type": "env",
        "device_id": ENV_DEVICE_ID,
        "gateway_id": GATEWAY_ID,
        "display_name": f"环境节点 {ENV_DEVICE_ID}",
        "location": "系统回归验证",
    },
)
if register_status not in {200, 201}:
    raise AssertionError(f"register device failed: {register_status} {register_body}")
registered_device_json = json.loads(register_body)
print(f"device register: {register_status}")

command_status, command_body = request(
    f"{BACKEND_BASE_URL}/api/v1/devices/{ENV_DEVICE_ID}/config",
    method="POST",
    headers=auth_headers,
    data={"config": {"telemetry_interval_s": 20}},
)
if command_status != 200:
    raise AssertionError(f"publish config failed: {command_status} {command_body}")
command_id = json.loads(command_body)["command_id"]
print("config command publish: 200")

command_detail_json = wait_for_json(
    "config command detail",
    f"{BACKEND_BASE_URL}/api/v1/gateway/commands/{command_id}",
    lambda body: body["command_id"] == command_id and body["status"] == "succeeded",
    headers=auth_headers,
)

summary_json = wait_for_json(
    "system health summary",
    f"{BACKEND_BASE_URL}/api/v1/system/health",
    lambda body: len(body) >= 1 and any(item["gateway_id"] == GATEWAY_ID for item in body),
    headers=auth_headers,
)

ops_health_json = wait_for_json(
    "ops observer health",
    f"{OPS_BASE_URL}/api/v1/ops/health",
    lambda body: (
        any(item["module_id"] == "gateway:gw-001" and item["health_status"] == "healthy" for item in body["items"])
        and any(item["module_id"] == "backend:api-main" and item["health_status"] == "healthy" for item in body["items"])
    ),
    headers=auth_headers,
)

ops_detail_json = wait_for_json(
    "ops observer detail",
    f"{OPS_BASE_URL}/api/v1/ops/health/gateway:gw-001",
    lambda body: body["summary"]["module_id"] == "gateway:gw-001" and len(body["components"]) >= 1,
    headers=auth_headers,
)

web_runtime_config = wait_for_text(
    "web runtime config",
    f"{WEB_BASE_URL}/runtime_config.js",
    lambda body: (
        "backend_base_url" in body
        and "ops_base_url" in body
        and "127.0.0.1:8000" in body
        and "127.0.0.1:8090" in body
    ),
)

web_index_html = wait_for_text(
    "web index",
    f"{WEB_BASE_URL}/",
    lambda body: ("粤动智感运维门户" in body) or ("root" in body.lower()),
)

print("device json:", json.dumps(device_json, ensure_ascii=False))
print("health detail json:", json.dumps(health_detail_json, ensure_ascii=False))
print("registered device json:", json.dumps(registered_device_json, ensure_ascii=False))
print("command detail json:", json.dumps(command_detail_json, ensure_ascii=False))
print("summary json:", json.dumps(summary_json, ensure_ascii=False))
print("ops health json:", json.dumps(ops_health_json, ensure_ascii=False))
print("ops detail json:", json.dumps(ops_detail_json, ensure_ascii=False))
print("web runtime config:", web_runtime_config)
print("web index html length:", len(web_index_html))
PY
