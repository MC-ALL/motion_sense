# motion_sense

Sprint 1 workspace for `04-网关端` and `05-后台端`.

## Current Status

- `gateway/`: async edge processor, Mosquitto, InfluxDB 3 Core deployment assets, Apple `container` local test scripts
- `backend/`: async FastAPI ingest/query service, TimescaleDB persistence, Redis realtime broadcast
- `docs/`: architecture, subsystem specs, interface contracts, and delivery plan

Completed and verified on this machine:

- backend ingest/query path with TimescaleDB persistence
- backend WebSocket realtime path in both `local` and `redis` modes
- gateway local InfluxDB-backed cache and replay path
- local chain: `mosquitto -> edge_processor -> POST /api/v1/ingest/batch -> backend/api_service`

Current gaps:

- gateway P1 rule engine
- gateway `DEVICE_OFFLINE` alert publishing
- backend auth/JWT and AI report flow

## Repository Layout

- `docs/`: source-of-truth requirements and interface docs
- `gateway/edge_processor/`: gateway Python service
- `gateway/deployment/`: Dockerfiles, entrypoints, Compose, Apple `container` helpers
- `backend/api_service/`: backend Python service
- `backend/deployment/`: backend Dockerfiles and Compose baseline

## Quick Commands

Build backend:

```bash
container build \
  --build-arg PYTHON_BASE=dockerproxy.net/library/python:3.13-slim \
  -t motion-sense-backend-api-local \
  -f backend/deployment/api_service/Dockerfile .
```

Build gateway:

```bash
container build \
  --build-arg PYTHON_BASE=dockerproxy.net/library/python:3.13-slim \
  -t motion-sense-edge-processor-local \
  -f gateway/deployment/edge_processor/Dockerfile .
```

Run backend unit tests:

```bash
container run --remove \
  --mount "type=bind,source=$PWD,target=/workspace" \
  --entrypoint sh motion-sense-backend-api-local \
  -lc "pip install --no-cache-dir pytest==8.3.5 httpx==0.28.1 >/tmp/pip.log 2>&1 && cd /workspace/backend/api_service && PYTHONPATH=/workspace/backend/api_service pytest tests/unit -q"
```

Run gateway unit tests:

```bash
container run --remove \
  --mount "type=bind,source=$PWD,target=/workspace" \
  --entrypoint sh motion-sense-edge-processor-local \
  -lc "pip install --no-cache-dir pytest==8.3.5 >/tmp/pip.log 2>&1 && cd /workspace/gateway/edge_processor && PYTHONPATH=/workspace/gateway/edge_processor pytest tests/unit -q"
```

## Local Platform Notes

- Dev platform: macOS + Apple `container`
- Deploy target: Linux + Docker
- Local ad hoc stacks do not provide Compose-style service-name DNS; scripts resolve container IPs explicitly
- Registry mirror currently in use: `dockerproxy.net`
