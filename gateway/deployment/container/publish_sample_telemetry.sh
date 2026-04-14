#!/bin/sh
set -eu

topic="${1:-gym/gym-gz-01/equipment/eq-001/telemetry}"
payload="${2:-{\"ts\":1712640000,\"device_id\":\"eq-001\",\"status\":\"active\",\"rep_count\":12,\"power_w\":350.5}}"
mosquitto_user="${MOSQUITTO_USER:-admin}"
mosquitto_password="${MOSQUITTO_PASSWORD:-admin123}"

container exec mosquitto /usr/bin/mosquitto_pub \
  -h 127.0.0.1 \
  -p 1883 \
  -u "${mosquitto_user}" \
  -P "${mosquitto_password}" \
  -t "${topic}" \
  -m "${payload}"
