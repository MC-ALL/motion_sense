#!/bin/sh
set -eu

runtime_dir="/runtime/config/influxdb"
defaults_dir="/opt/motion_sense/deployment/gateway/influxdb/defaults"
data_dir="/var/lib/influxdb3"
init_marker="${data_dir}/.motion_sense_initialized"
token_path="${runtime_dir}/admin_token.txt"

mkdir -p "$runtime_dir" "$data_dir"

if [ ! -f "${runtime_dir}/influxdb3_init.txt" ]; then
  cp "${defaults_dir}/default_influxdb3_init.txt" "${runtime_dir}/influxdb3_init.txt"
fi

database_name="$(awk -F= '/^database_name=/{print $2}' "${runtime_dir}/influxdb3_init.txt")"
retention_period="$(awk -F= '/^retention_period=/{print $2}' "${runtime_dir}/influxdb3_init.txt")"

influxdb3 serve \
  --node-id gateway-node \
  --object-store file \
  --data-dir "$data_dir" \
  --http-bind 0.0.0.0:8181 &
server_pid="$!"

cleanup() {
  kill "$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
}

trap cleanup INT TERM

if [ ! -f "$token_path" ]; then
  until token_json="$(influxdb3 create token --admin --host http://127.0.0.1:8181 --format json 2>/dev/null)"; do
    sleep 1
  done
  token="$(printf '%s\n' "$token_json" | sed -n 's/.*"token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
  if [ -z "$token" ]; then
    echo "failed to parse influxdb admin token from create token output" >&2
    exit 1
  fi
  printf '%s\n' "$token" >"$token_path"
  chmod 600 "$token_path"
fi

auth_token="$(tr -d '\r\n' < "$token_path")"
export INFLUXDB3_AUTH_TOKEN="$auth_token"

until influxdb3 show databases --host http://127.0.0.1:8181 --token "$auth_token" >/dev/null 2>&1; do
  sleep 1
done

if [ ! -f "$init_marker" ]; then
  if ! influxdb3 show databases --host http://127.0.0.1:8181 --token "$auth_token" | grep -q "^${database_name}$"; then
    influxdb3 create database --host http://127.0.0.1:8181 --token "$auth_token" --retention-period "$retention_period" "$database_name"
  fi
  touch "$init_marker"
fi

wait "$server_pid"
