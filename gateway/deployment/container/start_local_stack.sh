#!/bin/sh
set -eu

runtime_root="${PWD}/gateway/deployment/compose/runtime"
config_root="${runtime_root}/config"
secret_root="${runtime_root}/secrets"
cert_root="${runtime_root}/certs"
data_root="${runtime_root}/data"
backend_runtime_root="${PWD}/backend/deployment/compose/runtime"
backend_config_root="${backend_runtime_root}/config"
ops_runtime_root="${PWD}/ops_observer/deployment/compose/runtime"
ops_config_root="${ops_runtime_root}/config"
ops_data_root="${ops_runtime_root}/data"
web_runtime_root="${PWD}/web/deployment/compose/runtime"
web_config_root="${web_runtime_root}/config"
network_name="${CONTAINER_NETWORK:-motion-sense-local}"
mosquitto_user="${MOSQUITTO_USER:-admin}"
mosquitto_password="${MOSQUITTO_PASSWORD:-admin123}"
backend_storage_backend="${BACKEND_STORAGE_BACKEND:-postgres}"
postgres_password="${BACKEND_DATABASE_PASSWORD:-change_me_at_deploy}"
timescaledb_host_port="${TIMESCALEDB_HOST_PORT:-15432}"
redis_host_port="${REDIS_HOST_PORT:-16379}"
backend_host_port="${BACKEND_HOST_PORT:-18000}"
gateway_host_port="${GATEWAY_HOST_PORT:-18080}"
ops_host_port="${OPS_OBSERVER_HOST_PORT:-18090}"
web_host_port="${WEB_HOST_PORT:-18070}"
influxdb_host_port="${INFLUXDB_HOST_PORT:-18181}"
edge_health_interval_s="${EDGE_PROCESSOR_HEALTH_INTERVAL_S:-5}"
network_subnet="${CONTAINER_NETWORK_SUBNET:-192.168.65.0/24}"
network_gateway="${CONTAINER_NETWORK_GATEWAY:-192.168.65.1}"

if [ -n "${BACKEND_REALTIME_BACKEND:-}" ]; then
  backend_realtime_backend="${BACKEND_REALTIME_BACKEND}"
elif [ "${backend_storage_backend}" = "postgres" ]; then
  backend_realtime_backend="redis"
else
  backend_realtime_backend="local"
fi

mkdir -p "${config_root}" "${secret_root}" "${cert_root}"
mkdir -p "${data_root}/mosquitto_data" "${data_root}/mosquitto_log" "${data_root}/influxdb_data"
mkdir -p "${backend_config_root}"
mkdir -p "${ops_config_root}" "${ops_data_root}"
mkdir -p "${web_config_root}"

gateway_ops_token_path="${secret_root}/edge_processor_ops_token.txt"
if [ -f "${gateway_ops_token_path}" ]; then
  gateway_ops_token="$(tr -d '\r\n' < "${gateway_ops_token_path}")"
else
  gateway_ops_token="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  printf '%s\n' "${gateway_ops_token}" > "${gateway_ops_token_path}"
  chmod 600 "${gateway_ops_token_path}"
fi

container network create --subnet "${network_subnet}" "${network_name}" >/dev/null 2>&1 || true

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

if [ "${backend_storage_backend}" = "postgres" ]; then
  container run \
    --name timescaledb \
    --remove \
    -d \
    --network "${network_name}" \
    -p "${timescaledb_host_port}:5432" \
    --env "POSTGRES_DB=motion_sense" \
    --env "POSTGRES_USER=motion_sense" \
    --env "POSTGRES_PASSWORD=${postgres_password}" \
    motion-sense-timescaledb-local

  container run \
    --name redis \
    --remove \
    -d \
    --network "${network_name}" \
    -p "${redis_host_port}:6379" \
    redis:8.6-alpine \
    redis-server --save "" --appendonly no

  wait_for_tcp 127.0.0.1 "${timescaledb_host_port}" 90
  wait_for_tcp 127.0.0.1 "${redis_host_port}" 30
fi

timescaledb_ip=""
redis_ip=""
if [ "${backend_storage_backend}" = "postgres" ]; then
  timescaledb_ip="$(container inspect timescaledb | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data[0]["networks"][0]["ipv4Address"].split("/")[0])')"
  redis_ip="$(container inspect redis | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data[0]["networks"][0]["ipv4Address"].split("/")[0])')"
fi

backend_args="
  --name backend
  --remove
  -d
  --network ${network_name}
  -p ${backend_host_port}:8000
  --mount type=bind,source=${backend_config_root},target=/runtime/config
  --env BACKEND_STORAGE_BACKEND=${backend_storage_backend}
  --env BACKEND_REALTIME_BACKEND=${backend_realtime_backend}
"

if [ "${backend_storage_backend}" = "postgres" ]; then
  backend_args="${backend_args}
  --env BACKEND_DATABASE_HOST=${timescaledb_ip}
  --env BACKEND_DATABASE_PORT=5432
  --env BACKEND_DATABASE_NAME=motion_sense
  --env BACKEND_DATABASE_USER=motion_sense
  --env BACKEND_DATABASE_PASSWORD=${postgres_password}
  --env BACKEND_REDIS_HOST=${redis_ip}
  --env BACKEND_REDIS_PORT=6379
"
fi

# shellcheck disable=SC2086
container run ${backend_args} motion-sense-backend-api-local
wait_for_http_ok "http://127.0.0.1:${backend_host_port}/healthz" 90

container run \
  --name influxdb \
  --remove \
  -d \
  --network "${network_name}" \
  -p "${influxdb_host_port}:8181" \
  --mount "type=bind,source=${config_root},target=/runtime/config" \
  --mount "type=bind,source=${data_root}/influxdb_data,target=/var/lib/influxdb3" \
  motion-sense-influxdb-local

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
  motion-sense-mosquitto-local

backend_ip="$(container inspect backend | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data[0]["networks"][0]["ipv4Address"].split("/")[0])')"
influxdb_ip="$(container inspect influxdb | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data[0]["networks"][0]["ipv4Address"].split("/")[0])')"
backend_admin_username="$(sed -n 's/^username: //p' "${backend_config_root}/backend/api_service/bootstrap_admin.txt" | head -n 1)"
backend_admin_password="$(sed -n 's/^password: //p' "${backend_config_root}/backend/api_service/bootstrap_admin.txt" | head -n 1)"
backend_runtime_config_path="${backend_config_root}/backend/api_service/app_settings.yaml"
backend_auth_issuer="$(sed -n 's/^  issuer: //p' "${backend_runtime_config_path}" | head -n 1)"
backend_auth_audience="$(sed -n 's/^  audience: //p' "${backend_runtime_config_path}" | head -n 1)"
backend_auth_access_secret="$(sed -n 's/^    access_secret: //p' "${backend_runtime_config_path}" | head -n 1)"

if [ -z "${backend_auth_issuer}" ] || [ -z "${backend_auth_audience}" ] || [ -z "${backend_auth_access_secret}" ]; then
  echo "missing backend auth runtime settings for ops observer" >&2
  exit 1
fi

wait_for_tcp 127.0.0.1 "${influxdb_host_port}" 90
wait_for_tcp 127.0.0.1 1883 30

container run \
  --name edge_processor \
  --remove \
  -d \
  --network "${network_name}" \
  -p "${gateway_host_port}:8080" \
  --env "EDGE_PROCESSOR_BACKEND_BASE_URL=http://${backend_ip}:8000/api/v1" \
  --env "EDGE_PROCESSOR_INFLUXDB_BASE_URL=http://${influxdb_ip}:8181" \
  --env "EDGE_PROCESSOR_MQTT_HOST=${network_gateway}" \
  --env "EDGE_PROCESSOR_MQTT_USERNAME=${mosquitto_user}" \
  --env "EDGE_PROCESSOR_MQTT_PASSWORD=${mosquitto_password}" \
  --env "EDGE_PROCESSOR_HEALTH_INTERVAL_S=${edge_health_interval_s}" \
  --env "EDGE_PROCESSOR_OPS_AUTH_ENFORCE_REST=true" \
  --env "EDGE_PROCESSOR_OPS_AUTH_ENFORCE_WS=true" \
  --env "EDGE_PROCESSOR_OPS_AUTH_TOKEN=${gateway_ops_token}" \
  --mount "type=bind,source=${config_root},target=/runtime/config" \
  motion-sense-edge-processor-local

wait_for_http_ok "http://127.0.0.1:${gateway_host_port}/healthz" 90
edge_processor_ip="$(container inspect edge_processor | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data[0]["networks"][0]["ipv4Address"].split("/")[0])')"

container run \
  --name ops_observer \
  --remove \
  -d \
  --network "${network_name}" \
  -p "${ops_host_port}:8090" \
  --env "OPS_OBSERVER_GATEWAY_BASE_URL=http://${edge_processor_ip}:8080" \
  --env "OPS_OBSERVER_BACKEND_BASE_URL=http://${backend_ip}:8000" \
  --env "OPS_OBSERVER_BACKEND_AUTH_USERNAME=${backend_admin_username}" \
  --env "OPS_OBSERVER_BACKEND_AUTH_PASSWORD=${backend_admin_password}" \
  --env "OPS_OBSERVER_GATEWAY_AUTH_TOKEN=${gateway_ops_token}" \
  --env "OPS_OBSERVER_GATEWAY_WS_ENABLED=true" \
  --env "OPS_OBSERVER_BACKEND_WS_ENABLED=true" \
  --env "OPS_OBSERVER_AUTH_ENFORCE_REST=true" \
  --env "OPS_OBSERVER_AUTH_ENFORCE_WS=true" \
  --env "OPS_OBSERVER_AUTH_ISSUER=${backend_auth_issuer}" \
  --env "OPS_OBSERVER_AUTH_AUDIENCE=${backend_auth_audience}" \
  --env "OPS_OBSERVER_AUTH_ACCESS_SECRET=${backend_auth_access_secret}" \
  --mount "type=bind,source=${ops_config_root},target=/runtime/config" \
  --mount "type=bind,source=${ops_data_root},target=/runtime/data" \
  motion-sense-ops-observer-local

wait_for_http_ok "http://127.0.0.1:${ops_host_port}/healthz" 90

cat > "${web_config_root}/runtime_config.js" <<EOF
window.__motion_sense_runtime__ = {
  app_name: '粤动智感运维门户',
  backend_base_url: 'http://127.0.0.1:${backend_host_port}',
  backend_ws_url: 'ws://127.0.0.1:${backend_host_port}/api/ws',
  ops_base_url: 'http://127.0.0.1:${ops_host_port}',
  ops_ws_url: 'ws://127.0.0.1:${ops_host_port}/api/ws/ops',
  refresh_interval_ms: 15000
};
EOF

container run \
  --name web_portal \
  --remove \
  -d \
  --network "${network_name}" \
  -p "${web_host_port}:8080" \
  --mount "type=bind,source=${web_config_root},target=/runtime/config" \
  motion-sense-web-portal-local

wait_for_http_ok "http://127.0.0.1:${web_host_port}/" 90
