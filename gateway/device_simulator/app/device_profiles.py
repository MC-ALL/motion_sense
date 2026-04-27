from __future__ import annotations

from app.models import DeviceIdentity, EnvProfile, EquipmentProfile, SimulatorProfiles, WristbandProfile
from app.settings import RuntimeSettings


def build_device_profiles(settings: RuntimeSettings) -> SimulatorProfiles:
    """Build deterministic simulator device profiles from runtime settings.

    :param settings: Runtime settings containing gym ID and device counts.
    :return: Equipment, wristband, and environment profiles used by the
        scenario engine.
    """
    gym_id = settings.gym_id
    equipment: list[EquipmentProfile] = []
    wristbands: list[WristbandProfile] = []
    env_nodes: list[EnvProfile] = []

    for index in range(1, settings.scenario.equipment_count + 1):
        device_id = f"eq-{index:03d}"
        equipment.append(
            EquipmentProfile(
                identity=DeviceIdentity(gym_id=gym_id, device_type="equipment", device_id=device_id),
                display_name=f"器材 {index:03d}",
                rated_power_w=480.0 + index * 12.0,
                idle_power_w=8.0 + index * 0.25,
                nominal_power_w=180.0 + index * 6.0,
                firmware_version="sim-equipment-1.0.0",
                mac=f"02:00:10:00:00:{index:02x}",
            )
        )

    for index in range(1, settings.scenario.wristband_count + 1):
        device_id = f"wb-{index:03d}"
        relay_equipment_id = equipment[index - 1].identity.device_id if index <= len(equipment) else None
        wristbands.append(
            WristbandProfile(
                identity=DeviceIdentity(gym_id=gym_id, device_type="wristband", device_id=device_id),
                display_name=f"手环 {index:03d}",
                relay_equipment_id=relay_equipment_id,
                firmware_version="sim-wristband-1.0.0",
                mac=f"02:00:20:00:00:{index:02x}",
            )
        )

    for index in range(1, settings.scenario.env_count + 1):
        device_id = f"env-{index:03d}"
        env_nodes.append(
            EnvProfile(
                identity=DeviceIdentity(gym_id=gym_id, device_type="env", device_id=device_id),
                display_name=f"环境节点 {index:03d}",
                location=f"区域 {index:02d}",
                firmware_version="sim-env-1.0.0",
                mac=f"02:00:30:00:00:{index:02x}",
            )
        )

    return SimulatorProfiles(equipment=equipment, wristbands=wristbands, env_nodes=env_nodes)
