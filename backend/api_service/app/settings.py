from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError


DEFAULT_CONFIG_PATH = Path("/runtime/config/backend/api_service/app_settings.yaml")
DEFAULT_AI_API_KEY_PATH = Path("/runtime/secrets/backend_ai_api_key.txt")
DEFAULT_GATEWAY_COMMAND_TOKEN_PATH = Path("/runtime/secrets/backend_gateway_command_token.txt")
AI_MODEL_VARIANT_MAPPING = {
    "chat": "deepseek-chat",
    "reasoner": "deepseek-reasoner",
}


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


class RedisSettings(BaseModel):
    host: str = "redis"
    port: int = 6379
    db: int = 0
    channel: str = "motion_sense:realtime_events"

    def url(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.db}"


class DeviceCommandSettings(BaseModel):
    topic_prefix: str = "gym"
    default_qos: int = 1
    default_retain: bool = False
    pending_fetch_limit: int = 100
    max_attempts: int = 3
    retry_backoff_s: int = 5
    delivery_lease_s: int = 15
    expire_after_s: int = 300
    gateway_channel_token: str | None = None
    gateway_channel_token_file: str | None = None


class AuthAdminSettings(BaseModel):
    username: str = "admin"
    password_hash: str = ""


class AuthJwtSettings(BaseModel):
    access_secret: str = ""
    refresh_secret: str = ""


class AuthSettings(BaseModel):
    enforce_rest: bool = False
    enforce_ws: bool = False
    issuer: str = "motion_sense_backend"
    audience: str = "motion_sense_api"
    access_token_ttl_s: int = 900
    refresh_token_ttl_s: int = 604800
    admin: AuthAdminSettings = Field(default_factory=AuthAdminSettings)
    jwt: AuthJwtSettings = Field(default_factory=AuthJwtSettings)


class AiSettings(BaseModel):
    auto_process: bool = True
    poll_interval_s: int = 5
    batch_size: int = 4
    wakeup_backend: Literal["local", "redis"] = "local"
    wakeup_channel: str = "motion_sense:ai_report_wakeup"
    provider: str = "builtin"
    base_url: str | None = None
    model_variant: str = "reasoner"
    model: str | None = None
    api_key: str | None = None
    api_key_file: str | None = None
    request_timeout_s: int = 60
    max_tokens: int = 4096


class RuntimeSettings(BaseModel):
    app_name: str = "motion-sense-backend-api-service"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    storage_backend: str = "memory"
    realtime_backend: str = "local"
    realtime_telemetry_flush_interval_ms: int = 500
    ws_heartbeat_timeout_s: int = 45
    ops_refresh_interval_s: int = 15
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    device_command: DeviceCommandSettings = Field(default_factory=DeviceCommandSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    ai: AiSettings = Field(default_factory=AiSettings)


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
    redis = raw.setdefault("redis", {})
    device_command = raw.setdefault("device_command", {})
    auth = raw.setdefault("auth", {})
    auth_admin = auth.setdefault("admin", {})
    auth_jwt = auth.setdefault("jwt", {})
    ai = raw.setdefault("ai", {})

    if value := os.environ.get("BACKEND_API_HOST"):
        raw["host"] = value
    if value := os.environ.get("BACKEND_API_PORT"):
        raw["port"] = int(value)
    if value := os.environ.get("BACKEND_API_LOG_LEVEL"):
        raw["log_level"] = value
    if value := os.environ.get("BACKEND_STORAGE_BACKEND"):
        raw["storage_backend"] = value
    if value := os.environ.get("BACKEND_REALTIME_BACKEND"):
        raw["realtime_backend"] = value
    if value := os.environ.get("BACKEND_REALTIME_TELEMETRY_FLUSH_INTERVAL_MS"):
        raw["realtime_telemetry_flush_interval_ms"] = int(value)
    if value := os.environ.get("BACKEND_OPS_REFRESH_INTERVAL_S"):
        raw["ops_refresh_interval_s"] = int(value)
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
    if value := os.environ.get("BACKEND_REDIS_HOST"):
        redis["host"] = value
    if value := os.environ.get("BACKEND_REDIS_PORT"):
        redis["port"] = int(value)
    if value := os.environ.get("BACKEND_REDIS_DB"):
        redis["db"] = int(value)
    if value := os.environ.get("BACKEND_REDIS_CHANNEL"):
        redis["channel"] = value
    if value := os.environ.get("BACKEND_COMMAND_TOPIC_PREFIX"):
        device_command["topic_prefix"] = value
    if value := os.environ.get("BACKEND_COMMAND_DEFAULT_QOS"):
        device_command["default_qos"] = int(value)
    if value := os.environ.get("BACKEND_COMMAND_DEFAULT_RETAIN"):
        device_command["default_retain"] = value.lower() in {"1", "true", "yes", "on"}
    if value := os.environ.get("BACKEND_COMMAND_PENDING_FETCH_LIMIT"):
        device_command["pending_fetch_limit"] = int(value)
    if value := os.environ.get("BACKEND_COMMAND_MAX_ATTEMPTS"):
        device_command["max_attempts"] = int(value)
    if value := os.environ.get("BACKEND_COMMAND_RETRY_BACKOFF_S"):
        device_command["retry_backoff_s"] = int(value)
    if value := os.environ.get("BACKEND_COMMAND_DELIVERY_LEASE_S"):
        device_command["delivery_lease_s"] = int(value)
    if value := os.environ.get("BACKEND_COMMAND_EXPIRE_AFTER_S"):
        device_command["expire_after_s"] = int(value)
    if value := os.environ.get("BACKEND_COMMAND_GATEWAY_CHANNEL_TOKEN"):
        device_command["gateway_channel_token"] = value
    if value := os.environ.get("BACKEND_COMMAND_GATEWAY_CHANNEL_TOKEN_FILE"):
        device_command["gateway_channel_token_file"] = value
    if value := os.environ.get("BACKEND_AUTH_ENFORCE_REST"):
        auth["enforce_rest"] = value.lower() in {"1", "true", "yes", "on"}
    if value := os.environ.get("BACKEND_AUTH_ENFORCE_WS"):
        auth["enforce_ws"] = value.lower() in {"1", "true", "yes", "on"}
    if value := os.environ.get("BACKEND_AUTH_ISSUER"):
        auth["issuer"] = value
    if value := os.environ.get("BACKEND_AUTH_AUDIENCE"):
        auth["audience"] = value
    if value := os.environ.get("BACKEND_AUTH_ACCESS_TOKEN_TTL_S"):
        auth["access_token_ttl_s"] = int(value)
    if value := os.environ.get("BACKEND_AUTH_REFRESH_TOKEN_TTL_S"):
        auth["refresh_token_ttl_s"] = int(value)
    if value := os.environ.get("BACKEND_AUTH_ADMIN_USERNAME"):
        auth_admin["username"] = value
    if value := os.environ.get("BACKEND_AUTH_ADMIN_PASSWORD_HASH"):
        auth_admin["password_hash"] = value
    if value := os.environ.get("BACKEND_AUTH_ACCESS_SECRET"):
        auth_jwt["access_secret"] = value
    if value := os.environ.get("BACKEND_AUTH_REFRESH_SECRET"):
        auth_jwt["refresh_secret"] = value
    if value := os.environ.get("BACKEND_AI_AUTO_PROCESS"):
        ai["auto_process"] = value.lower() in {"1", "true", "yes", "on"}
    if value := os.environ.get("BACKEND_AI_POLL_INTERVAL_S"):
        ai["poll_interval_s"] = int(value)
    if value := os.environ.get("BACKEND_AI_BATCH_SIZE"):
        ai["batch_size"] = int(value)
    if value := os.environ.get("BACKEND_AI_WAKEUP_BACKEND"):
        ai["wakeup_backend"] = value
    if value := os.environ.get("BACKEND_AI_WAKEUP_CHANNEL"):
        ai["wakeup_channel"] = value
    if value := os.environ.get("BACKEND_AI_PROVIDER"):
        ai["provider"] = value
    if value := os.environ.get("BACKEND_AI_BASE_URL"):
        ai["base_url"] = value
    if value := os.environ.get("BACKEND_AI_MODEL_VARIANT"):
        ai["model_variant"] = value
    if value := os.environ.get("BACKEND_AI_MODEL"):
        ai["model"] = value
    if value := os.environ.get("BACKEND_AI_API_KEY"):
        ai["api_key"] = value
    if value := os.environ.get("BACKEND_AI_API_KEY_FILE"):
        ai["api_key_file"] = value
    if value := os.environ.get("BACKEND_AI_REQUEST_TIMEOUT_S"):
        ai["request_timeout_s"] = int(value)
    if value := os.environ.get("BACKEND_AI_MAX_TOKENS"):
        ai["max_tokens"] = int(value)

    _apply_ai_model_variant(ai)
    _apply_ai_secret_file(ai)
    _apply_gateway_command_secret_file(device_command)


def _apply_ai_model_variant(ai: dict[str, Any]) -> None:
    configured_model = ai.get("model")
    if isinstance(configured_model, str) and configured_model.strip():
        ai["model"] = configured_model.strip()
        return

    configured_variant = ai.get("model_variant")
    variant = configured_variant.strip() if isinstance(configured_variant, str) else ""
    if not variant:
        variant = "reasoner"

    resolved_model = AI_MODEL_VARIANT_MAPPING.get(variant)
    if resolved_model is None:
        raise RuntimeError(
            "invalid backend ai model_variant: "
            f"{variant} (expected one of: {', '.join(sorted(AI_MODEL_VARIANT_MAPPING))})"
        )

    ai["model_variant"] = variant
    ai["model"] = resolved_model


def _apply_ai_secret_file(ai: dict[str, Any]) -> None:
    configured_path = ai.get("api_key_file")
    candidate_path = Path(configured_path) if isinstance(configured_path, str) and configured_path else DEFAULT_AI_API_KEY_PATH
    ai["api_key_file"] = str(candidate_path)
    if ai.get("api_key"):
        return
    if not candidate_path.exists():
        return
    secret_value = candidate_path.read_text(encoding="utf-8").strip()
    if secret_value:
        ai["api_key"] = secret_value


def _apply_gateway_command_secret_file(device_command: dict[str, Any]) -> None:
    configured_path = device_command.get("gateway_channel_token_file")
    candidate_path = (
        Path(configured_path)
        if isinstance(configured_path, str) and configured_path
        else DEFAULT_GATEWAY_COMMAND_TOKEN_PATH
    )
    device_command["gateway_channel_token_file"] = str(candidate_path)
    if device_command.get("gateway_channel_token"):
        return
    if not candidate_path.exists():
        return
    secret_value = candidate_path.read_text(encoding="utf-8").strip()
    if secret_value:
        device_command["gateway_channel_token"] = secret_value
