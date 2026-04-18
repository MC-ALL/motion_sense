#!/bin/sh
set -eu

runtime_dir="/runtime/config/device_simulator"
defaults_dir="/opt/motion_sense/deployment/gateway/device_simulator/defaults"

mkdir -p "$runtime_dir"

target="${runtime_dir}/simulator_settings.yaml"
source="${defaults_dir}/default_simulator_settings.yaml"

if [ ! -f "$target" ]; then
  cp "$source" "$target"
fi

exec python -m app.main
