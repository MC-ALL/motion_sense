from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


DeviceType = Literal["equipment", "wristband", "env"]


@dataclass(frozen=True)
class DeviceIdentity:
    """Stable MQTT identity for one simulated device."""

    gym_id: str
    device_type: DeviceType
    device_id: str


@dataclass(frozen=True)
class EquipmentProfile:
    """Static profile used to generate equipment telemetry."""

    identity: DeviceIdentity
    display_name: str
    rated_power_w: float
    idle_power_w: float
    nominal_power_w: float
    firmware_version: str
    mac: str


@dataclass(frozen=True)
class WristbandProfile:
    """Static profile used to generate wristband telemetry and bindings."""

    identity: DeviceIdentity
    display_name: str
    relay_equipment_id: str | None
    firmware_version: str
    mac: str


@dataclass(frozen=True)
class EnvProfile:
    """Static profile used to generate environment node telemetry."""

    identity: DeviceIdentity
    display_name: str
    location: str
    firmware_version: str
    mac: str


@dataclass(frozen=True)
class SimulatorProfiles:
    """Grouped simulator profiles for all generated device types."""

    equipment: list[EquipmentProfile]
    wristbands: list[WristbandProfile]
    env_nodes: list[EnvProfile]


@dataclass(frozen=True)
class PublishedMessage:
    """MQTT message prepared by the scenario engine.

    :param topic: Destination MQTT topic.
    :param payload: JSON-compatible payload to publish.
    :param retain: Whether the broker should retain this message.
    """

    topic: str
    payload: dict[str, object]
    retain: bool = False
