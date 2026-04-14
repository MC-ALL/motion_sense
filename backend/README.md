# Backend

Current backend work lives under `backend/api_service/` and focuses on the Sprint 1 minimum:

- `POST /api/v1/ingest/batch`
- `GET /api/v1/devices`
- `GET /api/v1/devices/{id}`
- `GET /api/v1/alerts`
- `GET /api/v1/alerts/{id}`
- `PATCH /api/v1/alerts/{id}/ack`
- `GET /api/v1/telemetry/wristband/{id}`
- `GET /api/v1/telemetry/equipment/{id}`
- `GET /api/v1/telemetry/env/{id}`
- `GET /api/v1/wristband/{id}/bindings`
- `GET /healthz`
- `GET /api/ws`

The current implementation is an async FastAPI skeleton with two storage modes:

- `memory`: default for unit tests and minimal local runs
- `postgres`: async `psycopg` + Timescale/PostgreSQL persistence for `devices`, `alerts`, `equipment_binding_events`, and telemetry hypertables

It is intentionally a transition layer: the API contract is already aligned with `docs/05-后台端.md` and `docs/07-通讯接口定义.md`, while Redis, JWT, and AI flows are still to be added.

Build locally:

```bash
container build \
  --build-arg PYTHON_BASE=dockerproxy.net/library/python:3.13-slim \
  -t motion-sense-backend-api-local \
  -f backend/deployment/api_service/Dockerfile .
```

Backend Linux compose baseline now includes:

- `api_service`
- `timescaledb`

Verified locally on this machine:

- `POST /api/v1/ingest/batch` can persist into Timescale/PostgreSQL mode
- `GET /api/v1/devices/{id}` returns the persisted device snapshot
- `PATCH /api/v1/alerts/{id}/ack` updates persisted alert state
- `GET /api/v1/telemetry/equipment/{id}` returns persisted history rows
- `GET /api/v1/wristband/{id}/bindings` returns persisted binding events

Apple `container` note:

- local test networking does not provide Compose-like service-name DNS by default
- when testing outside Linux Compose, pass the database container IP to `BACKEND_DATABASE_HOST`

Run unit tests in a one-off container:

```bash
container run --remove \
  --mount "type=bind,source=$PWD,target=/workspace" \
  --entrypoint sh motion-sense-backend-api-local \
  -lc "pip install --no-cache-dir pytest==8.3.5 httpx==0.28.1 >/tmp/pip.log 2>&1 && cd /workspace/backend/api_service && PYTHONPATH=/workspace/backend/api_service pytest tests/unit -q"
```
