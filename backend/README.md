# Backend

Current backend work lives under `backend/api_service/` and focuses on the Sprint 1 minimum:

- `POST /api/v1/ingest/batch`
- `GET /api/v1/devices`
- `GET /api/v1/alerts`
- `GET /healthz`
- `GET /api/ws`

The current implementation is an async FastAPI skeleton with in-memory state for device status, alert records, and WebSocket broadcast. It is intentionally a transition layer: the API contract is already aligned with `docs/05-后台端.md` and `docs/07-通讯接口定义.md`, while PostgreSQL / TimescaleDB / Redis are still to be added behind the same interfaces.

Build locally:

```bash
container build \
  --build-arg PYTHON_BASE=dockerproxy.net/library/python:3.13-slim \
  -t motion-sense-backend-api-local \
  -f backend/deployment/api_service/Dockerfile .
```

Run unit tests in a one-off container:

```bash
container run --remove \
  --mount "type=bind,source=$PWD,target=/workspace" \
  --entrypoint sh motion-sense-backend-api-local \
  -lc "pip install --no-cache-dir pytest==8.3.5 httpx==0.28.1 >/tmp/pip.log 2>&1 && cd /workspace/backend/api_service && PYTHONPATH=/workspace/backend/api_service pytest tests/unit -q"
```
