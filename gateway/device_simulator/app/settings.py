from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


DEFAULT_RUNTIME_SETTINGS_PATH = Path("/runtime/config/device_simulator/simulator_settings.yaml")


class MqttSettings(BaseModel):
    host: str = "mosquitto"
    port: int = 1883
    username: str = "admin"
    password: str = "admin123"
    client_id: str = "device-simulator"
    keepalive_s: int = 60
    qos: int = Field(default=1, ge=0, le=2)
    publish_queue_size: int = Field(default=4096, ge=128, le=65536)


class IntervalSettings(BaseModel):
    equipment_telemetry_ms: int = Field(default=1000, ge=50)
    wristband_telemetry_ms: int = Field(default=500, ge=50)
    env_telemetry_ms: int = Field(default=5000, ge=500)
    status_interval_s: int = Field(default=15, ge=1)
    startup_jitter_ms: int = Field(default=1500, ge=0)


class ScenarioSettings(BaseModel):
    equipment_count: int = Field(default=10, ge=1)
    wristband_count: int = Field(default=10, ge=1)
    env_count: int = Field(default=10, ge=0)
    random_seed: int = 20260416
    offline_ratio: float = Field(default=0.015, ge=0.0, le=1.0)
    p0_alert_ratio: float = Field(default=0.01, ge=0.0, le=1.0)
    battery_low_ratio: float = Field(default=0.003, ge=0.0, le=1.0)
    equipment_overload_ratio: float = Field(default=0.04, ge=0.0, le=1.0)
    env_anomaly_ratio: float = Field(default=0.06, ge=0.0, le=1.0)
    bind_change_ratio: float = Field(default=0.02, ge=0.0, le=1.0)


class RuntimeSettings(BaseModel):
    gym_id: str = "gym-gz-01"
    mqtt: MqttSettings = Field(default_factory=MqttSettings)
    intervals: IntervalSettings = Field(default_factory=IntervalSettings)
    scenario: ScenarioSettings = Field(default_factory=ScenarioSettings)


def load_runtime_settings(path: Path | None = None) -> RuntimeSettings:
    settings_path = path or DEFAULT_RUNTIME_SETTINGS_PATH
    raw: dict[str, Any] = {}
    if settings_path.exists():
        loaded = yaml.safe_load(settings_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            raw = loaded
    return RuntimeSettings.model_validate(raw)
