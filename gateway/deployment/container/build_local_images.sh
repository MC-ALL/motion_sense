#!/bin/sh
set -eu

container build \
  --build-arg PYTHON_BASE=dockerproxy.net/library/python:3.13-slim \
  -t motion-sense-edge-processor-local \
  -f gateway/deployment/edge_processor/Dockerfile .

container build \
  --build-arg MOSQUITTO_BASE=dockerproxy.net/library/eclipse-mosquitto:2.1.2-alpine \
  -t motion-sense-mosquitto-local \
  -f gateway/deployment/mosquitto/Dockerfile .

container build \
  --build-arg INFLUXDB_BASE=dockerproxy.net/library/influxdb:3.8.0-core \
  -t motion-sense-influxdb-local \
  -f gateway/deployment/influxdb/Dockerfile .

container build \
  --build-arg PYTHON_BASE=dockerproxy.net/library/python:3.13-slim \
  -t motion-sense-mock-backend-local \
  -f gateway/deployment/testing/mock_backend/Dockerfile .
