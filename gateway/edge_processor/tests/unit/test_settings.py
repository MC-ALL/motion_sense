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
