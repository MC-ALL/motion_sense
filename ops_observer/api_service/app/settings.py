from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError


DEFAULT_CONFIG_PATH = Path("/runtime/config/ops_observer/api_service/app_settings.yaml")
DEFAULT_BACKEND_CONFIG_PATH = Path("/runtime/config/backend/api_service/app_settings.yaml")
DEFAULT_BACKEND_BOOTSTRAP_PATH = Path("/runtime/config/backend/api_service/bootstrap_admin.txt")
DEFAULT_GATEWAY_OPS_TOKEN_PATH = Path("/runtime/secrets/edge_processor_ops_token.txt")


class UpstreamModuleSettings(BaseModel):
    module_id: str
    module_type: Literal["gateway", "backend"]
    display_name: str
    base_url: str
    timeout_s: float = Field(default=5.0, gt=0)
    auth_token: str | None = None
    auth_username: str | None = None
    auth_password: str | None = None
    ws_enabled: bool = True
    ws_path: str = "/ops/ws"


class AlertThresholdSettings(BaseModel):
    stale_after_s: int = Field(default=60, ge=1)
    emit_recovery_alert: bool = True


class JwtAuthSettings(BaseModel):
    access_secret: str | None = None


class OpsApiAuthSettings(BaseModel):
    enforce_rest: bool = False
    enforce_ws: bool = False
    issuer: str = "motion_sense_backend"
    audience: str = "motion_sense_api"
    jwt: JwtAuthSettings = Field(default_factory=JwtAuthSettings)


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
    auth: OpsApiAuthSettings = Field(default_factory=OpsApiAuthSettings)
    upstream_modules: list[UpstreamModuleSettings] = Field(default_factory=list)


def load_settings(config_path: Path | str = DEFAULT_CONFIG_PATH) -> RuntimeSettings:
    path = Path(config_path)
    raw: dict[str, Any] = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    _apply_env_overrides(raw)
    _apply_runtime_fallbacks(raw)

    try:
        return RuntimeSettings.model_validate(raw)
    except ValidationError as exc:
        raise RuntimeError(f"invalid ops observer config at {path}: {exc}") from exc


def _apply_env_overrides(raw: dict[str, Any]) -> None:
    auth = raw.setdefault("auth", {})
    auth_jwt = auth.setdefault("jwt", {})
    upstream_modules = raw.setdefault("upstream_modules", [])
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
    if value := os.environ.get("OPS_OBSERVER_AUTH_ENFORCE_REST"):
        auth["enforce_rest"] = value.lower() in {"1", "true", "yes", "on"}
    if value := os.environ.get("OPS_OBSERVER_AUTH_ENFORCE_WS"):
        auth["enforce_ws"] = value.lower() in {"1", "true", "yes", "on"}
    if value := os.environ.get("OPS_OBSERVER_AUTH_ISSUER"):
        auth["issuer"] = value
    if value := os.environ.get("OPS_OBSERVER_AUTH_AUDIENCE"):
        auth["audience"] = value
    if value := os.environ.get("OPS_OBSERVER_AUTH_ACCESS_SECRET"):
        auth_jwt["access_secret"] = value
    _apply_upstream_override(upstream_modules, "gateway", "base_url", os.environ.get("OPS_OBSERVER_GATEWAY_BASE_URL"))
    _apply_upstream_override(upstream_modules, "backend", "base_url", os.environ.get("OPS_OBSERVER_BACKEND_BASE_URL"))
    _apply_upstream_override(upstream_modules, "gateway", "auth_token", os.environ.get("OPS_OBSERVER_GATEWAY_AUTH_TOKEN"))
    _apply_upstream_override(upstream_modules, "backend", "auth_token", os.environ.get("OPS_OBSERVER_BACKEND_AUTH_TOKEN"))
    _apply_upstream_override(upstream_modules, "gateway", "auth_username", os.environ.get("OPS_OBSERVER_GATEWAY_AUTH_USERNAME"))
    _apply_upstream_override(upstream_modules, "backend", "auth_username", os.environ.get("OPS_OBSERVER_BACKEND_AUTH_USERNAME"))
    _apply_upstream_override(upstream_modules, "gateway", "auth_password", os.environ.get("OPS_OBSERVER_GATEWAY_AUTH_PASSWORD"))
    _apply_upstream_override(upstream_modules, "backend", "auth_password", os.environ.get("OPS_OBSERVER_BACKEND_AUTH_PASSWORD"))
    _apply_upstream_override(upstream_modules, "gateway", "ws_enabled", _parse_optional_bool(os.environ.get("OPS_OBSERVER_GATEWAY_WS_ENABLED")))
    _apply_upstream_override(upstream_modules, "backend", "ws_enabled", _parse_optional_bool(os.environ.get("OPS_OBSERVER_BACKEND_WS_ENABLED")))
    _apply_upstream_override(upstream_modules, "gateway", "ws_path", os.environ.get("OPS_OBSERVER_GATEWAY_WS_PATH"))
    _apply_upstream_override(upstream_modules, "backend", "ws_path", os.environ.get("OPS_OBSERVER_BACKEND_WS_PATH"))


def _apply_runtime_fallbacks(raw: dict[str, Any]) -> None:
    auth = raw.setdefault("auth", {})
    auth_jwt = auth.setdefault("jwt", {})
    upstream_modules = raw.setdefault("upstream_modules", [])

    backend_config = _load_yaml(DEFAULT_BACKEND_CONFIG_PATH)
    if not auth_jwt.get("access_secret"):
        backend_secret = (
            backend_config.get("auth", {})
            .get("jwt", {})
            .get("access_secret")
        )
        if isinstance(backend_secret, str) and backend_secret:
            auth_jwt["access_secret"] = backend_secret

    gateway_ops_token = _read_text_file(DEFAULT_GATEWAY_OPS_TOKEN_PATH)
    if gateway_ops_token:
        _apply_upstream_fallback(upstream_modules, "gateway", "auth_token", gateway_ops_token)

    backend_username, backend_password = _load_bootstrap_admin(DEFAULT_BACKEND_BOOTSTRAP_PATH)
    if backend_username:
        _apply_upstream_fallback(upstream_modules, "backend", "auth_username", backend_username)
    if backend_password:
        _apply_upstream_fallback(upstream_modules, "backend", "auth_password", backend_password)


def _apply_upstream_override(
    upstream_modules: list[dict[str, Any]],
    module_type: str,
    key: str,
    value: Any,
) -> None:
    if value is None:
        return
    for item in upstream_modules:
        if item.get("module_type") == module_type:
            item[key] = value
            return


def _apply_upstream_fallback(
    upstream_modules: list[dict[str, Any]],
    module_type: str,
    key: str,
    value: Any,
) -> None:
    if value is None:
        return
    for item in upstream_modules:
        if item.get("module_type") == module_type and not item.get(key):
            item[key] = value
            return


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _read_text_file(path: Path) -> str | None:
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def _load_bootstrap_admin(path: Path) -> tuple[str | None, str | None]:
    if not path.exists():
        return None, None

    username: str | None = None
    password: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("username: "):
            username = line.removeprefix("username: ").strip() or None
        elif line.startswith("password: "):
            password = line.removeprefix("password: ").strip() or None
    return username, password


def _parse_optional_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.lower() in {"1", "true", "yes", "on"}
