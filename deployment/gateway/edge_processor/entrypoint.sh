#!/bin/sh
set -eu

runtime_dir="/runtime/config/edge_processor"
defaults_dir="/opt/motion_sense/deployment/gateway/edge_processor/defaults"
ops_token_path="/runtime/secrets/edge_processor_ops_token.txt"
gateway_command_token_path="/runtime/secrets/backend_gateway_command_token.txt"

mkdir -p "$runtime_dir" /runtime/secrets

for template in app_settings logging rules; do
  target="${runtime_dir}/${template}.yaml"
  source="${defaults_dir}/default_${template}.yaml"

  if [ ! -f "$target" ]; then
    cp "$source" "$target"
  fi
done

if [ ! -f "$ops_token_path" ]; then
  if [ -n "${EDGE_PROCESSOR_OPS_AUTH_TOKEN:-}" ]; then
    printf '%s\n' "${EDGE_PROCESSOR_OPS_AUTH_TOKEN}" > "$ops_token_path"
  else
    python -c 'import secrets; print(secrets.token_urlsafe(32))' > "$ops_token_path"
  fi
  chmod 600 "$ops_token_path"
fi

if [ ! -f "$gateway_command_token_path" ]; then
  if [ -n "${EDGE_PROCESSOR_BACKEND_COMMAND_CHANNEL_TOKEN:-}" ]; then
    printf '%s\n' "${EDGE_PROCESSOR_BACKEND_COMMAND_CHANNEL_TOKEN}" > "$gateway_command_token_path"
    chmod 600 "$gateway_command_token_path"
  else
    retries=0
    while [ ! -f "$gateway_command_token_path" ] && [ "$retries" -lt 30 ]; do
      sleep 1
      retries=$((retries + 1))
    done
    if [ ! -f "$gateway_command_token_path" ]; then
      echo "missing backend gateway command token: ${gateway_command_token_path}" >&2
      exit 1
    fi
  fi
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8080
