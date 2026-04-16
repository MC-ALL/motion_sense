from pathlib import Path

from app.settings import load_runtime_settings


def test_load_runtime_settings_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "simulator_settings.yaml"
    path.write_text(
        """
gym_id: gym-test-02
mqtt:
  host: broker.local
  port: 1884
scenario:
  equipment_count: 12
  wristband_count: 8
  env_count: 10
""".strip(),
        encoding="utf-8",
    )

    settings = load_runtime_settings(path)

    assert settings.gym_id == "gym-test-02"
    assert settings.mqtt.host == "broker.local"
    assert settings.mqtt.port == 1884
    assert settings.scenario.equipment_count == 12
    assert settings.scenario.wristband_count == 8
    assert settings.scenario.env_count == 10
