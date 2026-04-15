#!/bin/sh
set -eu

runtime_root="${PWD}/gateway/deployment/compose/runtime"
config_root="${runtime_root}/config"
secret_root="${runtime_root}/secrets"
cert_root="${runtime_root}/certs"
data_root="${runtime_root}/data"
network_name="${CONTAINER_NETWORK:-motion-sense-local}"
backend_host_port="${BACKEND_HOST_PORT:-18000}"
gateway_host_port="${GATEWAY_HOST_PORT:-18080}"
mosquitto_user="${MOSQUITTO_USER:-admin}"
mosquitto_password="${MOSQUITTO_PASSWORD:-admin123}"
rules_file="${config_root}/edge_processor/rules.yaml"
rules_backup="$(mktemp)"
restore_wait_s="${EDGE_PROCESSOR_RULES_RELOAD_INTERVAL_S:-5}"

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

wait_for_tcp() {
  host="$1"
  port="$2"
  max_attempts="${3:-60}"
  attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    if nc -z "$host" "$port" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    attempt=$((attempt + 1))
  done
  echo "timeout waiting for ${host}:${port}" >&2
  return 1
}

container_exists() {
  name="$1"
  body="$(container inspect "$name" 2>/dev/null || true)"
  [ -n "${body}" ] && [ "${body}" != "[]" ]
}

wait_for_container_gone() {
  name="$1"
  max_attempts="${2:-30}"
  attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    if ! container_exists "$name"; then
      return 0
    fi
    sleep 1
    attempt=$((attempt + 1))
  done
  echo "timeout waiting for container removal: ${name}" >&2
  return 1
}

wait_for_json() {
  url="$1"
  check_code="$2"
  max_attempts="${3:-60}"
  attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    body="$(curl -fsS "$url" 2>/dev/null || true)"
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

start_mosquitto() {
  if container_exists mosquitto; then
    return 0
  fi

  container run \
    --name mosquitto \
    --remove \
    -d \
    --network "${network_name}" \
    -p 1883:1883 \
    --mount "type=bind,source=${config_root},target=/runtime/config" \
    --mount "type=bind,source=${secret_root},target=/runtime/secrets" \
    --mount "type=bind,source=${cert_root},target=/runtime/certs" \
    --mount "type=bind,source=${data_root}/mosquitto_data,target=/mosquitto/data" \
    --mount "type=bind,source=${data_root}/mosquitto_log,target=/mosquitto/log" \
    --env "MOSQUITTO_USER=${mosquitto_user}" \
    --env "MOSQUITTO_PASSWORD=${mosquitto_password}" \
    motion-sense-mosquitto-local >/dev/null
}

restore_rules() {
  if [ -f "${rules_backup}" ] && [ -f "${rules_file}" ]; then
    cp "${rules_backup}" "${rules_file}"
    sleep $((restore_wait_s + 1))
  fi
}

cleanup() {
  restore_rules
  start_mosquitto >/dev/null 2>&1 || true
  rm -f "${rules_backup}"
}

trap cleanup EXIT INT TERM

if [ ! -f "${rules_file}" ]; then
  echo "missing rules file: ${rules_file}" >&2
  exit 1
fi

cp "${rules_file}" "${rules_backup}"

wait_for_http_ok "http://127.0.0.1:${backend_host_port}/healthz" 30
wait_for_http_ok "http://127.0.0.1:${gateway_host_port}/healthz" 30
wait_for_tcp 127.0.0.1 1883 30

container stop mosquitto >/dev/null 2>&1 || true
wait_for_container_gone mosquitto 30
start_mosquitto
wait_for_tcp 127.0.0.1 1883 60

reconnect_payload_file="$(mktemp)"
rule_payload_a_file="$(mktemp)"
rule_payload_b_file="$(mktemp)"

cleanup_payloads() {
  rm -f "${reconnect_payload_file}" "${rule_payload_a_file}" "${rule_payload_b_file}"
}

trap 'cleanup_payloads; cleanup' EXIT INT TERM

reconnect_ts="$(date +%s)"
cat > "${reconnect_payload_file}" <<EOF
{"ts":${reconnect_ts},"device_id":"eq-reconnect-01","status":"active","rep_count":8,"power_w":288.0,"gateway_id":"gw-001"}
EOF

sh gateway/deployment/container/publish_sample_telemetry.sh \
  "gym/gym-gz-01/equipment/eq-reconnect-01/telemetry" \
  "${reconnect_payload_file}"

broker_reconnect_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/devices/eq-reconnect-01" \
  'import json, os; body=json.loads(os.environ["BODY_JSON"]); assert body["device_id"]=="eq-reconnect-01"; assert body["online"] is True; assert body["last_payload"]["power_w"]==288.0')"

pre_reload_ts="$(date +%s)"
cat > "${rule_payload_a_file}" <<EOF
{"ts":${pre_reload_ts},"device_id":"env-rule-01","co2_ppm":700,"temperature_c":26.5,"humidity":52.0}
EOF

sh gateway/deployment/container/publish_sample_telemetry.sh \
  "gym/gym-gz-01/env/env-rule-01/telemetry" \
  "${rule_payload_a_file}"

pre_reload_alerts_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/alerts?device_id=env-rule-01" \
  'import json, os; body=json.loads(os.environ["BODY_JSON"]); assert body == []')"

RULES_FILE="${rules_file}" python3 -c '
from pathlib import Path
import os
import yaml

path = Path(os.environ["RULES_FILE"])
data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
rules = data.setdefault("alert_rules", {})
co2 = rules.setdefault("CO2_HIGH", {})
co2["enabled"] = True
co2["threshold_ppm"] = 600
co2["window_s"] = 2
co2["level"] = "warning"
path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=False), encoding="utf-8")
'

sleep $((restore_wait_s + 2))

reload_ts_a="$((pre_reload_ts + 1))"
reload_ts_b="$((pre_reload_ts + 4))"
cat > "${rule_payload_a_file}" <<EOF
{"ts":${reload_ts_a},"device_id":"env-rule-01","co2_ppm":700,"temperature_c":26.5,"humidity":52.0}
EOF
cat > "${rule_payload_b_file}" <<EOF
{"ts":${reload_ts_b},"device_id":"env-rule-01","co2_ppm":710,"temperature_c":26.7,"humidity":51.0}
EOF

sh gateway/deployment/container/publish_sample_telemetry.sh \
  "gym/gym-gz-01/env/env-rule-01/telemetry" \
  "${rule_payload_a_file}"
sh gateway/deployment/container/publish_sample_telemetry.sh \
  "gym/gym-gz-01/env/env-rule-01/telemetry" \
  "${rule_payload_b_file}"

rules_reload_alert_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/alerts?device_id=env-rule-01" \
  'import json, os; body=json.loads(os.environ["BODY_JSON"]); assert any(item["device_id"]=="env-rule-01" and item["code"]=="CO2_HIGH" for item in body)')"

printf 'Broker 重连验证通过: %s\n' "${broker_reconnect_json}"
printf '规则热重载前无命中验证通过: %s\n' "${pre_reload_alerts_json}"
printf '规则热重载后告警验证通过: %s\n' "${rules_reload_alert_json}"
