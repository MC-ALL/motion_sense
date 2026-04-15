#!/bin/sh
set -eu

topic="${1:-gym/gym-gz-01/equipment/eq-001/telemetry}"
mosquitto_user="${MOSQUITTO_USER:-admin}"
mosquitto_password="${MOSQUITTO_PASSWORD:-admin123}"

if [ "$#" -ge 2 ]; then
  payload_input="$2"
else
  payload_input='{"ts":1712640000,"device_id":"eq-001","status":"active","rep_count":12,"power_w":350.5}'
fi

publish_from_stdin() {
  container exec -i mosquitto /usr/bin/mosquitto_pub \
    -h 127.0.0.1 \
    -p 1883 \
    -u "${mosquitto_user}" \
    -P "${mosquitto_password}" \
    -t "${topic}" \
    -s
}

if [ -f "${payload_input}" ]; then
  publish_from_stdin < "${payload_input}"
else
  printf '%s' "${payload_input}" | publish_from_stdin
fi
