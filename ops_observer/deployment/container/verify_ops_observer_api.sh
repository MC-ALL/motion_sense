#!/bin/sh
set -eu

ops_host_port="${OPS_OBSERVER_HOST_PORT:-18090}"

curl -fsS "http://127.0.0.1:${ops_host_port}/healthz" >/dev/null
curl -fsS "http://127.0.0.1:${ops_host_port}/api/v1/ops/health" >/dev/null
curl -fsS "http://127.0.0.1:${ops_host_port}/api/v1/ops/stats" >/dev/null
curl -fsS "http://127.0.0.1:${ops_host_port}/api/v1/ops/alerts" >/dev/null

printf 'ops_observer 基础接口验证通过\n'
