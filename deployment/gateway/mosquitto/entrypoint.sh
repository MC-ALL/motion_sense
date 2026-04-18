#!/bin/sh
set -eu

runtime_dir="/runtime/config/mosquitto"
defaults_dir="/opt/motion_sense/deployment/gateway/mosquitto/defaults"
secret_file="/runtime/secrets/mosquitto.passwd"
config_file="${runtime_dir}/mosquitto.conf"
mosquitto_user="${MOSQUITTO_USER:-admin}"
mosquitto_password="${MOSQUITTO_PASSWORD:-admin123}"

mkdir -p "$runtime_dir" /runtime/secrets /runtime/certs /mosquitto/data /mosquitto/log

if [ ! -f "${runtime_dir}/mosquitto.conf" ]; then
  cp "${defaults_dir}/default_mosquitto.conf" "${runtime_dir}/mosquitto.conf"
fi

if [ ! -f "${runtime_dir}/acl.conf" ]; then
  sed "s/__MOSQUITTO_USER__/${mosquitto_user}/g" \
    "${defaults_dir}/default_acl.conf" > "${runtime_dir}/acl.conf"
fi

if [ ! -f "$secret_file" ]; then
  mosquitto_passwd -b -c "$secret_file" "$mosquitto_user" "$mosquitto_password"
fi

chown mosquitto:mosquitto /mosquitto/data /mosquitto/log "$runtime_dir" "$secret_file"
chmod 755 /mosquitto/data /mosquitto/log "$runtime_dir"
chmod 644 "${runtime_dir}/mosquitto.conf" "${runtime_dir}/acl.conf"
chmod 640 "$secret_file"

if grep -q "listener 8883" "$config_file"; then
  for cert_path in /runtime/certs/server.crt /runtime/certs/server.key /runtime/certs/ca.crt; do
    if [ ! -f "$cert_path" ]; then
      echo "missing required TLS material: $cert_path" >&2
      exit 1
    fi
  done
fi

exec /docker-entrypoint.sh /usr/sbin/mosquitto -c "$config_file"
