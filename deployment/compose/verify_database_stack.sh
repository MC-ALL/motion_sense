#!/bin/sh
set -eu

compose_file="${COMPOSE_FILE_PATH:-deployment/compose/docker-compose.yaml}"
backend_service="${BACKEND_SERVICE_NAME:-backend_api_service}"
gateway_service="${GATEWAY_SERVICE_NAME:-gateway_edge_processor}"
timescaledb_service="${TIMESCALEDB_SERVICE_NAME:-backend_timescaledb}"
redis_service="${REDIS_SERVICE_NAME:-backend_redis}"
influxdb_service="${INFLUXDB_SERVICE_NAME:-gateway_influxdb}"
postgres_password="${BACKEND_DATABASE_PASSWORD:-change_me_at_deploy}"
gateway_id="${EDGE_PROCESSOR_GATEWAY_ID:-gw-001}"
gym_id="${EDGE_PROCESSOR_GYM_ID:-gym-gz-01}"
suffix="$(date +%s)"
eq_device_id="eq-db-${suffix}"
wb_device_id="wb-db-${suffix}"
env_device_id="env-db-${suffix}"

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

for service in \
  "${backend_service}" \
  "${gateway_service}" \
  "${timescaledb_service}" \
  "${redis_service}" \
  "${influxdb_service}"
do
  require_running_service "${service}"
done

backend_bootstrap="$(
  docker compose -f "${compose_file}" exec -T "${backend_service}" \
    sh -lc 'cat /runtime/config/backend/api_service/bootstrap_admin.txt'
)"
influxdb_admin_token="$(
  docker compose -f "${compose_file}" exec -T "${influxdb_service}" \
    sh -lc 'cat /runtime/config/influxdb/admin_token.txt'
)"

backend_admin_username="$(printf '%s\n' "${backend_bootstrap}" | sed -n 's/^username: //p' | head -n 1)"
backend_admin_password="$(printf '%s\n' "${backend_bootstrap}" | sed -n 's/^password: //p' | head -n 1)"
influxdb_admin_token="$(printf '%s\n' "${influxdb_admin_token}" | tr -d '\r\n')"

if [ -z "${backend_admin_username}" ] || [ -z "${backend_admin_password}" ]; then
  echo "failed to read backend bootstrap admin credentials from running container" >&2
  exit 1
fi

if [ -z "${influxdb_admin_token}" ]; then
  echo "failed to read influxdb admin token from running container" >&2
  exit 1
fi

query_timescaledb() {
  sql="$1"
  docker compose -f "${compose_file}" exec -T "${timescaledb_service}" sh -lc \
    "PGPASSWORD='${postgres_password}' psql -v ON_ERROR_STOP=1 -U motion_sense -d motion_sense -tAq" <<EOF
${sql}
EOF
}

query_influx_jsonl() {
  sql="$1"
  docker compose -f "${compose_file}" exec -T \
    -e "INFLUX_QUERY=${sql}" \
    -e "INFLUXDB_ADMIN_TOKEN=${influxdb_admin_token}" \
    "${backend_service}" python - <<'PY'
import json
import os
import urllib.request

payload = {
    "db": "gym_local",
    "q": os.environ["INFLUX_QUERY"],
    "format": "jsonl",
}
request = urllib.request.Request(
    "http://gateway_influxdb:8181/api/v3/query_sql",
    data=json.dumps(payload).encode(),
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.environ['INFLUXDB_ADMIN_TOKEN']}",
    },
    method="POST",
)
with urllib.request.urlopen(request, timeout=20) as response:
    print(response.read().decode(), end="")
PY
}

eq_ts="$(date +%s)"
wb_ts="$((eq_ts + 1))"
bind_ts="$((eq_ts + 2))"
unbind_ts="$((eq_ts + 7))"
env_ts="$((eq_ts + 3))"
alert_ts="$((eq_ts + 4))"

eq_payload_file="$(mktemp)"
wb_payload_file="$(mktemp)"
bind_payload_file="$(mktemp)"
unbind_payload_file="$(mktemp)"
env_payload_file="$(mktemp)"
alert_payload_file="$(mktemp)"

cleanup() {
  rm -f \
    "${eq_payload_file}" \
    "${wb_payload_file}" \
    "${bind_payload_file}" \
    "${unbind_payload_file}" \
    "${env_payload_file}" \
    "${alert_payload_file}"
}

trap cleanup EXIT INT TERM

cat > "${eq_payload_file}" <<EOF
{"ts":${eq_ts},"device_id":"${eq_device_id}","status":"active","rep_count":18,"power_w":412.4,"energy_wh":3.125,"gateway_id":"${gateway_id}"}
EOF

cat > "${wb_payload_file}" <<EOF
{"ts":${wb_ts},"device_id":"${wb_device_id}","heart_rate":92,"step_count":148,"battery_pct":87,"current_equipment_id":"${eq_device_id}","relayed_by":"${eq_device_id}"}
EOF

cat > "${bind_payload_file}" <<EOF
{"ts":${bind_ts},"wristband_id":"${wb_device_id}","equipment_id":"${eq_device_id}","gym_id":"${gym_id}","action":"bind","reason":"ble_connected"}
EOF

cat > "${unbind_payload_file}" <<EOF
{"ts":${unbind_ts},"wristband_id":"${wb_device_id}","equipment_id":"${eq_device_id}","gym_id":"${gym_id}","action":"unbind","reason":"idle_timeout"}
EOF

cat > "${env_payload_file}" <<EOF
{"ts":${env_ts},"node_id":"${env_device_id}","temperature":29.3,"humidity":61.2,"lux":412.5,"co2_ppm":1180,"pm1_0":24,"pm2_5":43,"pm10":62,"wifi_rssi":-58}
EOF

cat > "${alert_payload_file}" <<EOF
{"ts":${alert_ts},"device_id":"${env_device_id}","priority":"P1","level":"warning","code":"CO2_HIGH","message":"环境 CO2 超标","value":1180,"threshold":1000}
EOF

sh deployment/compose/publish_sample_telemetry.sh \
  "gym/${gym_id}/equipment/${eq_device_id}/telemetry" \
  "${eq_payload_file}"
sh deployment/compose/publish_sample_telemetry.sh \
  "gym/${gym_id}/wristband/${wb_device_id}/telemetry" \
  "${wb_payload_file}"
sh deployment/compose/publish_sample_telemetry.sh \
  "gym/${gym_id}/wristband/${wb_device_id}/binding" \
  "${bind_payload_file}"
sh deployment/compose/publish_sample_telemetry.sh \
  "gym/${gym_id}/wristband/${wb_device_id}/binding" \
  "${unbind_payload_file}"
sh deployment/compose/publish_sample_telemetry.sh \
  "gym/${gym_id}/env/${env_device_id}/telemetry" \
  "${env_payload_file}"
sh deployment/compose/publish_sample_telemetry.sh \
  "gym/${gym_id}/env/${env_device_id}/alert" \
  "${alert_payload_file}"

api_output="$(
  docker compose -f "${compose_file}" exec -T \
    -e "BACKEND_ADMIN_USERNAME=${backend_admin_username}" \
    -e "BACKEND_ADMIN_PASSWORD=${backend_admin_password}" \
    -e "GATEWAY_ID=${gateway_id}" \
    -e "GYM_ID=${gym_id}" \
    -e "EQ_DEVICE_ID=${eq_device_id}" \
    -e "WB_DEVICE_ID=${wb_device_id}" \
    -e "ENV_DEVICE_ID=${env_device_id}" \
    -e "EQ_TS=${eq_ts}" \
    -e "WB_TS=${wb_ts}" \
    -e "ENV_TS=${env_ts}" \
    "${backend_service}" python - <<'PY'
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

BACKEND_BASE_URL = "http://127.0.0.1:8000"
BACKEND_ADMIN_USERNAME = os.environ["BACKEND_ADMIN_USERNAME"]
BACKEND_ADMIN_PASSWORD = os.environ["BACKEND_ADMIN_PASSWORD"]
GATEWAY_ID = os.environ["GATEWAY_ID"]
GYM_ID = os.environ["GYM_ID"]
EQ_DEVICE_ID = os.environ["EQ_DEVICE_ID"]
WB_DEVICE_ID = os.environ["WB_DEVICE_ID"]
ENV_DEVICE_ID = os.environ["ENV_DEVICE_ID"]
EQ_TS = int(os.environ["EQ_TS"])
WB_TS = int(os.environ["WB_TS"])
ENV_TS = int(os.environ["ENV_TS"])


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
    max_attempts: int = 90,
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


login_status, login_body = request(
    f"{BACKEND_BASE_URL}/api/v1/auth/login",
    method="POST",
    data={"username": BACKEND_ADMIN_USERNAME, "password": BACKEND_ADMIN_PASSWORD},
)
if login_status != 200:
    raise AssertionError(f"backend admin login failed: {login_status} {login_body}")
print("backend admin login: 200")
login_json = json.loads(login_body)
access_token = login_json["access_token"]
refresh_token = login_json["refresh_token"]
auth_headers = {"Authorization": f"Bearer {access_token}"}

refresh_status, refresh_body = request(
    f"{BACKEND_BASE_URL}/api/v1/auth/refresh",
    method="POST",
    data={"refresh_token": refresh_token},
)
if refresh_status != 200:
    raise AssertionError(f"backend refresh failed: {refresh_status} {refresh_body}")
refresh_json = json.loads(refresh_body)
assert refresh_json["refresh_token"] != refresh_token
print("backend refresh: 200")
print(f"ROTATED_REFRESH_TOKEN={refresh_json['refresh_token']}")

wait_for_json(
    "device eq",
    f"{BACKEND_BASE_URL}/api/v1/devices/{EQ_DEVICE_ID}",
    lambda body: body["device_id"] == EQ_DEVICE_ID and body["online"] is True,
    headers=auth_headers,
)
wait_for_json(
    "device wb",
    f"{BACKEND_BASE_URL}/api/v1/devices/{WB_DEVICE_ID}",
    lambda body: body["device_id"] == WB_DEVICE_ID and body["online"] is True,
    headers=auth_headers,
)
wait_for_json(
    "device env",
    f"{BACKEND_BASE_URL}/api/v1/devices/{ENV_DEVICE_ID}",
    lambda body: body["device_id"] == ENV_DEVICE_ID and body["online"] is True,
    headers=auth_headers,
)

wait_for_json(
    "equipment telemetry",
    f"{BACKEND_BASE_URL}/api/v1/telemetry/equipment/{EQ_DEVICE_ID}",
    lambda body: any(item["payload"].get("ts") == EQ_TS and item["payload"].get("power_w") == 412.4 for item in body),
    headers=auth_headers,
)
wait_for_json(
    "wristband telemetry",
    f"{BACKEND_BASE_URL}/api/v1/telemetry/wristband/{WB_DEVICE_ID}",
    lambda body: any(item["payload"].get("ts") == WB_TS and item["payload"].get("heart_rate") == 92 for item in body),
    headers=auth_headers,
)
wait_for_json(
    "env telemetry",
    f"{BACKEND_BASE_URL}/api/v1/telemetry/env/{ENV_DEVICE_ID}",
    lambda body: any(item["payload"].get("ts") == ENV_TS and item["payload"].get("co2_ppm") == 1180 for item in body),
    headers=auth_headers,
)
wait_for_json(
    "alerts",
    f"{BACKEND_BASE_URL}/api/v1/alerts?device_id={ENV_DEVICE_ID}",
    lambda body: any(item["code"] == "CO2_HIGH" and item["priority"] == "P1" for item in body),
    headers=auth_headers,
)
wait_for_json(
    "bindings",
    f"{BACKEND_BASE_URL}/api/v1/wristband/{WB_DEVICE_ID}/bindings",
    lambda body: any(item["action"] == "bind" for item in body) and any(item["action"] == "unbind" and (item.get("duration_s") or 0) >= 5 for item in body),
    headers=auth_headers,
)

command_status, command_body = request(
    f"{BACKEND_BASE_URL}/api/v1/devices/{ENV_DEVICE_ID}/config",
    method="POST",
    headers=auth_headers,
    data={"config": {"telemetry_interval_s": 25}, "gateway_id": GATEWAY_ID, "device_type": "env", "gym_id": GYM_ID},
)
if command_status != 200:
    raise AssertionError(f"publish config failed: {command_status} {command_body}")
command_json = json.loads(command_body)
command_id = command_json["command_id"]
print("config command publish: 200")
print(f"COMMAND_ID={command_id}")

wait_for_json(
    "command detail",
    f"{BACKEND_BASE_URL}/api/v1/gateway/commands/{command_id}",
    lambda body: body["command_id"] == command_id and body["status"] == "succeeded",
    headers=auth_headers,
)
wait_for_json(
    "gateway health detail",
    f"{BACKEND_BASE_URL}/api/v1/system/health/{GATEWAY_ID}",
    lambda body: body["gateway_id"] == GATEWAY_ID and len(body["components"]) >= 5,
    headers=auth_headers,
)
PY
)"

printf '%s\n' "${api_output}"

command_id="$(printf '%s\n' "${api_output}" | sed -n 's/^COMMAND_ID=//p' | tail -n 1)"
rotated_refresh_token="$(printf '%s\n' "${api_output}" | sed -n 's/^ROTATED_REFRESH_TOKEN=//p' | tail -n 1)"

if [ -z "${command_id}" ] || [ -z "${rotated_refresh_token}" ]; then
  echo "failed to capture command id or rotated refresh token from API verification output" >&2
  exit 1
fi

refresh_session_count="$(query_timescaledb \
  "SELECT COUNT(*) FROM refresh_sessions WHERE username = '${backend_admin_username}' AND expires_at > NOW();")"
REFRESH_SESSION_COUNT="${refresh_session_count:-0}" python3 - <<'PY'
import os
assert int((os.environ["REFRESH_SESSION_COUNT"] or "0").strip()) >= 1
PY

devices_row="$(query_timescaledb \
  "SELECT device_id || '|' || device_type || '|' || status || '|' || online::text FROM devices WHERE device_id IN ('${eq_device_id}','${wb_device_id}','${env_device_id}') ORDER BY device_id;")"
DEVICES_ROW="${devices_row}" python3 - <<'PY'
import os
rows = [line.strip() for line in os.environ["DEVICES_ROW"].splitlines() if line.strip()]
assert any(row.startswith("env-db-") and row.endswith("|env|online|true") for row in rows)
assert any(row.startswith("eq-db-") and row.endswith("|equipment|active|true") for row in rows)
assert any(row.startswith("wb-db-") and row.endswith("|wristband|online|true") for row in rows)
PY

equipment_row="$(query_timescaledb \
  "SELECT (payload->>'power_w') || '|' || (payload->>'rep_count') FROM equipment_telemetry WHERE device_id = '${eq_device_id}' ORDER BY ts DESC LIMIT 1;")"
[ "$(printf '%s' "${equipment_row}" | tr -d '[:space:]')" = "412.4|18" ]

wristband_row="$(query_timescaledb \
  "SELECT (payload->>'heart_rate') || '|' || (payload->>'current_equipment_id') FROM wristband_telemetry WHERE device_id = '${wb_device_id}' ORDER BY ts DESC LIMIT 1;")"
[ "$(printf '%s' "${wristband_row}" | tr -d '[:space:]')" = "92|${eq_device_id}" ]

env_row="$(query_timescaledb \
  "SELECT (payload->>'co2_ppm') || '|' || (payload->>'pm2_5') FROM env_telemetry WHERE device_id = '${env_device_id}' ORDER BY ts DESC LIMIT 1;")"
[ "$(printf '%s' "${env_row}" | tr -d '[:space:]')" = "1180|43" ]

alert_row="$(query_timescaledb \
  "SELECT code || '|' || priority || '|' || level FROM alerts WHERE device_id = '${env_device_id}' ORDER BY triggered_at DESC LIMIT 1;")"
[ "$(printf '%s' "${alert_row}" | tr -d '[:space:]')" = "CO2_HIGH|P1|warning" ]

binding_row="$(query_timescaledb \
  "SELECT action || '|' || COALESCE(duration_s::text,'') FROM equipment_binding_events WHERE wristband_id = '${wb_device_id}' ORDER BY ts DESC LIMIT 1;")"
BINDING_ROW="${binding_row}" python3 - <<'PY'
import os
action, duration = os.environ["BINDING_ROW"].strip().split("|", 1)
assert action == "unbind"
assert int(duration) >= 5
PY

command_row="$(query_timescaledb \
  "SELECT status || '|' || (payload->>'telemetry_interval_s') FROM device_config_commands WHERE command_id = '${command_id}'::uuid LIMIT 1;")"
[ "$(printf '%s' "${command_row}" | tr -d '[:space:]')" = "succeeded|25" ]

gateway_health_count="$(query_timescaledb \
  "SELECT COUNT(*) FROM gateway_component_health WHERE gateway_id = '${gateway_id}';")"
GATEWAY_HEALTH_COUNT="${gateway_health_count:-0}" python3 - <<'PY'
import os
assert int((os.environ["GATEWAY_HEALTH_COUNT"] or "0").strip()) >= 5
PY

redis_ping="$(docker compose -f "${compose_file}" exec -T "${redis_service}" redis-cli ping | tr -d '\r')"
[ "${redis_ping}" = "PONG" ]

influx_edge_rows="$(query_influx_jsonl \
  "SELECT event_id, topic FROM edge_ingest_events WHERE device_id IN ('${eq_device_id}','${wb_device_id}','${env_device_id}') ORDER BY time DESC LIMIT 16")"
influx_event_ids="$(INFLUX_EDGE_ROWS="${influx_edge_rows}" EQ_DEVICE_ID="${eq_device_id}" WB_DEVICE_ID="${wb_device_id}" ENV_DEVICE_ID="${env_device_id}" python3 - <<'PY'
import json
import os
rows = [json.loads(line) for line in os.environ["INFLUX_EDGE_ROWS"].splitlines() if line.strip()]
topics = {row["topic"] for row in rows}
assert any(topic.endswith(f"/equipment/{os.environ['EQ_DEVICE_ID']}/telemetry") for topic in topics)
assert any(topic.endswith(f"/wristband/{os.environ['WB_DEVICE_ID']}/telemetry") for topic in topics)
assert any(topic.endswith(f"/env/{os.environ['ENV_DEVICE_ID']}/telemetry") for topic in topics)
print(",".join(row["event_id"] for row in rows[:8]), end="")
PY
)"

delivered_sql="$(INFLUX_EVENT_IDS="${influx_event_ids}" python3 - <<'PY'
import os
event_ids = [item for item in os.environ["INFLUX_EVENT_IDS"].split(",") if item]
quoted = ",".join(f"'{item}'" for item in event_ids)
print(f"SELECT event_id FROM edge_delivery_log WHERE event_id IN ({quoted}) ORDER BY time DESC LIMIT 8", end="")
PY
)"
influx_delivery_rows="$(query_influx_jsonl "${delivered_sql}")"
INFLUX_DELIVERY_ROWS="${influx_delivery_rows}" python3 - <<'PY'
import json
import os
rows = [json.loads(line) for line in os.environ["INFLUX_DELIVERY_ROWS"].splitlines() if line.strip()]
assert len(rows) >= 1
PY

printf 'refresh session 持久化验证通过: 新 refresh token=%s\n' "${rotated_refresh_token}"
printf 'Redis 连通性验证通过: %s\n' "${redis_ping}"
printf 'TimescaleDB 设备表验证通过: %s\n' "${devices_row}"
printf 'TimescaleDB 器材时序表验证通过: %s\n' "${equipment_row}"
printf 'TimescaleDB 手环时序表验证通过: %s\n' "${wristband_row}"
printf 'TimescaleDB 环境时序表验证通过: %s\n' "${env_row}"
printf 'PostgreSQL 告警表验证通过: %s\n' "${alert_row}"
printf 'PostgreSQL 绑定表验证通过: %s\n' "${binding_row}"
printf 'PostgreSQL 配置命令表验证通过: %s\n' "${command_row}"
printf '网关健康表验证通过: %s\n' "${gateway_health_count}"
printf 'Influx 缓冲写入验证通过: %s\n' "${influx_edge_rows}"
printf 'Influx 补发确认验证通过: %s\n' "${influx_delivery_rows}"
