#!/bin/sh
set -eu

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
compose_file="${COMPOSE_FILE_PATH:-${script_dir}/docker-compose.yaml}"
wait_timeout_s="${WAIT_TIMEOUT_S:-240}"
poll_interval_s="${POLL_INTERVAL_S:-2}"
compose_up_log_path="${COMPOSE_UP_LOG_PATH:-/tmp/motion_sense.compose.up.log}"

runtime_init_service="${RUNTIME_INIT_SERVICE_NAME:-runtime_init}"
backend_service="${BACKEND_SERVICE_NAME:-backend_api_service}"
gateway_service="${GATEWAY_SERVICE_NAME:-gateway_edge_processor}"
ops_service="${OPS_SERVICE_NAME:-ops_observer_api_service}"
web_service="${WEB_SERVICE_NAME:-web_portal_app}"

main_services="
backend_timescaledb
backend_redis
gateway_mosquitto
gateway_influxdb
backend_api_service
gateway_edge_processor
ops_observer_api_service
web_portal_app
"

elapsed_s=0

service_container_id() {
  docker compose -f "${compose_file}" ps -q "$1"
}

service_container_id_all() {
  docker compose -f "${compose_file}" ps -a -q "$1"
}

wait_for_runtime_init() {
  service_name="$1"
  elapsed_s=0
  while [ "${elapsed_s}" -lt "${wait_timeout_s}" ]; do
    container_id="$(service_container_id_all "${service_name}")"
    if [ -n "${container_id}" ]; then
      status="$(docker inspect -f '{{.State.Status}}' "${container_id}")"
      exit_code="$(docker inspect -f '{{.State.ExitCode}}' "${container_id}")"
      if [ "${status}" = "exited" ] && [ "${exit_code}" = "0" ]; then
        printf 'runtime init ready: %s\n' "${service_name}"
        return 0
      fi
    fi
    sleep "${poll_interval_s}"
    elapsed_s=$((elapsed_s + poll_interval_s))
  done

  echo "timeout waiting for ${service_name} to complete successfully" >&2
  docker compose -f "${compose_file}" ps
  docker compose -f "${compose_file}" logs --tail=80 "${service_name}" || true
  return 1
}

wait_for_healthy_service() {
  service_name="$1"
  elapsed_s=0
  while [ "${elapsed_s}" -lt "${wait_timeout_s}" ]; do
    container_id="$(service_container_id "${service_name}")"
    if [ -n "${container_id}" ]; then
      status="$(docker inspect -f '{{.State.Status}}' "${container_id}")"
      health_status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${container_id}")"
      if [ "${status}" = "running" ] && { [ "${health_status}" = "healthy" ] || [ "${health_status}" = "none" ]; }; then
        printf 'service ready: %s (%s)\n' "${service_name}" "${health_status}"
        return 0
      fi
    fi
    sleep "${poll_interval_s}"
    elapsed_s=$((elapsed_s + poll_interval_s))
  done

  echo "timeout waiting for healthy service: ${service_name}" >&2
  docker compose -f "${compose_file}" ps
  docker compose -f "${compose_file}" logs --tail=120 "${service_name}" || true
  return 1
}

print_runtime_summary() {
  backend_bootstrap="$(
    docker compose -f "${compose_file}" exec -T "${backend_service}" \
      sh -lc 'cat /runtime/config/backend/api_service/bootstrap_admin.txt'
  )"
  backend_admin_username="$(printf '%s\n' "${backend_bootstrap}" | sed -n 's/^username: //p' | head -n 1)"
  backend_admin_password="$(printf '%s\n' "${backend_bootstrap}" | sed -n 's/^password: //p' | head -n 1)"

  docker compose -f "${compose_file}" exec -T \
    -e "BACKEND_ADMIN_USERNAME=${backend_admin_username}" \
    -e "BACKEND_ADMIN_PASSWORD=${backend_admin_password}" \
    -e "GATEWAY_SERVICE_HOST=${gateway_service}" \
    -e "OPS_SERVICE_HOST=${ops_service}" \
    -e "WEB_SERVICE_HOST=${web_service}" \
    "${backend_service}" python - <<'PY'
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

backend_base_url = "http://127.0.0.1:8000"
gateway_base_url = f"http://{os.environ['GATEWAY_SERVICE_HOST']}:8080"
ops_base_url = f"http://{os.environ['OPS_SERVICE_HOST']}:8090"
web_base_url = f"http://{os.environ['WEB_SERVICE_HOST']}:8080"


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
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


for name, url in [
    ("backend", f"{backend_base_url}/healthz"),
    ("gateway", f"{gateway_base_url}/healthz"),
    ("ops", f"{ops_base_url}/healthz"),
    ("web", f"{web_base_url}/"),
]:
    status, _ = request(url)
    print(f"{name} health: {status}")

login_status, login_body = request(
    f"{backend_base_url}/api/v1/auth/login",
    method="POST",
    data={
        "username": os.environ["BACKEND_ADMIN_USERNAME"],
        "password": os.environ["BACKEND_ADMIN_PASSWORD"],
    },
)
if login_status != 200:
    raise SystemExit(f"backend admin login failed: {login_status} {login_body}")

access_token = json.loads(login_body)["access_token"]
ops_status, ops_body = request(
    f"{ops_base_url}/api/v1/ops/health",
    headers={"Authorization": f"Bearer {access_token}"},
)
if ops_status != 200:
    raise SystemExit(f"ops observer summary failed: {ops_status} {ops_body}")

ops_payload = json.loads(ops_body)
print("ops modules:")
for item in ops_payload["items"]:
    print(
        f"  {item['module_id']}: "
        f"online={item['online']} "
        f"health={item['health_status']} "
        f"components={item['healthy_components']}/{item['component_total']}"
    )
PY
}

printf 'building compose images: %s\n' "${compose_file}"
docker compose -f "${compose_file}" build

printf 'starting compose services: %s\n' "${compose_file}"
docker compose -f "${compose_file}" up -d >"${compose_up_log_path}" 2>&1 &
compose_up_pid="$!"

wait_for_runtime_init "${runtime_init_service}"

for service_name in ${main_services}; do
  wait_for_healthy_service "${service_name}"
done

printf '\ncompose services:\n'
docker compose -f "${compose_file}" ps

printf '\nbootstrap info:\n'
COMPOSE_FILE_PATH="${compose_file}" sh "${script_dir}/print_bootstrap_credentials.sh"

printf '\nstack summary:\n'
print_runtime_summary

if kill -0 "${compose_up_pid}" >/dev/null 2>&1; then
  printf '\nnote: docker compose up is still finalizing in background, recent output stored at %s\n' "${compose_up_log_path}"
fi
