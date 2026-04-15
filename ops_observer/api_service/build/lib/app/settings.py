from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError


DEFAULT_CONFIG_PATH = Path("/runtime/config/ops_observer/api_service/app_settings.yaml")


class UpstreamModuleSettings(BaseModel):
    module_id: str
    module_type: Literal["gateway", "backend"]
    display_name: str
    base_url: str
    timeout_s: float = Field(default=5.0, gt=0)
    auth_token: str | None = None
    ws_enabled: bool = True
    ws_path: str = "/ops/ws"


class AlertThresholdSettings(BaseModel):
    stale_after_s: int = Field(default=60, ge=1)
    emit_recovery_alert: bool = True


class RuntimeSettings(BaseModel):
    app_name: str = "motion-sense-ops-observer-api-service"
    host: str = "0.0.0.0"
    port: int = 8090
    log_level: str = "INFO"
    poll_interval_s: int = Field(default=15, ge=1)
    database_path: str = "/runtime/data/ops_observer/ops_observer.sqlite3"
    ws_snapshot_interval_s: int = Field(default=30, ge=1)
    upstream_ws_ping_interval_s: int = Field(default=20, ge=1)
    upstream_ws_retry_interval_s: int = Field(default=5, ge=1)
    alert_threshold: AlertThresholdSettings = Field(default_factory=AlertThresholdSettings)
    upstream_modules: list[UpstreamModuleSettings] = Field(default_factory=list)


def load_settings(config_path: Path | str = DEFAULT_CONFIG_PATH) -> RuntimeSettings:
    path = Path(config_path)
    raw: dict[str, Any] = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    _apply_env_overrides(raw)

    try:
        return RuntimeSettings.model_validate(raw)
    except ValidationError as exc:
        raise RuntimeError(f"invalid ops observer config at {path}: {exc}") from exc


def _apply_env_overrides(raw: dict[str, Any]) -> None:
    if value := os.environ.get("OPS_OBSERVER_HOST"):
        raw["host"] = value
    if value := os.environ.get("OPS_OBSERVER_PORT"):
        raw["port"] = int(value)
    if value := os.environ.get("OPS_OBSERVER_LOG_LEVEL"):
        raw["log_level"] = value
    if value := os.environ.get("OPS_OBSERVER_POLL_INTERVAL_S"):
        raw["poll_interval_s"] = int(value)
    if value := os.environ.get("OPS_OBSERVER_DATABASE_PATH"):
        raw["database_path"] = value
    if value := os.environ.get("OPS_OBSERVER_WS_SNAPSHOT_INTERVAL_S"):
        raw["ws_snapshot_interval_s"] = int(value)
    if value := os.environ.get("OPS_OBSERVER_UPSTREAM_WS_PING_INTERVAL_S"):
        raw["upstream_ws_ping_interval_s"] = int(value)
    if value := os.environ.get("OPS_OBSERVER_UPSTREAM_WS_RETRY_INTERVAL_S"):
        raw["upstream_ws_retry_interval_s"] = int(value)
