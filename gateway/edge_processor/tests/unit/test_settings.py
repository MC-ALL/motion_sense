from pathlib import Path

from app.settings import load_settings


def test_load_settings_reads_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "app_settings.yaml"
    config_path.write_text(
        "\n".join(
            [
                'app_name: "custom-edge-processor"',
                'gateway_id: "gw-local-001"',
                "batch_interval_s: 12",
                "backend:",
                '  base_url: "http://backend:8000/api/v1"',
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.app_name == "custom-edge-processor"
    assert settings.gateway_id == "gw-local-001"
    assert settings.batch_interval_s == 12
    assert settings.backend.base_url == "http://backend:8000/api/v1"
