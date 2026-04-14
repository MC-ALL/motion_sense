from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError


DEFAULT_CONFIG_PATH = Path("/runtime/config/backend/api_service/app_settings.yaml")


class DatabaseSettings(BaseModel):
    host: str = "timescaledb"
    port: int = 5432
    dbname: str = "motion_sense"
    user: str = "motion_sense"
    password: str | None = None
    min_pool_size: int = 1
    max_pool_size: int = 8

    def dsn(self) -> str:
        password = self.password or ""
        return (
            f"postgresql://{self.user}:{password}@{self.host}:{self.port}/{self.dbname}"
        )


class RuntimeSettings(BaseModel):
    app_name: str = "motion-sense-backend-api-service"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    storage_backend: str = "memory"
    ws_heartbeat_timeout_s: int = 45
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)


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
    database = raw.setdefault("database", {})

    if value := os.environ.get("BACKEND_API_HOST"):
        raw["host"] = value
    if value := os.environ.get("BACKEND_API_PORT"):
        raw["port"] = int(value)
    if value := os.environ.get("BACKEND_API_LOG_LEVEL"):
        raw["log_level"] = value
    if value := os.environ.get("BACKEND_STORAGE_BACKEND"):
        raw["storage_backend"] = value
    if value := os.environ.get("BACKEND_DATABASE_HOST"):
        database["host"] = value
    if value := os.environ.get("BACKEND_DATABASE_PORT"):
        database["port"] = int(value)
    if value := os.environ.get("BACKEND_DATABASE_NAME"):
        database["dbname"] = value
    if value := os.environ.get("BACKEND_DATABASE_USER"):
        database["user"] = value
    if value := os.environ.get("BACKEND_DATABASE_PASSWORD"):
        database["password"] = value
    if value := os.environ.get("BACKEND_DATABASE_MIN_POOL_SIZE"):
        database["min_pool_size"] = int(value)
    if value := os.environ.get("BACKEND_DATABASE_MAX_POOL_SIZE"):
        database["max_pool_size"] = int(value)
