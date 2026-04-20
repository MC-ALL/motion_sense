#!/bin/sh
set -eu

runtime_dir="/runtime/config/web/portal_app"
defaults_dir="/opt/motion_sense/deployment/web/portal_app/defaults"
html_dir="/usr/share/nginx/html"
runtime_config_path="${runtime_dir}/runtime_config.js"
runtime_config_mode="${WEB_PORTAL_RUNTIME_CONFIG_MODE:-render}"
app_name="${WEB_PORTAL_APP_NAME:-粤动智感运维门户}"
backend_base_url="${WEB_PORTAL_BACKEND_BASE_URL:-}"
backend_ws_url="${WEB_PORTAL_BACKEND_WS_URL:-/api/ws}"
ops_base_url="${WEB_PORTAL_OPS_BASE_URL:-}"
ops_ws_url="${WEB_PORTAL_OPS_WS_URL:-/api/ws/ops}"
refresh_interval_ms="${WEB_PORTAL_REFRESH_INTERVAL_MS:-15000}"

mkdir -p "$runtime_dir"

escape_js_string() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

render_runtime_config() {
  app_name_escaped="$(escape_js_string "$app_name")"
  backend_base_url_escaped="$(escape_js_string "$backend_base_url")"
  backend_ws_url_escaped="$(escape_js_string "$backend_ws_url")"
  ops_base_url_escaped="$(escape_js_string "$ops_base_url")"
  ops_ws_url_escaped="$(escape_js_string "$ops_ws_url")"

  cat > "$runtime_config_path" <<EOF
window.__motion_sense_runtime__ = {
  app_name: "${app_name_escaped}",
  backend_base_url: "${backend_base_url_escaped}",
  backend_ws_url: "${backend_ws_url_escaped}",
  ops_base_url: "${ops_base_url_escaped}",
  ops_ws_url: "${ops_ws_url_escaped}",
  refresh_interval_ms: ${refresh_interval_ms}
};
EOF
}

case "$runtime_config_mode" in
  render)
    render_runtime_config
    ;;
  preserve)
    if [ ! -f "$runtime_config_path" ]; then
      render_runtime_config
    elif [ ! -s "$runtime_config_path" ]; then
      cp "$defaults_dir/default_runtime_config.js" "$runtime_config_path"
    fi
    ;;
  *)
    echo "unsupported WEB_PORTAL_RUNTIME_CONFIG_MODE: $runtime_config_mode" >&2
    exit 1
    ;;
esac

if [ ! -s "$runtime_config_path" ]; then
  cp "$defaults_dir/default_runtime_config.js" "$runtime_config_path"
fi

cp "$runtime_config_path" "$html_dir/runtime_config.js"

exec nginx -g 'daemon off;'
