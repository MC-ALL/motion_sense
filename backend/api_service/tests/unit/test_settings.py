from __future__ import annotations

from pathlib import Path

from app.settings import load_settings


def test_load_settings_reads_ai_api_key_from_secret_file(tmp_path: Path) -> None:
    config_path = tmp_path / "app_settings.yaml"
    secret_path = tmp_path / "backend_ai_api_key.txt"
    config_path.write_text(
        "\n".join(
            [
                "app_name: motion-sense-backend-api-service",
                "ai:",
                "  provider: openai_compatible",
                f"  api_key_file: {secret_path}",
                "  api_key: null",
            ]
        ),
        encoding="utf-8",
    )
    secret_path.write_text("token-from-file\n", encoding="utf-8")

    settings = load_settings(config_path)

    assert settings.ai.provider == "openai_compatible"
    assert settings.ai.api_key_file == str(secret_path)
    assert settings.ai.api_key == "token-from-file"


def test_load_settings_resolves_ai_model_from_variant(tmp_path: Path) -> None:
    config_path = tmp_path / "app_settings.yaml"
    config_path.write_text(
        "\n".join(
            [
                "app_name: motion-sense-backend-api-service",
                "ai:",
                "  provider: openai_compatible",
                "  model_variant: chat",
                "  model: null",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.ai.provider == "openai_compatible"
    assert settings.ai.model_variant == "chat"
    assert settings.ai.model == "deepseek-chat"


def test_load_settings_reads_gateway_command_token_from_secret_file(tmp_path: Path) -> None:
    config_path = tmp_path / "app_settings.yaml"
    secret_path = tmp_path / "backend_gateway_command_token.txt"
    config_path.write_text(
        "\n".join(
            [
                "app_name: motion-sense-backend-api-service",
                "device_command:",
                f"  gateway_channel_token_file: {secret_path}",
                "  gateway_channel_token: null",
            ]
        ),
        encoding="utf-8",
    )
    secret_path.write_text("gateway-command-token\n", encoding="utf-8")

    settings = load_settings(config_path)

    assert settings.device_command.gateway_channel_token_file == str(secret_path)
    assert settings.device_command.gateway_channel_token == "gateway-command-token"
