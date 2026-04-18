#!/bin/sh
set -eu

runtime_dir="/runtime/config/ops_observer/api_service"
defaults_dir="/opt/motion_sense/deployment/ops_observer/api_service/defaults"
data_dir="/runtime/data/ops_observer"

mkdir -p "$runtime_dir" "$data_dir"

if [ ! -f "$runtime_dir/app_settings.yaml" ]; then
  cp "$defaults_dir/default_app_settings.yaml" "$runtime_dir/app_settings.yaml"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8090
