#!/bin/sh
set -eu

compose_file="${COMPOSE_FILE_PATH:-deployment/compose/docker-compose.yaml}"
backend_service="${BACKEND_SERVICE_NAME:-backend_api_service}"
gateway_service="${GATEWAY_SERVICE_NAME:-gateway_edge_processor}"
web_host="${WEB_HOST:-127.0.0.1}"
web_port="${WEB_PORT:-8080}"
backend_host="${BACKEND_HOST:-127.0.0.1}"
backend_port="${BACKEND_PORT:-8000}"
ops_host="${OPS_HOST:-127.0.0.1}"
ops_port="${OPS_PORT:-8090}"

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

backend_bootstrap="$(
  docker compose -f "${compose_file}" exec -T "${backend_service}" \
    sh -lc 'cat /runtime/config/backend/api_service/bootstrap_admin.txt'
)"

gateway_ops_token="$(
  docker compose -f "${compose_file}" exec -T "${gateway_service}" \
    sh -lc 'cat /runtime/secrets/edge_processor_ops_token.txt'
)"

backend_admin_username="$(printf '%s\n' "${backend_bootstrap}" | sed -n 's/^username: //p' | head -n 1)"
backend_admin_password="$(printf '%s\n' "${backend_bootstrap}" | sed -n 's/^password: //p' | head -n 1)"
gateway_ops_token="$(printf '%s\n' "${gateway_ops_token}" | tr -d '\r\n')"

if [ -z "${backend_admin_username}" ] || [ -z "${backend_admin_password}" ]; then
  echo "failed to read backend bootstrap admin credentials from running container" >&2
  exit 1
fi

if [ -z "${gateway_ops_token}" ]; then
  echo "failed to read gateway ops token from running container" >&2
  exit 1
fi

cat <<EOF
后台首登账号:
  username: ${backend_admin_username}
  password: ${backend_admin_password}

网关运维 token:
  ${gateway_ops_token}

默认访问入口:
  web:     http://${web_host}:${web_port}/
  backend: http://${backend_host}:${backend_port}/
  ops:     http://${ops_host}:${ops_port}/
EOF
