#!/bin/sh
set -eu

ops_host_port="${OPS_OBSERVER_HOST_PORT:-18090}"
backend_host_port="${BACKEND_HOST_PORT:-18000}"
backend_bootstrap_admin_path="${BACKEND_BOOTSTRAP_ADMIN_PATH:-${PWD}/deployment/runtime/config/backend/api_service/bootstrap_admin.txt}"
backend_admin_username="${BACKEND_ADMIN_USERNAME:-}"
backend_admin_password="${BACKEND_ADMIN_PASSWORD:-}"

curl -fsS "http://127.0.0.1:${ops_host_port}/healthz" >/dev/null

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

curl -fsS -H "${backend_auth_header}" "http://127.0.0.1:${ops_host_port}/api/v1/ops/health" >/dev/null
curl -fsS -H "${backend_auth_header}" "http://127.0.0.1:${ops_host_port}/api/v1/ops/stats" >/dev/null
curl -fsS -H "${backend_auth_header}" "http://127.0.0.1:${ops_host_port}/api/v1/ops/alerts" >/dev/null

printf 'ops_observer 基础接口验证通过\n'
