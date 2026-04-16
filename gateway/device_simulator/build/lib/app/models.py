from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


DeviceType = Literal["equipment", "wristband", "env"]


@dataclass(frozen=True)
class DeviceIdentity:
    gym_id: str
    device_type: DeviceType
    device_id: str


@dataclass(frozen=True)
class EquipmentProfile:
    identity: DeviceIdentity
    display_name: str
    rated_power_w: float
    idle_power_w: float
    nominal_power_w: float
    firmware_version: str
    ip_address: str


@dataclass(frozen=True)
class WristbandProfile:
    identity: DeviceIdentity
    display_name: str
    relay_equipment_id: str | None
    firmware_version: str
    ip_address: str


@dataclass(frozen=True)
class EnvProfile:
    identity: DeviceIdentity
    display_name: str
    location: str
    firmware_version: str
    ip_address: str


@dataclass(frozen=True)
class SimulatorProfiles:
    equipment: list[EquipmentProfile]
    wristbands: list[WristbandProfile]
    env_nodes: list[EnvProfile]


@dataclass(frozen=True)
class PublishedMessage:
    topic: str
    payload: dict[str, object]
    retain: bool = False

