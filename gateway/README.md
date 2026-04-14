# Gateway

Gateway service stack for `04-网关端`.

## Layout

- `edge_processor/`: Python 3.13 async application source and tests.
- `mosquitto/defaults/`: default broker config templates copied into the runtime mount on first start.
- `influxdb/defaults/`: default InfluxDB bootstrap assets.
- `deployment/`: Dockerfiles, entrypoints, and Compose orchestration.

## Local macOS testing

Linux deployment remains based on Docker Compose.

On macOS with Apple's `container` CLI, use per-image build/run commands instead of Compose. The base image can be switched to a registry mirror at build time, for example:

```bash
container build \
  --build-arg PYTHON_BASE=docker.1panel.live/library/python:3.13-slim \
  -t motion-sense-edge-processor-local \
  -f gateway/deployment/edge_processor/Dockerfile .
```

Detailed local test commands are documented in `deployment/container/README.md`.

## Runtime mounts

Compose expects these host-mounted runtime directories under `deployment/compose/runtime/`:

- `config/`
- `secrets/`
- `certs/`

Runtime data is stored in named Docker volumes for Mosquitto and InfluxDB.

## Current Status

- `edge_processor` now persists incoming MQTT events into local InfluxDB before upload.
- Backend replay reads undelivered events from InfluxDB and marks them delivered after successful HTTP batch upload.
- `rules.yaml` rewrite and reload polling are implemented for gateway config updates.
- P1 threshold rules are evaluated on telemetry (`EQ_OVERLOAD`, `CO2_HIGH`, `CO2_CRITICAL`, `PM25_HIGH`, `TEMP_HIGH`).
- `DEVICE_OFFLINE` monitoring publishes MQTT `alert` and retained `status`, and marks recovered devices online.

Current gaps:

- Linux production permission initialization for Mosquitto bind-mounted secrets/certs still needs deployment hardening.

## Runtime Rules

- `/runtime/config/edge_processor/app_settings.yaml`, `rules.yaml`, and `logging.yaml` are generated on first start.
- `/runtime/config/influxdb/admin_token.txt` is generated on first InfluxDB start and reused by `edge_processor`.
- Editing `rules.yaml` is hot-reloadable.
- Editing `app_settings.yaml` requires restarting `edge_processor`.
- Changing InfluxDB retention or storage settings requires restarting `influxdb`.
