# API Service

Async FastAPI backend for Sprint 1.

Current implemented scope:

- batch ingest: `POST /api/v1/ingest/batch`
- device, alert, telemetry, and binding history query APIs
- WebSocket endpoint: `GET /api/ws`
- storage backends: `memory`, `postgres`
- realtime backends: `local`, `redis`

Runtime config file generation:

- first start copies `backend/deployment/api_service/defaults/default_app_settings.yaml`
  to `/runtime/config/backend/api_service/app_settings.yaml`
- later edits apply on next `api_service` restart
