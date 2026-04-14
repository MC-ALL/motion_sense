# Repository Guidelines

## Project Structure & Module Organization
This repository now contains both specs and Sprint 1 implementation work.
- `docs/`: architecture, subsystem specs, API/topic contracts, and schedule.
- `gateway/`: `04-网关端` code and deployment assets. Main service code is in `gateway/edge_processor/app/`; Dockerfiles and runtime helpers live under `gateway/deployment/`.
- `backend/`: `05-后台端` code and deployment assets. Main service code is in `backend/api_service/app/`; Compose and image definitions live under `backend/deployment/`.

Keep docs synchronized with implementation, especially `docs/04-网关端.md`, `docs/05-后台端.md`, and `docs/07-通讯接口定义.md`.

## Build, Test, and Development Commands
- `container build --build-arg PYTHON_BASE=dockerproxy.net/library/python:3.13-slim -t motion-sense-edge-processor-local -f gateway/deployment/edge_processor/Dockerfile .`: build gateway image for local macOS testing.
- `container build --build-arg PYTHON_BASE=dockerproxy.net/library/python:3.13-slim -t motion-sense-backend-api-local -f backend/deployment/api_service/Dockerfile .`: build backend image.
- `container run --remove ... pytest tests/unit -q`: run unit tests inside the built images for `gateway/edge_processor` or `backend/api_service`.
- `sh gateway/deployment/container/start_local_stack.sh`: start the local Apple `container` stack for gateway-to-backend testing.
- `rg -n "TODO|FIXME|待补充" docs gateway backend`: find unfinished work.

## Coding Style & Naming Conventions
- Prefer async Python architecture and keep runtime code explicit and operationally simple.
- Use `snake_case` for Python modules, config keys, payload fields, and internal identifiers.
- Keep deployment artifacts under module-specific `deployment/` directories; do not add loose root-level scripts.
- Runtime-generated files must come from `default_*` templates on first start. Never commit secrets, certs, passwd files, or generated tokens.
- Keep API paths and MQTT topics aligned with `docs/07-通讯接口定义.md`.

## Testing Guidelines
- Run unit tests for any touched Python service.
- For gateway changes, prefer verifying the local chain `mosquitto -> edge_processor -> backend`.
- For backend changes, verify both persistence behavior and WebSocket/realtime behavior when relevant.
- If contracts change, update the matching docs in `docs/04-05-07`.

## Commit & Pull Request Guidelines
Current history uses Conventional Commits with scopes, for example:
- `feat(gateway): add influxdb replay buffer`
- `fix(gateway): fallback when delivery log is absent`
- `feat(backend): add redis realtime broadcast path`
- `chore(local): wire apple container stack to backend api`

PRs should include:
- What changed and why.
- Affected modules and docs.
- Contract or deployment impact.
- Local verification performed (`pytest`, Apple `container` replay check, compose path, etc.).
