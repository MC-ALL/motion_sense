from __future__ import annotations

from pathlib import Path
from typing import Any
import os

import yaml
from pydantic import BaseModel, Field, ValidationError


DEFAULT_CONFIG_PATH = Path("/runtime/config/edge_processor/app_settings.yaml")
DEFAULT_INFLUXDB_TOKEN_PATH = Path("/runtime/config/influxdb/admin_token.txt")


class HttpBackendSettings(BaseModel):
    base_url: str = "http://backend:8000/api/v1"
    ingest_path: str = "/ingest/batch"
    request_timeout_s: float = 5.0
    health_path: str = "/healthz"


class MqttSettings(BaseModel):
    host: str = "mosquitto"
    port: int = 1883
    client_id: str = "gw-001-edge-processor"
    qos: int = 1
    username: str | None = None
    password: str | None = None
    topic_patterns: list[str] = Field(
        default_factory=lambda: [
            "gym/+/wristband/+/telemetry",
            "gym/+/wristband/+/binding",
            "gym/+/equipment/+/telemetry",
            "gym/+/equipment/+/alert",
            "gym/+/equipment/+/status",
            "gym/+/env/+/telemetry",
            "gym/+/env/+/alert",
            "gym/+/env/+/status",
            "gym/+/gateway/+/config",
        ]
    )


class InfluxdbSettings(BaseModel):
    base_url: str = "http://influxdb:8181"
    database_name: str = "gym_local"
    auth_token: str | None = None
    request_timeout_s: float = 5.0
    replay_batch_size: int = 500


class RuntimeSettings(BaseModel):
    app_name: str = "motion-sense-edge-processor"
    gateway_id: str = "gw-001"
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"
    batch_interval_s: int = 10
    health_interval_s: int = 15
    rules_reload_interval_s: int = 5
    backend: HttpBackendSettings = Field(default_factory=HttpBackendSettings)
    influxdb: InfluxdbSettings = Field(default_factory=InfluxdbSettings)
    mqtt: MqttSettings = Field(default_factory=MqttSettings)


def load_settings(config_path: Path | str = DEFAULT_CONFIG_PATH) -> RuntimeSettings:
    path = Path(config_path)
    raw: dict[str, Any] = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    _apply_env_overrides(raw)

    try:
        return RuntimeSettings.model_validate(raw)
    except ValidationError as exc:
        raise RuntimeError(f"invalid edge processor config at {path}: {exc}") from exc


def _apply_env_overrides(raw: dict[str, Any]) -> None:
    backend = raw.setdefault("backend", {})
    influxdb = raw.setdefault("influxdb", {})
    mqtt = raw.setdefault("mqtt", {})

    if value := os.environ.get("EDGE_PROCESSOR_GATEWAY_ID"):
        raw["gateway_id"] = value
    if value := os.environ.get("EDGE_PROCESSOR_BATCH_INTERVAL_S"):
        raw["batch_interval_s"] = int(value)
    if value := os.environ.get("EDGE_PROCESSOR_LOG_LEVEL"):
        raw["log_level"] = value
    if value := os.environ.get("EDGE_PROCESSOR_BACKEND_BASE_URL"):
        backend["base_url"] = value
    if value := os.environ.get("EDGE_PROCESSOR_BACKEND_INGEST_PATH"):
        backend["ingest_path"] = value
    if value := os.environ.get("EDGE_PROCESSOR_INFLUXDB_BASE_URL"):
        influxdb["base_url"] = value
    if value := os.environ.get("EDGE_PROCESSOR_INFLUXDB_DATABASE_NAME"):
        influxdb["database_name"] = value
    if value := os.environ.get("EDGE_PROCESSOR_INFLUXDB_AUTH_TOKEN"):
        influxdb["auth_token"] = value
    if value := os.environ.get("EDGE_PROCESSOR_INFLUXDB_REPLAY_BATCH_SIZE"):
        influxdb["replay_batch_size"] = int(value)
    if value := os.environ.get("EDGE_PROCESSOR_MQTT_HOST"):
        mqtt["host"] = value
    if value := os.environ.get("EDGE_PROCESSOR_MQTT_PORT"):
        mqtt["port"] = int(value)
    if value := os.environ.get("EDGE_PROCESSOR_MQTT_USERNAME"):
        mqtt["username"] = value
    if value := os.environ.get("EDGE_PROCESSOR_MQTT_PASSWORD"):
        mqtt["password"] = value

    if not influxdb.get("auth_token") and DEFAULT_INFLUXDB_TOKEN_PATH.exists():
        influxdb["auth_token"] = DEFAULT_INFLUXDB_TOKEN_PATH.read_text(encoding="utf-8").strip()
