from pathlib import Path

from app.services.runtime_config import RuntimeConfigManager
from app.settings import RuntimeSettings


def test_gateway_config_rewrites_rules_file(tmp_path: Path, monkeypatch) -> None:
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text("alert_rules: {}\n", encoding="utf-8")

    settings = RuntimeSettings()
    manager = RuntimeConfigManager(settings)
    monkeypatch.setattr(manager, "_rules_path", rules_path)

    manager.update_from_gateway_config(
        {
            "alert_rules": {
                "DEVICE_OFFLINE": {
                    "enabled": True,
                    "timeout_s": 30,
                    "level": "warning",
                }
            }
        }
    )

    assert "DEVICE_OFFLINE" in rules_path.read_text(encoding="utf-8")
