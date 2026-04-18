#!/bin/sh
set -eu

runtime_dir="/runtime/config/web/portal_app"
defaults_dir="/opt/motion_sense/deployment/web/portal_app/defaults"
html_dir="/usr/share/nginx/html"

mkdir -p "$runtime_dir"

if [ ! -f "$runtime_dir/runtime_config.js" ]; then
  cp "$defaults_dir/default_runtime_config.js" "$runtime_dir/runtime_config.js"
fi

cp "$runtime_dir/runtime_config.js" "$html_dir/runtime_config.js"

exec nginx -g 'daemon off;'
