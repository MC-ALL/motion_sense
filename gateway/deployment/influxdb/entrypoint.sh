#!/bin/sh
set -eu

runtime_dir="/runtime/config/influxdb"
defaults_dir="/opt/motion_sense/influxdb/defaults"
data_dir="/var/lib/influxdb3"
init_marker="${data_dir}/.motion_sense_initialized"

mkdir -p "$runtime_dir" "$data_dir"

if [ ! -f "${runtime_dir}/influxdb3_init.txt" ]; then
  cp "${defaults_dir}/default_influxdb3_init.txt" "${runtime_dir}/influxdb3_init.txt"
fi

database_name="$(awk -F= '/^database_name=/{print $2}' "${runtime_dir}/influxdb3_init.txt")"
retention_period="$(awk -F= '/^retention_period=/{print $2}' "${runtime_dir}/influxdb3_init.txt")"

influxdb3 serve --node-id gateway-node --object-store file --data-dir "$data_dir" --http-bind 0.0.0.0:8181 &
server_pid="$!"

cleanup() {
  kill "$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
}

trap cleanup INT TERM

until influxdb3 show databases --host http://127.0.0.1:8181 >/dev/null 2>&1; do
  sleep 1
done

if [ ! -f "$init_marker" ]; then
  if ! influxdb3 show databases --host http://127.0.0.1:8181 | grep -q "^${database_name}$"; then
    influxdb3 create database --host http://127.0.0.1:8181 --retention-period "$retention_period" "$database_name"
  fi
  touch "$init_marker"
fi

wait "$server_pid"
