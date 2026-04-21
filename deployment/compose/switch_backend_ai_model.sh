#!/bin/sh
set -eu

variant="${1:-}"

if [ -z "${variant}" ]; then
  echo "usage: sh deployment/compose/switch_backend_ai_model.sh <reasoner|chat>" >&2
  exit 1
fi

case "${variant}" in
  reasoner|chat)
    ;;
  *)
    echo "invalid model variant: ${variant} (expected: reasoner or chat)" >&2
    exit 1
    ;;
esac

script_dir=$(
  CDPATH= cd -- "$(dirname "$0")" && pwd
)
repo_root=$(
  CDPATH= cd -- "${script_dir}/../.." && pwd
)

config_path="${BACKEND_APP_SETTINGS_PATH:-${repo_root}/deployment/runtime/config/backend/api_service/app_settings.yaml}"
compose_file="${COMPOSE_FILE_PATH:-${repo_root}/deployment/compose/docker-compose.yaml}"
backend_service="${BACKEND_SERVICE_NAME:-backend_api_service}"

if [ ! -f "${config_path}" ]; then
  echo "runtime config not found: ${config_path}" >&2
  echo "hint: start the compose stack once so the runtime config is generated first" >&2
  exit 1
fi

if ! python3 - "${config_path}" "${variant}" <<'PY'
from pathlib import Path
import re
import sys

config_path = Path(sys.argv[1])
variant = sys.argv[2]
text = config_path.read_text(encoding="utf-8")

if "\nai:\n" not in text and not text.startswith("ai:\n"):
    if not text.endswith("\n"):
        text += "\n"
    text += (
        "ai:\n"
        f"  model_variant: {variant}\n"
        "  model: null\n"
    )
else:
    if re.search(r"(?m)^  model_variant: .*$", text):
        text = re.sub(r"(?m)^  model_variant: .*$", f"  model_variant: {variant}", text)
    else:
        text = re.sub(r"(?m)^ai:\n", f"ai:\n  model_variant: {variant}\n", text, count=1)

    if re.search(r"(?m)^  model: .*$", text):
        text = re.sub(r"(?m)^  model: .*$", "  model: null", text)
    else:
        text = re.sub(r"(?m)^  model_variant: .*$", lambda m: m.group(0) + "\n  model: null", text, count=1)

config_path.write_text(text, encoding="utf-8")
print(f"updated {config_path} -> model_variant={variant}, model=null")
PY
then
  echo "failed to update runtime config: ${config_path}" >&2
  echo "hint: if deployment/runtime is root-owned, run: sudo sh deployment/compose/switch_backend_ai_model.sh ${variant}" >&2
  exit 1
fi

echo "restarting ${backend_service} via ${compose_file}" >&2
docker compose -f "${compose_file}" up -d --build "${backend_service}"

echo "active ai model variant switched to: ${variant}" >&2
