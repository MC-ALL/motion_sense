#!/bin/sh
set -eu

backend_host_port="${BACKEND_HOST_PORT:-18000}"
gateway_host_port="${GATEWAY_HOST_PORT:-18080}"
timescaledb_host_port="${TIMESCALEDB_HOST_PORT:-15432}"
redis_host_port="${REDIS_HOST_PORT:-16379}"
influxdb_host_port="${INFLUXDB_HOST_PORT:-18181}"
postgres_password="${BACKEND_DATABASE_PASSWORD:-change_me_at_deploy}"
backend_bootstrap_admin_path="${BACKEND_BOOTSTRAP_ADMIN_PATH:-${PWD}/backend/deployment/compose/runtime/config/backend/api_service/bootstrap_admin.txt}"
backend_admin_username="${BACKEND_ADMIN_USERNAME:-}"
backend_admin_password="${BACKEND_ADMIN_PASSWORD:-}"
influxdb_admin_token_path="${INFLUXDB_ADMIN_TOKEN_PATH:-${PWD}/gateway/deployment/compose/runtime/config/influxdb/admin_token.txt}"

wait_for_json() {
  url="$1"
  check_code="$2"
  max_attempts="${3:-60}"
  auth_header="${4:-}"
  attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    if [ -n "$auth_header" ]; then
      body="$(curl -fsS -H "$auth_header" "$url" 2>/dev/null || true)"
    else
      body="$(curl -fsS "$url" 2>/dev/null || true)"
    fi
    if [ -n "$body" ] && BODY_JSON="$body" python3 -c "$check_code" >/dev/null 2>&1; then
      printf '%s\n' "$body"
      return 0
    fi
    sleep 1
    attempt=$((attempt + 1))
  done
  echo "timeout waiting for ${url}" >&2
  return 1
}

query_timescaledb() {
  sql="$1"
  printf '%s\n' "$sql" | container exec -i timescaledb sh -lc \
    "PGPASSWORD='${postgres_password}' psql -v ON_ERROR_STOP=1 -U motion_sense -d motion_sense -tAq"
}

query_influx_jsonl() {
  sql="$1"
  INFLUX_QUERY="$sql" INFLUX_HOST_PORT="$influxdb_host_port" INFLUXDB_ADMIN_TOKEN="$influxdb_admin_token" python3 - <<'PY'
import json
import os
import urllib.request

payload = {
    "db": "gym_local",
    "q": os.environ["INFLUX_QUERY"],
    "format": "jsonl",
}
request = urllib.request.Request(
    f"http://127.0.0.1:{os.environ['INFLUX_HOST_PORT']}/api/v3/query_sql",
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

curl -fsS "http://127.0.0.1:${backend_host_port}/healthz" >/dev/null
curl -fsS "http://127.0.0.1:${gateway_host_port}/healthz" >/dev/null
nc -z 127.0.0.1 "${timescaledb_host_port}"
nc -z 127.0.0.1 "${redis_host_port}"
nc -z 127.0.0.1 "${influxdb_host_port}"

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

if [ ! -f "${influxdb_admin_token_path}" ]; then
  echo "missing influxdb admin token: ${influxdb_admin_token_path}" >&2
  exit 1
fi

influxdb_admin_token="$(tr -d '\r\n' < "${influxdb_admin_token_path}")"

backend_login_body="$(curl -fsS -X POST "http://127.0.0.1:${backend_host_port}/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"${backend_admin_username}\",\"password\":\"${backend_admin_password}\"}")"
backend_access_token="$(BODY_JSON="$backend_login_body" python3 -c 'import json, os; print(json.loads(os.environ["BODY_JSON"])["access_token"])')"
backend_refresh_token="$(BODY_JSON="$backend_login_body" python3 -c 'import json, os; print(json.loads(os.environ["BODY_JSON"])["refresh_token"])')"
backend_auth_header="Authorization: Bearer ${backend_access_token}"

backend_refresh_body="$(curl -fsS -X POST "http://127.0.0.1:${backend_host_port}/api/v1/auth/refresh" \
  -H 'Content-Type: application/json' \
  -d "{\"refresh_token\":\"${backend_refresh_token}\"}")"
backend_refresh_token_rotated="$(OLD_TOKEN="${backend_refresh_token}" BODY_JSON="$backend_refresh_body" python3 -c 'import json, os; body=json.loads(os.environ["BODY_JSON"]); assert body["refresh_token"]; assert body["refresh_token"] != os.environ["OLD_TOKEN"]; print(body["refresh_token"])')"

refresh_session_count="$(query_timescaledb \
  "SELECT COUNT(*) FROM refresh_sessions WHERE username = '${backend_admin_username}' AND expires_at > NOW();")"
REFRESH_SESSION_COUNT="${refresh_session_count:-0}" python3 - <<'PY'
import os
assert int((os.environ["REFRESH_SESSION_COUNT"] or "0").strip()) >= 1
PY

eq_device_id="eq-db-01"
wb_device_id="wb-db-01"
env_device_id="env-db-01"
gateway_id="${EDGE_PROCESSOR_GATEWAY_ID:-gw-001}"
gym_id="gym-gz-01"

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

sh gateway/deployment/container/publish_sample_telemetry.sh \
  "gym/${gym_id}/equipment/${eq_device_id}/telemetry" \
  "${eq_payload_file}"
sh gateway/deployment/container/publish_sample_telemetry.sh \
  "gym/${gym_id}/wristband/${wb_device_id}/telemetry" \
  "${wb_payload_file}"
sh gateway/deployment/container/publish_sample_telemetry.sh \
  "gym/${gym_id}/wristband/${wb_device_id}/binding" \
  "${bind_payload_file}"
sh gateway/deployment/container/publish_sample_telemetry.sh \
  "gym/${gym_id}/wristband/${wb_device_id}/binding" \
  "${unbind_payload_file}"
sh gateway/deployment/container/publish_sample_telemetry.sh \
  "gym/${gym_id}/env/${env_device_id}/telemetry" \
  "${env_payload_file}"
sh gateway/deployment/container/publish_sample_telemetry.sh \
  "gym/${gym_id}/env/${env_device_id}/alert" \
  "${alert_payload_file}"

device_eq_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/devices/${eq_device_id}" \
  "import json, os; body=json.loads(os.environ['BODY_JSON']); assert body['device_id']=='${eq_device_id}'; assert body['online'] is True" \
  90 \
  "${backend_auth_header}")"

device_wb_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/devices/${wb_device_id}" \
  "import json, os; body=json.loads(os.environ['BODY_JSON']); assert body['device_id']=='${wb_device_id}'; assert body['online'] is True" \
  90 \
  "${backend_auth_header}")"

device_env_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/devices/${env_device_id}" \
  "import json, os; body=json.loads(os.environ['BODY_JSON']); assert body['device_id']=='${env_device_id}'; assert body['online'] is True" \
  90 \
  "${backend_auth_header}")"

equipment_telemetry_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/telemetry/equipment/${eq_device_id}" \
  "import json, os; body=json.loads(os.environ['BODY_JSON']); assert any(item['payload'].get('ts') == ${eq_ts} and item['payload'].get('power_w') == 412.4 for item in body)" \
  90 \
  "${backend_auth_header}")"

wristband_telemetry_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/telemetry/wristband/${wb_device_id}" \
  "import json, os; body=json.loads(os.environ['BODY_JSON']); assert any(item['payload'].get('ts') == ${wb_ts} and item['payload'].get('heart_rate') == 92 for item in body)" \
  90 \
  "${backend_auth_header}")"

env_telemetry_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/telemetry/env/${env_device_id}" \
  "import json, os; body=json.loads(os.environ['BODY_JSON']); assert any(item['payload'].get('ts') == ${env_ts} and item['payload'].get('co2_ppm') == 1180 for item in body)" \
  90 \
  "${backend_auth_header}")"

alerts_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/alerts?device_id=${env_device_id}" \
  "import json, os; body=json.loads(os.environ['BODY_JSON']); assert any(item['code'] == 'CO2_HIGH' and item['priority'] == 'P1' for item in body)" \
  90 \
  "${backend_auth_header}")"

bindings_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/wristband/${wb_device_id}/bindings" \
  "import json, os; body=json.loads(os.environ['BODY_JSON']); assert any(item['action'] == 'bind' for item in body); assert any(item['action'] == 'unbind' and (item.get('duration_s') or 0) >= 5 for item in body)" \
  90 \
  "${backend_auth_header}")"

command_body="$(curl -fsS -X POST "http://127.0.0.1:${backend_host_port}/api/v1/devices/${env_device_id}/config" \
  -H "${backend_auth_header}" \
  -H 'Content-Type: application/json' \
  -d "{\"config\":{\"telemetry_interval_s\":25},\"gateway_id\":\"${gateway_id}\",\"device_type\":\"env\",\"gym_id\":\"${gym_id}\"}")"
command_id="$(BODY_JSON="$command_body" python3 -c 'import json, os; print(json.loads(os.environ["BODY_JSON"])["command_id"])')"

command_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/gateway/commands/${command_id}" \
  "import json, os; body=json.loads(os.environ['BODY_JSON']); assert body['command_id']=='${command_id}'; assert body['status']=='succeeded'" \
  90 \
  "${backend_auth_header}")"

gateway_health_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/system/health/${gateway_id}" \
  "import json, os; body=json.loads(os.environ['BODY_JSON']); assert body['gateway_id']=='${gateway_id}'; assert len(body['components']) >= 5" \
  90 \
  "${backend_auth_header}")"

redis_ping="$(container exec redis redis-cli ping | tr -d '\r')"
[ "${redis_ping}" = "PONG" ]

devices_row="$(query_timescaledb \
  "SELECT device_id || '|' || device_type || '|' || status || '|' || online::text FROM devices WHERE device_id IN ('${eq_device_id}','${wb_device_id}','${env_device_id}') ORDER BY device_id;")"
DEVICES_ROW="${devices_row}" python3 - <<'PY'
import os
rows = [line.strip() for line in os.environ["DEVICES_ROW"].splitlines() if line.strip()]
assert "env-db-01|env|online|true" in rows
assert "eq-db-01|equipment|active|true" in rows
assert "wb-db-01|wristband|online|true" in rows
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

influx_edge_rows="$(query_influx_jsonl \
  "SELECT event_id, topic FROM edge_ingest_events WHERE device_id IN ('${eq_device_id}','${wb_device_id}','${env_device_id}') ORDER BY time DESC LIMIT 16")"
influx_event_ids="$(INFLUX_EDGE_ROWS="${influx_edge_rows}" python3 - <<'PY'
import json
import os
rows = [json.loads(line) for line in os.environ["INFLUX_EDGE_ROWS"].splitlines() if line.strip()]
topics = {row["topic"] for row in rows}
assert any(topic.endswith("/equipment/eq-db-01/telemetry") for topic in topics)
assert any(topic.endswith("/wristband/wb-db-01/telemetry") for topic in topics)
assert any(topic.endswith("/env/env-db-01/telemetry") for topic in topics)
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

printf 'refresh session 持久化验证通过: refresh_token 已轮换，新 token=%s\n' "${backend_refresh_token_rotated}"
printf '设备详情写库验证通过: %s\n' "${device_eq_json}"
printf '手环详情写库验证通过: %s\n' "${device_wb_json}"
printf '环境详情写库验证通过: %s\n' "${device_env_json}"
printf '器材时序写库验证通过: %s\n' "${equipment_telemetry_json}"
printf '手环时序写库验证通过: %s\n' "${wristband_telemetry_json}"
printf '环境时序写库验证通过: %s\n' "${env_telemetry_json}"
printf '告警写库验证通过: %s\n' "${alerts_json}"
printf '绑定历史写库验证通过: %s\n' "${bindings_json}"
printf '配置命令写库验证通过: %s\n' "${command_json}"
printf '健康表落库验证通过: %s\n' "${gateway_health_json}"
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
