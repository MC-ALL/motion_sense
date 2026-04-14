#!/bin/sh
set -eu

runtime_root="${PWD}/gateway/deployment/compose/runtime"
config_root="${runtime_root}/config"
secret_root="${runtime_root}/secrets"
cert_root="${runtime_root}/certs"
data_root="${runtime_root}/data"

mkdir -p "${config_root}" "${secret_root}" "${cert_root}"
mkdir -p "${data_root}/mosquitto_data" "${data_root}/mosquitto_log" "${data_root}/influxdb_data"

mosquitto_user="${MOSQUITTO_USER:-admin}"
mosquitto_password="${MOSQUITTO_PASSWORD:-admin123}"

if [ ! -f "${secret_root}/mosquitto.passwd" ]; then
  container run \
    --remove \
    --mount "type=bind,source=${secret_root},target=/runtime/secrets" \
    --entrypoint sh \
    motion-sense-mosquitto-local \
    -c "mosquitto_passwd -b -c /runtime/secrets/mosquitto.passwd '${mosquitto_user}' '${mosquitto_password}'"
fi
