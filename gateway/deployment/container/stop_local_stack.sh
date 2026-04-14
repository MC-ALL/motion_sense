#!/bin/sh
set -eu

for name in edge_processor mosquitto influxdb backend; do
  container stop "${name}" >/dev/null 2>&1 || true
done
