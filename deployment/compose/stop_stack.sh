#!/bin/sh
set -eu

compose_file="${COMPOSE_FILE_PATH:-deployment/compose/docker-compose.yaml}"
purge_volumes="${PURGE_VOLUMES:-false}"
purge_runtime="${PURGE_RUNTIME:-false}"

down_args="down --remove-orphans"

if [ "${purge_volumes}" = "true" ]; then
  down_args="${down_args} --volumes"
fi

# shellcheck disable=SC2086
docker compose -f "${compose_file}" ${down_args}

if [ "${purge_runtime}" = "true" ]; then
  find deployment/runtime -mindepth 1 ! -name '.gitignore' -exec rm -rf {} +
fi
