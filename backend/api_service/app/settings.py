from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError


DEFAULT_CONFIG_PATH = Path("/runtime/config/backend/api_service/app_settings.yaml")


class RuntimeSettings(BaseModel):
    app_name: str = "motion-sense-backend-api-service"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    ws_heartbeat_timeout_s: int = 45
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


def load_settings(config_path: Path | str = DEFAULT_CONFIG_PATH) -> RuntimeSettings:
    path = Path(config_path)
    raw: dict[str, Any] = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    _apply_env_overrides(raw)

    try:
        return RuntimeSettings.model_validate(raw)
    except ValidationError as exc:
        raise RuntimeError(f"invalid backend config at {path}: {exc}") from exc


def _apply_env_overrides(raw: dict[str, Any]) -> None:
    if value := os.environ.get("BACKEND_API_HOST"):
        raw["host"] = value
    if value := os.environ.get("BACKEND_API_PORT"):
        raw["port"] = int(value)
    if value := os.environ.get("BACKEND_API_LOG_LEVEL"):
        raw["log_level"] = value
