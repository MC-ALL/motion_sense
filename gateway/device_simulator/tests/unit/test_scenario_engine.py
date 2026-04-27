from app.device_profiles import build_device_profiles
from app.scenario_engine import ScenarioEngine
from app.settings import RuntimeSettings


def _engine() -> ScenarioEngine:
    settings = RuntimeSettings.model_validate(
        {
            "scenario": {
                "equipment_count": 1,
                "wristband_count": 1,
                "env_count": 1,
                "random_seed": 1,
                "offline_ratio": 0,
                "p0_alert_ratio": 0,
                "battery_low_ratio": 0,
                "equipment_overload_ratio": 0,
                "env_anomaly_ratio": 0,
                "bind_change_ratio": 0,
            }
        }
    )
    return ScenarioEngine(settings, build_device_profiles(settings))


def test_equipment_messages_follow_mqtt_schema() -> None:
    """Verify equipment status and telemetry payloads use schema rc1 fields."""
    messages = _engine().step_equipment("eq-001", 1712640000)

    status = next(item.payload for item in messages if item.topic.endswith("/status"))
    telemetry = next(item.payload for item in messages if item.topic.endswith("/telemetry"))

    assert status == {
        "ts": 1712640000,
        "status": "standby",
        "firmware_version": "sim-equipment-1.0.0",
        "mac": "02:00:10:00:00:01",
    }
    assert "device_id" not in telemetry
    assert "status" not in telemetry
    assert telemetry["rated_power_w"] == 492.0


def test_wristband_messages_follow_mqtt_schema() -> None:
    """Verify wristband telemetry uses list IMU fields and schema names."""
    messages = _engine().step_wristband("wb-001", 1712640000)

    status = next(item.payload for item in messages if item.topic.endswith("/status"))
    telemetry = next(item.payload for item in messages if item.topic.endswith("/telemetry"))

    assert status == {
        "ts": 1712640000,
        "status": "standby",
        "firmware_version": "sim-wristband-1.0.0",
        "mac": "02:00:20:00:00:01",
    }
    assert "device_id" not in telemetry
    assert len(telemetry["accel"]) == 3
    assert len(telemetry["gyro"]) == 3
    assert telemetry["flags"] == 0
    assert "relayed_by" in telemetry


def test_env_messages_follow_mqtt_schema() -> None:
    """Verify environment telemetry excludes removed legacy fields."""
    messages = _engine().step_env("env-001", 1712640000)

    status = next(item.payload for item in messages if item.topic.endswith("/status"))
    telemetry = next(item.payload for item in messages if item.topic.endswith("/telemetry"))

    assert status == {
        "ts": 1712640000,
        "status": "standby",
        "firmware_version": "sim-env-1.0.0",
        "mac": "02:00:30:00:00:01",
    }
    for removed_field in ("device_id", "node_id", "pm1_0", "pm10", "wifi_rssi"):
        assert removed_field not in telemetry


def test_wristband_binding_and_alerts_follow_mqtt_schema() -> None:
    """Verify binding and direct wristband alerts use schema rc1 fields."""
    engine = _engine()
    state = engine._wristbands["wb-001"]
    state.bound_equipment_id = "eq-001"
    state.battery_pct = 9
    state.battery_low_sent = False
    state.rng.random = lambda: 0.0
    engine._settings.scenario.bind_change_ratio = 1

    messages = engine.step_wristband("wb-001", 1712640000)
    bindings = [item.payload for item in messages if item.topic.endswith("/binding")]
    alerts = [item.payload for item in messages if item.topic.endswith("/alert")]

    assert bindings
    assert set(bindings[0]) == {"ts", "equipment_id", "bound", "reason"}
    assert isinstance(bindings[0]["bound"], bool)
    assert alerts[0]["alert_type"] == "battery_low"
    assert alerts[0]["priority"] == "P2"
    assert "code" not in alerts[0]
    assert "device_id" not in alerts[0]
