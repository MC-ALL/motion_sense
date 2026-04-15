#!/bin/sh
set -eu

network_name="${CONTAINER_NETWORK:-motion-sense-local}"

for name in edge_processor mosquitto influxdb backend redis timescaledb; do
  container stop "${name}" >/dev/null 2>&1 || true
done

container network rm "${network_name}" >/dev/null 2>&1 || true
