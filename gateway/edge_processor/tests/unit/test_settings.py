from __future__ import annotations

from pathlib import Path

from app.settings import load_settings


def test_load_settings_reads_gateway_command_channel_token_from_secret_file(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "app_settings.yaml"
    secret_path = tmp_path / "backend_gateway_command_token.txt"
    config_path.write_text(
        "\n".join(
            [
                "app_name: motion-sense-edge-processor",
                "backend:",
                f"  gateway_command_channel_token_file: {secret_path}",
                "  gateway_command_channel_token: null",
            ]
        ),
        encoding="utf-8",
    )
    secret_path.write_text("gateway-command-token\n", encoding="utf-8")

    settings = load_settings(config_path)

    assert settings.backend.gateway_command_channel_token_file == str(secret_path)
    assert settings.backend.gateway_command_channel_token == "gateway-command-token"


def test_load_settings_reads_batch_aggregation_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "app_settings.yaml"
    config_path.write_text(
        "\n".join(
            [
                "app_name: motion-sense-edge-processor",
                "batch_interval_s: 10",
                "batch_min_window_s: 0.5",
                "batch_trigger_threshold: 32",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.batch_interval_s == 10
    assert settings.batch_min_window_s == 0.5
    assert settings.batch_trigger_threshold == 32
