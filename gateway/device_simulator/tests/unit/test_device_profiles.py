from app.device_profiles import build_device_profiles
from app.settings import RuntimeSettings


def test_build_device_profiles_uses_expected_counts() -> None:
    settings = RuntimeSettings.model_validate(
        {
            "gym_id": "gym-test-01",
            "scenario": {
                "equipment_count": 10,
                "wristband_count": 10,
                "env_count": 10,
            },
        }
    )

    profiles = build_device_profiles(settings)

    assert len(profiles.equipment) == 10
    assert len(profiles.wristbands) == 10
    assert len(profiles.env_nodes) == 10
    assert profiles.equipment[0].identity.device_id == "eq-001"
    assert profiles.wristbands[0].relay_equipment_id == "eq-001"
    assert profiles.env_nodes[-1].identity.device_id == "env-010"
