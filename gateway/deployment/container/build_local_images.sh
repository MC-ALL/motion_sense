#!/bin/sh
set -eu

script_dir="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
repo_root="$(CDPATH= cd -- "${script_dir}/../../.." && pwd)"
runtime_root="${repo_root}/gateway/deployment/compose/runtime"

mkdir -p "${runtime_root}"
build_root="$(mktemp -d "${runtime_root}/build_contexts.XXXXXX")"

cleanup() {
  rm -rf "${build_root}"
}

trap cleanup EXIT INT TERM

copy_path() {
  source_path="${repo_root}/$1"
  target_path="$2/$1"

  mkdir -p "$(dirname "${target_path}")"
  if [ -d "${source_path}" ]; then
    cp -R "${source_path}" "${target_path}"
  else
    cp "${source_path}" "${target_path}"
  fi
}

prune_context() {
  context_dir="$1"

  find "${context_dir}" \
    \( \
      -name __pycache__ -o \
      -name .pytest_cache -o \
      -name node_modules -o \
      -name dist -o \
      -name build -o \
      -name '*.egg-info' \
    \) \
    -prune -exec rm -rf {} +
}

prepare_context() {
  context_name="$1"
  shift

  context_dir="${build_root}/${context_name}"
  mkdir -p "${context_dir}"

  for relative_path in "$@"; do
    copy_path "${relative_path}" "${context_dir}"
  done

  prune_context "${context_dir}"

  printf '%s\n' "${context_dir}"
}

build_image() {
  context_dir="$1"
  image_tag="$2"
  dockerfile_rel="$3"
  shift 3

  (
    cd "${context_dir}"
    container build "$@" -t "${image_tag}" -f "${dockerfile_rel}" .
  )
}

edge_context="$(prepare_context edge \
  gateway/edge_processor \
  gateway/deployment/edge_processor)"
build_image \
  "${edge_context}" \
  motion-sense-edge-processor-local \
  gateway/deployment/edge_processor/Dockerfile \
  --build-arg PYTHON_BASE=python:3.13-slim \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

mosquitto_context="$(prepare_context mosquitto \
  gateway/mosquitto \
  gateway/deployment/mosquitto)"
build_image \
  "${mosquitto_context}" \
  motion-sense-mosquitto-local \
  gateway/deployment/mosquitto/Dockerfile \
  --build-arg MOSQUITTO_BASE=eclipse-mosquitto:2.1-alpine

influxdb_context="$(prepare_context influxdb \
  gateway/influxdb \
  gateway/deployment/influxdb)"
build_image \
  "${influxdb_context}" \
  motion-sense-influxdb-local \
  gateway/deployment/influxdb/Dockerfile \
  --build-arg INFLUXDB_BASE=influxdb:3.9-core

backend_context="$(prepare_context backend \
  backend/api_service \
  backend/deployment/api_service \
  backend/deployment/timescaledb)"
build_image \
  "${backend_context}" \
  motion-sense-backend-api-local \
  backend/deployment/api_service/Dockerfile \
  --build-arg PYTHON_BASE=python:3.13-slim \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
build_image \
  "${backend_context}" \
  motion-sense-timescaledb-local \
  backend/deployment/timescaledb/Dockerfile \
  --build-arg TIMESCALEDB_BASE=timescale/timescaledb:latest-pg17

ops_context="$(prepare_context ops_observer \
  ops_observer/api_service \
  ops_observer/deployment/api_service)"
build_image \
  "${ops_context}" \
  motion-sense-ops-observer-local \
  ops_observer/deployment/api_service/Dockerfile \
  --build-arg PYTHON_BASE=python:3.13-slim \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

mock_backend_context="$(prepare_context mock_backend \
  gateway/deployment/testing/mock_backend)"
build_image \
  "${mock_backend_context}" \
  motion-sense-mock-backend-local \
  gateway/deployment/testing/mock_backend/Dockerfile \
  --build-arg PYTHON_BASE=python:3.13-slim \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

web_context="$(prepare_context web \
  web/portal_app \
  web/deployment/portal_app)"
build_image \
  "${web_context}" \
  motion-sense-web-portal-local \
  web/deployment/portal_app/Dockerfile \
  --build-arg BUILD_BASE=node:24-alpine \
  --build-arg NGINX_BASE=nginx:1.29-alpine
