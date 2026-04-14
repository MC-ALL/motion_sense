# API Service

Async FastAPI backend for Sprint 1.

Current implemented scope:

- batch ingest: `POST /api/v1/ingest/batch`
- device, alert, telemetry, and binding history query APIs
- WebSocket endpoint: `GET /api/ws`
- device config publish: `POST /api/v1/devices/{id}/config`
- storage backends: `memory`, `postgres`
- realtime backends: `local`, `redis`

Device config publish behavior:

- MQTT publish backend is configured by `mqtt.backend` in runtime settings.
- default is `disabled` (API returns `503` for publish requests).
- set `mqtt.backend: mqtt` and broker connection fields to enable publish.
- target topic format: `gym/{gym_id}/{device_type}/{device_id}/config`.

Runtime config file generation:

- first start copies `backend/deployment/api_service/defaults/default_app_settings.yaml`
  to `/runtime/config/backend/api_service/app_settings.yaml`
- later edits apply on next `api_service` restart
