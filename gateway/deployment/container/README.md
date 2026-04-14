# Apple Container Local Testing

This directory documents how to test the gateway stack on macOS with Apple's `container` CLI.

## Prerequisites

1. Start the Apple container system service once:

```bash
container system start
```

2. Create runtime directories:

```bash
mkdir -p gateway/deployment/compose/runtime/config
mkdir -p gateway/deployment/compose/runtime/secrets
mkdir -p gateway/deployment/compose/runtime/certs
```

3. Provide `gateway/deployment/compose/runtime/secrets/mosquitto.passwd` before starting Mosquitto.
   Or run `gateway/deployment/container/prepare_runtime.sh` after the local Mosquitto image is built.

4. `mosquitto` will generate `runtime/config/mosquitto/acl.conf` on first start from the image template.
   If you change `MOSQUITTO_USER` later, delete or update the generated ACL file before restarting.

## Build with registry mirror

Current verified macOS mirror baseline is `dockerproxy.net`, without the `https://` prefix in image references:

```bash
container build \
  --build-arg PYTHON_BASE=dockerproxy.net/library/python:3.13-slim \
  -t motion-sense-edge-processor-local \
  -f gateway/deployment/edge_processor/Dockerfile .
```

`mosquitto`:

```bash
container build \
  --build-arg MOSQUITTO_BASE=dockerproxy.net/library/eclipse-mosquitto:2.1.2-alpine \
  -t motion-sense-mosquitto-local \
  -f gateway/deployment/mosquitto/Dockerfile .
```

`influxdb`:

```bash
container build \
  --build-arg INFLUXDB_BASE=dockerproxy.net/library/influxdb:3.8.0-core \
  -t motion-sense-influxdb-local \
  -f gateway/deployment/influxdb/Dockerfile .
```

## Run a single service locally

Example: run `edge_processor` only.

```bash
container run \
  --name edge-test \
  --remove \
  -d \
  -p 18080:8080 \
  --mount type=bind,source=$PWD/gateway/deployment/compose/runtime/config,target=/runtime/config \
  motion-sense-edge-processor-local
```

Inspect logs:

```bash
container logs edge-test
```

Stop it:

```bash
container stop edge-test
```

## Run the full local stack

From the repository root:

```bash
sh gateway/deployment/container/build_local_images.sh
sh gateway/deployment/container/prepare_runtime.sh
sh gateway/deployment/container/start_local_stack.sh
```

Publish a sample telemetry message:

```bash
sh gateway/deployment/container/publish_sample_telemetry.sh
```

Run gateway unit tests in a one-off container:

```bash
container run --remove \
  --mount "type=bind,source=$PWD,target=/workspace" \
  --entrypoint sh motion-sense-edge-processor-local \
  -lc "pip install --no-cache-dir pytest==8.3.5 >/tmp/pip.log 2>&1 && cd /workspace/gateway/edge_processor && PYTHONPATH=/workspace/gateway/edge_processor pytest tests/unit -q"
```

Stop the local stack:

```bash
sh gateway/deployment/container/stop_local_stack.sh
```

## Notes

- The Apple `container` CLI supports image build, run, volumes, networks, bind mounts, port publishing, and env files.
- It does not provide a Compose-compatible orchestration layer in this toolchain, so multi-service local testing must be done service by service or with project-specific helper automation later.
- In local stack mode, `start_local_stack.sh` resolves backend and broker container IPs and injects them into `edge_processor` via environment variables, because container-name DNS resolution is not available by default in this setup.
- In local stack mode, `start_local_stack.sh` also injects MQTT credentials from `MOSQUITTO_USER` / `MOSQUITTO_PASSWORD`.
- Generated config files appear under the mounted `runtime/config/...` directories after first start.
- Verified locally on this machine: MQTT telemetry can flow `mosquitto -> edge_processor -> POST /api/v1/ingest/batch -> mock_backend`.
- Known remaining risk: bind-mounted `acl.conf` keeps host ownership and mode in Apple `container`, so Mosquitto 2.1.2 logs a warning. It still works now, but Linux deployment must add an explicit permission-initialization step before production rollout.
- Verified locally on this machine:
  - `dockerproxy.net/library/python:3.13-slim` builds successfully with `container build`
  - `dockerproxy.net/library/eclipse-mosquitto:2.1.2-alpine` builds successfully with `container build`
  - `dockerproxy.net/library/influxdb:3.8.0-core` builds successfully with `container build`
