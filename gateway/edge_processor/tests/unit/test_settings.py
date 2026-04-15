from pathlib import Path

from app.settings import load_settings


def test_load_settings_reads_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "app_settings.yaml"
    config_path.write_text(
        "\n".join(
            [
                'app_name: "custom-edge-processor"',
                'gateway_id: "gw-local-001"',
                'gym_id: "gym-gz-01"',
                "batch_interval_s: 12",
                "command_poll_interval_s: 4",
                "backend:",
                '  base_url: "http://backend:8000/api/v1"',
                '  gateway_command_pending_path: "/gateway/{gateway_id}/commands/pending"',
                "influxdb:",
                '  base_url: "http://influxdb:8181"',
                '  database_name: "gym_local"',
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.app_name == "custom-edge-processor"
    assert settings.gateway_id == "gw-local-001"
    assert settings.gym_id == "gym-gz-01"
    assert settings.batch_interval_s == 12
    assert settings.command_poll_interval_s == 4
    assert settings.backend.base_url == "http://backend:8000/api/v1"
    assert settings.backend.gateway_command_pending_path == "/gateway/{gateway_id}/commands/pending"
    assert settings.influxdb.base_url == "http://influxdb:8181"
    assert settings.influxdb.database_name == "gym_local"


def test_load_settings_applies_health_and_backend_env_overrides(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "app_settings.yaml"
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("EDGE_PROCESSOR_HEALTH_INTERVAL_S", "6")
    monkeypatch.setenv("EDGE_PROCESSOR_RULES_RELOAD_INTERVAL_S", "9")
    monkeypatch.setenv("EDGE_PROCESSOR_BACKEND_REQUEST_TIMEOUT_S", "7.5")
    monkeypatch.setenv("EDGE_PROCESSOR_BACKEND_HEALTH_PATH", "/healthz")
    monkeypatch.setenv("EDGE_PROCESSOR_MQTT_CLIENT_ID", "gw-test-client")
    monkeypatch.setenv("EDGE_PROCESSOR_MQTT_QOS", "2")

    settings = load_settings(config_path)

    assert settings.health_interval_s == 6
    assert settings.rules_reload_interval_s == 9
    assert settings.backend.request_timeout_s == 7.5
    assert settings.backend.health_path == "/healthz"
    assert settings.mqtt.client_id == "gw-test-client"
    assert settings.mqtt.qos == 2
