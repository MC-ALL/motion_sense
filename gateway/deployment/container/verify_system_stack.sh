#!/bin/sh
set -eu

backend_host_port="${BACKEND_HOST_PORT:-18000}"
gateway_host_port="${GATEWAY_HOST_PORT:-18080}"
ops_host_port="${OPS_OBSERVER_HOST_PORT:-18090}"
web_host_port="${WEB_HOST_PORT:-18070}"
gateway_id="${EDGE_PROCESSOR_GATEWAY_ID:-gw-001}"
backend_bootstrap_admin_path="${BACKEND_BOOTSTRAP_ADMIN_PATH:-${PWD}/backend/deployment/compose/runtime/config/backend/api_service/bootstrap_admin.txt}"
backend_admin_username="${BACKEND_ADMIN_USERNAME:-}"
backend_admin_password="${BACKEND_ADMIN_PASSWORD:-}"

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

curl -fsS "http://127.0.0.1:${backend_host_port}/healthz" >/dev/null
curl -fsS "http://127.0.0.1:${gateway_host_port}/healthz" >/dev/null
curl -fsS "http://127.0.0.1:${ops_host_port}/healthz" >/dev/null
curl -fsS "http://127.0.0.1:${web_host_port}/" >/dev/null

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

backend_login_body="$(curl -fsS -X POST "http://127.0.0.1:${backend_host_port}/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"${backend_admin_username}\",\"password\":\"${backend_admin_password}\"}")"
backend_access_token="$(BODY_JSON="$backend_login_body" python3 -c 'import json, os; print(json.loads(os.environ["BODY_JSON"])["access_token"])')"
backend_auth_header="Authorization: Bearer ${backend_access_token}"

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
  'import json, os; body=json.loads(os.environ["BODY_JSON"]); assert body["device_id"]=="eq-001"; assert body["online"] is True' \
  60 \
  "$backend_auth_header")"

health_detail_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/system/health/${gateway_id}" \
  'import json, os; body=json.loads(os.environ["BODY_JSON"]); assert body["gateway_id"]; assert len(body["components"]) >= 5' \
  60 \
  "$backend_auth_header")"

registered_device_json="$(curl -fsS -X POST "http://127.0.0.1:${backend_host_port}/api/v1/devices" \
  -H "$backend_auth_header" \
  -H 'Content-Type: application/json' \
  -d '{"gym_id":"gym-gz-01","device_type":"env","device_id":"env-b","gateway_id":"gw-001","display_name":"环境节点 B","location":"二楼东侧"}')"

command_body="$(curl -fsS -X POST "http://127.0.0.1:${backend_host_port}/api/v1/devices/env-b/config" \
  -H "$backend_auth_header" \
  -H 'Content-Type: application/json' \
  -d '{"config":{"telemetry_interval_s":20}}')"
command_id="$(BODY_JSON="$command_body" python3 -c 'import json, os; print(json.loads(os.environ["BODY_JSON"])["command_id"])')"

command_detail_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/gateway/commands/${command_id}" \
  'import json, os; body=json.loads(os.environ["BODY_JSON"]); assert body["status"]=="succeeded"' \
  60 \
  "$backend_auth_header")"

summary_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/system/health" \
  'import json, os; body=json.loads(os.environ["BODY_JSON"]); assert len(body) >= 1; assert body[0]["gateway_id"]' \
  60 \
  "$backend_auth_header")"

ops_health_json="$(wait_for_json \
  "http://127.0.0.1:${ops_host_port}/api/v1/ops/health" \
  "import json, os; body=json.loads(os.environ['BODY_JSON']); assert len(body['items']) >= 2; gateway=next(item for item in body['items'] if item['module_id']=='gateway:gw-001'); backend=next(item for item in body['items'] if item['module_id']=='backend:api-main'); assert gateway['online'] is True and gateway['health_status']=='healthy'; assert backend['online'] is True and backend['health_status']=='healthy'")"

ops_detail_json="$(wait_for_json \
  "http://127.0.0.1:${ops_host_port}/api/v1/ops/health/gateway:gw-001" \
  'import json, os; body=json.loads(os.environ["BODY_JSON"]); assert body["summary"]["module_id"]=="gateway:gw-001"; assert len(body["components"]) >= 1')"

web_runtime_config="$(wait_for_json \
  "http://127.0.0.1:${web_host_port}/runtime_config.js" \
  "import os; body=os.environ['BODY_JSON']; assert 'backend_base_url' in body; assert 'ops_base_url' in body; assert '${backend_host_port}' in body; assert '${ops_host_port}' in body")"

web_index_html="$(wait_for_json \
  "http://127.0.0.1:${web_host_port}/" \
  'import os; body=os.environ["BODY_JSON"]; assert "粤动智感运维门户" in body or "root" in body')"

printf '设备入库验证通过: %s\n' "$device_json"
printf '健康汇聚验证通过: %s\n' "$health_detail_json"
printf '设备注册验证通过: %s\n' "$registered_device_json"
printf '配置命令闭环验证通过: %s\n' "$command_detail_json"
printf '健康汇总视图验证通过: %s\n' "$summary_json"
printf 'ops_observer 健康汇总验证通过: %s\n' "$ops_health_json"
printf 'ops_observer 健康详情验证通过: %s\n' "$ops_detail_json"
printf '网页运行时配置验证通过: %s\n' "$web_runtime_config"
printf '网页入口验证通过: %s\n' "$web_index_html"
