#!/bin/sh
set -eu

compose_file="${COMPOSE_FILE_PATH:-deployment/compose/docker-compose.yaml}"
backend_service="${BACKEND_SERVICE_NAME:-backend_api_service}"
gateway_service="${GATEWAY_SERVICE_NAME:-gateway_edge_processor}"
mosquitto_service="${MOSQUITTO_SERVICE_NAME:-gateway_mosquitto}"
gateway_id="${EDGE_PROCESSOR_GATEWAY_ID:-gw-001}"
gym_id="${EDGE_PROCESSOR_GYM_ID:-gym-gz-01}"
suffix="$(date +%s)"
burst_prefix="eq-batch-burst-${suffix}"
burst_ts="$(date +%s)"

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
require_running_service "${mosquitto_service}"

backend_bootstrap="$(
  docker compose -f "${compose_file}" exec -T "${backend_service}" \
    sh -lc 'cat /runtime/config/backend/api_service/bootstrap_admin.txt'
)"
gateway_ops_token="$(
  docker compose -f "${compose_file}" exec -T "${gateway_service}" \
    sh -lc 'cat /runtime/secrets/edge_processor_ops_token.txt'
)"
batch_min_window_s="$(
  docker compose -f "${compose_file}" exec -T "${gateway_service}" \
    sh -lc "sed -n 's/^batch_min_window_s: //p' /runtime/config/edge_processor/app_settings.yaml | head -n 1"
)"
batch_trigger_threshold="$(
  docker compose -f "${compose_file}" exec -T "${gateway_service}" \
    sh -lc "sed -n 's/^batch_trigger_threshold: //p' /runtime/config/edge_processor/app_settings.yaml | head -n 1"
)"

backend_admin_username="$(printf '%s\n' "${backend_bootstrap}" | sed -n 's/^username: //p' | head -n 1)"
backend_admin_password="$(printf '%s\n' "${backend_bootstrap}" | sed -n 's/^password: //p' | head -n 1)"
gateway_ops_token="$(printf '%s\n' "${gateway_ops_token}" | tr -d '\r\n')"
batch_min_window_s="$(printf '%s\n' "${batch_min_window_s}" | tr -d '\r\n')"
batch_trigger_threshold="$(printf '%s\n' "${batch_trigger_threshold}" | tr -d '\r\n')"

if [ -z "${backend_admin_username}" ] || [ -z "${backend_admin_password}" ]; then
  echo "failed to read backend bootstrap admin credentials from running container" >&2
  exit 1
fi

if [ -z "${gateway_ops_token}" ] || [ -z "${batch_min_window_s}" ] || [ -z "${batch_trigger_threshold}" ]; then
  echo "failed to read gateway batch settings or ops token from running container" >&2
  exit 1
fi

(
  sleep 1
  docker compose -f "${compose_file}" exec -T \
    -e "GYM_ID=${gym_id}" \
    -e "GATEWAY_ID=${gateway_id}" \
    -e "BURST_PREFIX=${burst_prefix}" \
    -e "BURST_COUNT=${batch_trigger_threshold}" \
    -e "BURST_TS=${burst_ts}" \
    "${mosquitto_service}" sh -lc '
      i=1
      while [ "$i" -le "$BURST_COUNT" ]; do
        topic="gym/${GYM_ID}/equipment/${BURST_PREFIX}-${i}/telemetry"
        payload="$(printf "{\"ts\":%s,\"device_id\":\"%s-%s\",\"status\":\"active\",\"rep_count\":%s,\"power_w\":350.5,\"gateway_id\":\"%s\"}" "$((BURST_TS + i))" "${BURST_PREFIX}" "$i" "$i" "${GATEWAY_ID}")"
        printf "%s" "${payload}" | /usr/bin/mosquitto_pub \
          -h 127.0.0.1 \
          -p 1883 \
          -u admin \
          -P admin123 \
          -t "${topic}" \
          -s
        i=$((i + 1))
      done
    '
) &
publisher_pid="$!"

docker compose -f "${compose_file}" exec -T \
  -e "BACKEND_ADMIN_USERNAME=${backend_admin_username}" \
  -e "BACKEND_ADMIN_PASSWORD=${backend_admin_password}" \
  -e "GATEWAY_OPS_TOKEN=${gateway_ops_token}" \
  -e "GATEWAY_SERVICE_HOST=${gateway_service}" \
  -e "GATEWAY_ID=${gateway_id}" \
  -e "BURST_PREFIX=${burst_prefix}" \
  -e "BURST_COUNT=${batch_trigger_threshold}" \
  -e "BATCH_MIN_WINDOW_S=${batch_min_window_s}" \
  "${backend_service}" python - <<'PY'
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request


BACKEND_BASE_URL = "http://127.0.0.1:8000"
GATEWAY_BASE_URL = f"http://{os.environ['GATEWAY_SERVICE_HOST']}:8080"
BACKEND_ADMIN_USERNAME = os.environ["BACKEND_ADMIN_USERNAME"]
BACKEND_ADMIN_PASSWORD = os.environ["BACKEND_ADMIN_PASSWORD"]
GATEWAY_OPS_TOKEN = os.environ["GATEWAY_OPS_TOKEN"]
GATEWAY_ID = os.environ["GATEWAY_ID"]
BURST_PREFIX = os.environ["BURST_PREFIX"]
BURST_COUNT = int(os.environ["BURST_COUNT"])
BATCH_MIN_WINDOW_S = float(os.environ["BATCH_MIN_WINDOW_S"])


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
    sleep_s: float = 1.0,
):
    for _ in range(max_attempts):
        status, body = request(url, headers=headers)
        if status == 200 and body:
            try:
                payload = json.loads(body)
                if validator(payload):
                    print(f"{name}: ok")
                    return payload
            except Exception:
                pass
        time.sleep(sleep_s)
    raise AssertionError(f"timeout waiting for {name}: {url}")


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
gateway_ops_headers = {"Authorization": f"Bearer {GATEWAY_OPS_TOKEN}"}

initial_stats_status, initial_stats_body = request(
    f"{GATEWAY_BASE_URL}/ops/v1/stats",
    headers=gateway_ops_headers,
)
if initial_stats_status != 200:
    raise AssertionError(f"gateway ops stats failed: {initial_stats_status} {initial_stats_body}")
initial_stats = json.loads(initial_stats_body)
initial_batch_success_total = int(initial_stats["batch_upload_success_total"])

if BATCH_MIN_WINDOW_S <= 0:
    raise AssertionError(f"unexpected batch_min_window_s: {BATCH_MIN_WINDOW_S}")
if BURST_COUNT < 2:
    raise AssertionError(f"unexpected batch_trigger_threshold: {BURST_COUNT}")
print(f"gateway batch settings: min_window={BATCH_MIN_WINDOW_S}s threshold={BURST_COUNT}")

wait_for_json(
    "gateway batch stats",
    f"{GATEWAY_BASE_URL}/ops/v1/stats",
    lambda body: (
        body["gateway_id"] == GATEWAY_ID
        and int(body["batch_upload_success_total"]) > initial_batch_success_total
        and int(body["last_batch_size"]) == BURST_COUNT
        and body["last_batch_uploaded_at"] is not None
    ),
    headers=gateway_ops_headers,
    max_attempts=45,
    sleep_s=0.5,
)

for index in range(1, BURST_COUNT + 1):
    device_id = f"{BURST_PREFIX}-{index}"
    wait_for_json(
        f"backend device {device_id}",
        f"{BACKEND_BASE_URL}/api/v1/devices/{device_id}",
        lambda body, expected=device_id: (
            body["device_id"] == expected
            and body["online"] is True
            and body["last_payload"]["gateway_id"] == GATEWAY_ID
        ),
        headers=auth_headers,
        max_attempts=45,
        sleep_s=0.5,
    )
PY

wait "${publisher_pid}"

echo "verify_gateway_batch_stack: ok"
