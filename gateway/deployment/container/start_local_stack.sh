#!/bin/sh
set -eu

runtime_root="${PWD}/gateway/deployment/compose/runtime"
config_root="${runtime_root}/config"
secret_root="${runtime_root}/secrets"
cert_root="${runtime_root}/certs"
data_root="${runtime_root}/data"
network_name="${CONTAINER_NETWORK:-motion-sense-local}"
mosquitto_user="${MOSQUITTO_USER:-admin}"
mosquitto_password="${MOSQUITTO_PASSWORD:-admin123}"

mkdir -p "${config_root}" "${secret_root}" "${cert_root}"
mkdir -p "${data_root}/mosquitto_data" "${data_root}/mosquitto_log" "${data_root}/influxdb_data"

container network create "${network_name}" >/dev/null 2>&1 || true

container run \
  --name backend \
  --remove \
  -d \
  --network "${network_name}" \
  -p 18000:8000 \
  motion-sense-mock-backend-local

container run \
  --name influxdb \
  --remove \
  -d \
  --network "${network_name}" \
  -p 18181:8181 \
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
mqtt_ip="$(container inspect mosquitto | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data[0]["networks"][0]["ipv4Address"].split("/")[0])')"

container run \
  --name edge_processor \
  --remove \
  -d \
  --network "${network_name}" \
  -p 18080:8080 \
  --env "EDGE_PROCESSOR_BACKEND_BASE_URL=http://${backend_ip}:8000/api/v1" \
  --env "EDGE_PROCESSOR_MQTT_HOST=${mqtt_ip}" \
  --env "EDGE_PROCESSOR_MQTT_USERNAME=${mosquitto_user}" \
  --env "EDGE_PROCESSOR_MQTT_PASSWORD=${mosquitto_password}" \
  --mount "type=bind,source=${config_root},target=/runtime/config" \
  motion-sense-edge-processor-local
