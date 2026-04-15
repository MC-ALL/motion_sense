#!/bin/sh
set -eu

container build \
  --build-arg PYTHON_BASE=python:3.13-slim \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  -t motion-sense-edge-processor-local \
  -f gateway/deployment/edge_processor/Dockerfile .

container build \
  --build-arg MOSQUITTO_BASE=eclipse-mosquitto:2.1-alpine \
  -t motion-sense-mosquitto-local \
  -f gateway/deployment/mosquitto/Dockerfile .

container build \
  --build-arg INFLUXDB_BASE=influxdb:3.9-core \
  -t motion-sense-influxdb-local \
  -f gateway/deployment/influxdb/Dockerfile .

container build \
  --build-arg PYTHON_BASE=python:3.13-slim \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  -t motion-sense-backend-api-local \
  -f backend/deployment/api_service/Dockerfile .

container build \
  --build-arg PYTHON_BASE=python:3.13-slim \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  -t motion-sense-ops-observer-local \
  -f ops_observer/deployment/api_service/Dockerfile .

container build \
  --build-arg TIMESCALEDB_BASE=timescale/timescaledb:latest-pg17 \
  -t motion-sense-timescaledb-local \
  -f backend/deployment/timescaledb/Dockerfile .

container build \
  --build-arg PYTHON_BASE=python:3.13-slim \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  -t motion-sense-mock-backend-local \
  -f gateway/deployment/testing/mock_backend/Dockerfile .
