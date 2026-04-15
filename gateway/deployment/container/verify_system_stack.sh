#!/bin/sh
set -eu

backend_host_port="${BACKEND_HOST_PORT:-18000}"
gateway_host_port="${GATEWAY_HOST_PORT:-18080}"
gateway_id="${EDGE_PROCESSOR_GATEWAY_ID:-gw-001}"

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

curl -fsS "http://127.0.0.1:${backend_host_port}/healthz" >/dev/null
curl -fsS "http://127.0.0.1:${gateway_host_port}/healthz" >/dev/null

sample_payload_file="$(mktemp)"
cleanup() {
  rm -f "${sample_payload_file}"
}
trap cleanup EXIT INT TERM

current_ts="$(date +%s)"

cat > "${sample_payload_file}" <<'EOF'
{"ts":__CURRENT_TS__,"device_id":"eq-001","status":"active","rep_count":12,"power_w":350.5,"gateway_id":"gw-001"}
EOF

sed -i.bak "s/__CURRENT_TS__/${current_ts}/" "${sample_payload_file}"
rm -f "${sample_payload_file}.bak"

sh gateway/deployment/container/publish_sample_telemetry.sh \
  "gym/gym-gz-01/equipment/eq-001/telemetry" \
  "${sample_payload_file}"

device_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/devices/eq-001" \
  'import json, os; body=json.loads(os.environ["BODY_JSON"]); assert body["device_id"]=="eq-001"; assert body["online"] is True')"

health_detail_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/system/health/${gateway_id}" \
  'import json, os; body=json.loads(os.environ["BODY_JSON"]); assert body["gateway_id"]; assert len(body["components"]) >= 5')"

command_body="$(curl -fsS -X POST "http://127.0.0.1:${backend_host_port}/api/v1/devices/env-a/config" \
  -H 'Content-Type: application/json' \
  -d '{"gym_id":"gym-gz-01","gateway_id":"gw-001","device_type":"env","config":{"telemetry_interval_s":20}}')"
command_id="$(BODY_JSON="$command_body" python3 -c 'import json, os; print(json.loads(os.environ["BODY_JSON"])["command_id"])')"

command_detail_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/gateway/commands/${command_id}" \
  'import json, os; body=json.loads(os.environ["BODY_JSON"]); assert body["status"]=="succeeded"')"

summary_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/system/health" \
  'import json, os; body=json.loads(os.environ["BODY_JSON"]); assert len(body) >= 1; assert body[0]["gateway_id"]')"

printf '设备入库验证通过: %s\n' "$device_json"
printf '健康汇聚验证通过: %s\n' "$health_detail_json"
printf '配置命令闭环验证通过: %s\n' "$command_detail_json"
printf '健康汇总视图验证通过: %s\n' "$summary_json"
