#!/bin/sh
set -eu

runtime_dir="/runtime/config/edge_processor"
defaults_dir="/opt/motion_sense/deployment/gateway/edge_processor/defaults"

mkdir -p "$runtime_dir"

for template in app_settings logging rules; do
  target="${runtime_dir}/${template}.yaml"
  source="${defaults_dir}/default_${template}.yaml"

  if [ ! -f "$target" ]; then
    cp "$source" "$target"
  fi
done

exec uvicorn app.main:app --host 0.0.0.0 --port 8080
