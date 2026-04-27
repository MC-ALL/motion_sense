from __future__ import annotations

import random
from dataclasses import dataclass

from app.models import EnvProfile, EquipmentProfile, PublishedMessage, SimulatorProfiles, WristbandProfile
from app.settings import RuntimeSettings


def _topic(gym_id: str, device_type: str, device_id: str, action: str) -> str:
    """Build a gateway MQTT topic for simulated device output.

    :param gym_id: Gym identifier.
    :param device_type: Device type segment.
    :param device_id: Device identifier.
    :param action: MQTT action segment.
    :return: MQTT topic in gateway contract format.
    """
    return f"gym/{gym_id}/{device_type}/{device_id}/{action}"


def _consume_scheduled_event(
    *,
    rng: random.Random,
    now_s: int,
    ratio: float,
    interval_ms: int,
    current_next_at_s: int | None,
) -> tuple[bool, int | None]:
    """Return whether a scheduled scenario event is due and its next timestamp.

    ``ratio`` keeps the old per-tick probability meaning, but the simulator now
    converts it into an expected interval and spreads each device's first event
    across that interval. This avoids all devices drawing from the same
    second-level Bernoulli buckets.

    :param rng: Per-device random generator.
    :param now_s: Current Unix timestamp in seconds.
    :param ratio: Previous per-step event probability.
    :param interval_ms: Step interval for this device type.
    :param current_next_at_s: Previously scheduled event timestamp.
    :return: Pair of ``event_due`` and updated next event timestamp.
    """
    if ratio <= 0:
        return False, None
    if current_next_at_s is None:
        return False, _schedule_next_event_at(
            rng=rng,
            now_s=now_s,
            ratio=ratio,
            interval_ms=interval_ms,
            initial=True,
        )
    if now_s < current_next_at_s:
        return False, current_next_at_s
    return True, _schedule_next_event_at(
        rng=rng,
        now_s=now_s,
        ratio=ratio,
        interval_ms=interval_ms,
        initial=False,
    )


def _schedule_next_event_at(
    *,
    rng: random.Random,
    now_s: int,
    ratio: float,
    interval_ms: int,
    initial: bool,
) -> int:
    """Schedule the next scenario event while preserving expected frequency.

    :param rng: Per-device random generator.
    :param now_s: Current Unix timestamp in seconds.
    :param ratio: Previous per-step event probability.
    :param interval_ms: Step interval for this device type.
    :param initial: Whether this is the first schedule for the device.
    :return: Next due timestamp in Unix seconds.
    """
    step_s = max(interval_ms / 1000.0, 0.001)
    expected_interval_s = max(step_s, step_s / max(ratio, 0.000001))
    if initial:
        offset_s = rng.uniform(0.0, expected_interval_s)
    else:
        offset_s = rng.uniform(expected_interval_s * 0.5, expected_interval_s * 1.5)
    return now_s + max(1, int(round(offset_s)))


@dataclass
class EquipmentRuntimeState:
    """Mutable state for one simulated equipment device."""

    profile: EquipmentProfile
    rng: random.Random
    online: bool = True
    active: bool = False
    rep_count: int = 0
    energy_wh: float = 0.0
    overload_ticks: int = 0
    next_overload_at_s: int | None = None
    last_status_online: bool | None = None
    last_status_text: str | None = None
    last_status_ts: int | None = None


@dataclass
class WristbandRuntimeState:
    """Mutable state for one simulated wristband."""

    profile: WristbandProfile
    rng: random.Random
    online: bool = True
    battery_pct: float = 96.0
    step_count: int = 0
    bound_equipment_id: str | None = None
    last_binding_action: str | None = None
    last_status_online: bool | None = None
    last_status_text: str | None = None
    last_status_ts: int | None = None
    battery_low_sent: bool = False
    next_p0_alert_at_s: int | None = None
    next_battery_low_alert_at_s: int | None = None


@dataclass
class EnvRuntimeState:
    """Mutable state for one simulated environment node."""

    profile: EnvProfile
    rng: random.Random
    online: bool = True
    anomaly_ticks: int = 0
    anomaly_kind: str | None = None
    next_anomaly_at_s: int | None = None
    last_status_online: bool | None = None
    last_status_text: str | None = None
    last_status_ts: int | None = None


class ScenarioEngine:
    """Generate deterministic-but-randomized MQTT messages for all devices."""

    def __init__(self, settings: RuntimeSettings, profiles: SimulatorProfiles) -> None:
        """Initialize per-device runtime state and seeded random generators.

        :param settings: Runtime settings controlling scenario probabilities and
            timing.
        :param profiles: Static device profiles built for this simulator run.
        :return: None.
        """
        self._settings = settings
        seed_base = settings.scenario.random_seed
        self._equipment = {
            profile.identity.device_id: EquipmentRuntimeState(
                profile=profile,
                rng=random.Random(seed_base + 1000 + index),
            )
            for index, profile in enumerate(profiles.equipment, start=1)
        }
        self._wristbands = {
            profile.identity.device_id: WristbandRuntimeState(
                profile=profile,
                rng=random.Random(seed_base + 2000 + index),
                bound_equipment_id=profile.relay_equipment_id,
            )
            for index, profile in enumerate(profiles.wristbands, start=1)
        }
        self._env_nodes = {
            profile.identity.device_id: EnvRuntimeState(
                profile=profile,
                rng=random.Random(seed_base + 3000 + index),
            )
            for index, profile in enumerate(profiles.env_nodes, start=1)
        }

    def step_equipment(self, device_id: str, now_s: int) -> list[PublishedMessage]:
        """Advance one equipment device and return messages to publish.

        :param device_id: Equipment ID to advance.
        :param now_s: Current Unix timestamp in seconds.
        :return: Status and telemetry messages generated by this step.
        """
        state = self._equipment[device_id]
        scenario = self._settings.scenario

        if state.online and state.rng.random() < scenario.offline_ratio * 0.06:
            state.online = False
            state.active = False
        elif (not state.online) and state.rng.random() < 0.22:
            state.online = True

        messages: list[PublishedMessage] = []
        status_text = self._equipment_status_text(state)
        if self._should_emit_status(
            state.last_status_online,
            state.last_status_text,
            state.last_status_ts,
            state.online,
            status_text,
            now_s,
        ):
            messages.append(
                PublishedMessage(
                    topic=_topic(state.profile.identity.gym_id, "equipment", device_id, "status"),
                    payload=self._build_status_payload(
                        status=status_text,
                        ts=now_s,
                        firmware_version=state.profile.firmware_version,
                        mac=state.profile.mac,
                    ),
                    retain=True,
                )
            )
            state.last_status_online = state.online
            state.last_status_text = status_text
            state.last_status_ts = now_s

        if not state.online:
            return messages

        if state.rng.random() < 0.18:
            state.active = not state.active

        overload_triggered, state.next_overload_at_s = _consume_scheduled_event(
            rng=state.rng,
            now_s=now_s,
            ratio=scenario.equipment_overload_ratio,
            interval_ms=self._settings.intervals.equipment_telemetry_ms,
            current_next_at_s=state.next_overload_at_s,
        )
        if overload_triggered:
            state.overload_ticks = state.rng.randint(8, 18)
        elif state.overload_ticks > 0:
            state.overload_ticks -= 1

        power_w = state.profile.idle_power_w
        if state.active:
            power_w = state.profile.nominal_power_w * state.rng.uniform(0.82, 1.18)
            state.rep_count += state.rng.randint(0, 2)
        if state.overload_ticks > 0:
            power_w = state.profile.rated_power_w * state.rng.uniform(1.58, 1.88)

        state.energy_wh += power_w * (self._settings.intervals.equipment_telemetry_ms / 1000.0) / 3600.0
        voltage_v = 220.0 + state.rng.uniform(-2.0, 2.0)
        current_ma = power_w / max(voltage_v, 1.0) * 1000.0
        axis_angle = state.rng.uniform(5.0, 85.0) if state.active else state.rng.uniform(0.0, 10.0)

        messages.append(
            PublishedMessage(
                topic=_topic(state.profile.identity.gym_id, "equipment", device_id, "telemetry"),
                payload={
                    "ts": now_s,
                    "rep_count": state.rep_count,
                    "power_w": round(power_w, 2),
                    "rated_power_w": round(state.profile.rated_power_w, 2),
                    "energy_wh": round(state.energy_wh, 3),
                    "axis_angle": round(axis_angle, 2),
                    "voltage_v": round(voltage_v, 2),
                    "current_ma": round(current_ma, 2),
                },
            )
        )
        return messages

    def step_wristband(self, device_id: str, now_s: int) -> list[PublishedMessage]:
        """Advance one wristband and return messages to publish.

        :param device_id: Wristband ID to advance.
        :param now_s: Current Unix timestamp in seconds.
        :return: Status, binding, alert, and telemetry messages generated by
            this step.
        """
        state = self._wristbands[device_id]
        scenario = self._settings.scenario

        if state.online and state.rng.random() < scenario.offline_ratio * 0.08:
            state.online = False
            previous_equipment_id = state.bound_equipment_id
            state.bound_equipment_id = None
        else:
            previous_equipment_id = state.bound_equipment_id
            if (not state.online) and state.rng.random() < 0.3:
                state.online = True

        messages: list[PublishedMessage] = []
        status_text = "standby" if state.online else "offline"
        if self._should_emit_status(
            state.last_status_online,
            state.last_status_text,
            state.last_status_ts,
            state.online,
            status_text,
            now_s,
        ):
            messages.append(
                PublishedMessage(
                    topic=_topic(state.profile.identity.gym_id, "wristband", device_id, "status"),
                    payload=self._build_status_payload(
                        status=status_text,
                        ts=now_s,
                        firmware_version=state.profile.firmware_version,
                        mac=state.profile.mac,
                    ),
                    retain=True,
                )
            )
            state.last_status_online = state.online
            state.last_status_text = status_text
            state.last_status_ts = now_s

        if not state.online:
            if previous_equipment_id is not None:
                messages.append(
                    PublishedMessage(
                        topic=_topic(state.profile.identity.gym_id, "wristband", device_id, "binding"),
                        payload={
                            "ts": now_s,
                            "equipment_id": previous_equipment_id,
                            "bound": False,
                            "reason": "ble_disconnected",
                        },
                    )
                )
            return messages

        if state.rng.random() < scenario.bind_change_ratio:
            state.bound_equipment_id = self._pick_equipment_binding(
                current_equipment_id=state.bound_equipment_id,
                rng=state.rng,
            )

        if state.bound_equipment_id != previous_equipment_id:
            if previous_equipment_id is not None:
                messages.append(
                    PublishedMessage(
                        topic=_topic(state.profile.identity.gym_id, "wristband", device_id, "binding"),
                        payload={
                            "ts": now_s,
                            "equipment_id": previous_equipment_id,
                            "bound": False,
                            "reason": "idle_timeout",
                        },
                    )
                )
            if state.bound_equipment_id is not None:
                messages.append(
                    PublishedMessage(
                        topic=_topic(state.profile.identity.gym_id, "wristband", device_id, "binding"),
                        payload={
                            "ts": now_s,
                            "equipment_id": state.bound_equipment_id,
                            "bound": True,
                            "reason": "ble_connected",
                        },
                    )
                )

        equipment_state = self._equipment.get(state.bound_equipment_id or "")
        equipment_active = bool(equipment_state and equipment_state.online and equipment_state.active)
        base_heart_rate = 118 if equipment_active else 74
        heart_rate = max(38, int(base_heart_rate + state.rng.randint(-8, 14)))
        if equipment_active:
            state.step_count += state.rng.randint(1, 6)
        else:
            state.step_count += state.rng.randint(0, 1)
        state.battery_pct = max(0.0, state.battery_pct - state.rng.uniform(0.005, 0.035))

        messages.extend(self._maybe_emit_p0_alert(state, now_s, heart_rate))
        battery_low_retry_due = False
        if state.battery_low_sent:
            battery_low_retry_due, state.next_battery_low_alert_at_s = _consume_scheduled_event(
                rng=state.rng,
                now_s=now_s,
                ratio=scenario.battery_low_ratio,
                interval_ms=self._settings.intervals.wristband_telemetry_ms,
                current_next_at_s=state.next_battery_low_alert_at_s,
            )
        if state.battery_pct < 10.0 and ((not state.battery_low_sent) or battery_low_retry_due):
            messages.append(
                PublishedMessage(
                    topic=_topic(state.profile.identity.gym_id, "wristband", device_id, "alert"),
                    payload={
                        "ts": now_s,
                        "priority": "P2",
                        "level": "warning",
                        "alert_type": "battery_low",
                        "message": f"手环电量过低：{int(state.battery_pct)}%",
                        "value": int(state.battery_pct),
                        "threshold": 10,
                    },
                )
            )
            state.battery_low_sent = True

        telemetry_payload: dict[str, object] = {
            "ts": now_s,
            "heart_rate": heart_rate,
            "step_count": state.step_count,
            "battery_pct": int(round(state.battery_pct)),
            "current_equipment_id": state.bound_equipment_id,
            "relayed_by": state.bound_equipment_id,
            "accel": [
                state.rng.randint(-180, 180),
                state.rng.randint(-1050, -880),
                state.rng.randint(-180, 180),
            ],
            "gyro": [
                state.rng.randint(-12, 12),
                state.rng.randint(-12, 12),
                state.rng.randint(-12, 12),
            ],
            "flags": 0,
        }
        messages.append(
            PublishedMessage(
                topic=_topic(state.profile.identity.gym_id, "wristband", device_id, "telemetry"),
                payload=telemetry_payload,
            )
        )
        return messages

    def step_env(self, device_id: str, now_s: int) -> list[PublishedMessage]:
        """Advance one environment node and return messages to publish.

        :param device_id: Environment node ID to advance.
        :param now_s: Current Unix timestamp in seconds.
        :return: Status and telemetry messages generated by this step.
        """
        state = self._env_nodes[device_id]
        scenario = self._settings.scenario

        if state.online and state.rng.random() < scenario.offline_ratio * 0.05:
            state.online = False
        elif (not state.online) and state.rng.random() < 0.25:
            state.online = True

        messages: list[PublishedMessage] = []
        status_text = "standby" if state.online else "offline"
        if self._should_emit_status(
            state.last_status_online,
            state.last_status_text,
            state.last_status_ts,
            state.online,
            status_text,
            now_s,
        ):
            messages.append(
                PublishedMessage(
                    topic=_topic(state.profile.identity.gym_id, "env", device_id, "status"),
                    payload=self._build_status_payload(
                        status=status_text,
                        ts=now_s,
                        firmware_version=state.profile.firmware_version,
                        mac=state.profile.mac,
                    ),
                    retain=True,
                )
            )
            state.last_status_online = state.online
            state.last_status_text = status_text
            state.last_status_ts = now_s

        if not state.online:
            return messages

        anomaly_triggered, state.next_anomaly_at_s = _consume_scheduled_event(
            rng=state.rng,
            now_s=now_s,
            ratio=scenario.env_anomaly_ratio,
            interval_ms=self._settings.intervals.env_telemetry_ms,
            current_next_at_s=state.next_anomaly_at_s,
        )
        if state.anomaly_ticks <= 0 and anomaly_triggered:
            state.anomaly_ticks = state.rng.randint(3, 8)
            state.anomaly_kind = state.rng.choice(["co2", "pm2_5", "temperature"])
        elif state.anomaly_ticks > 0:
            state.anomaly_ticks -= 1
            if state.anomaly_ticks == 0:
                state.anomaly_kind = None

        temperature = 25.5 + state.rng.uniform(-1.5, 2.5)
        humidity = 58.0 + state.rng.uniform(-8.0, 8.0)
        co2_ppm = 780 + state.rng.randint(-90, 150)
        pm2_5 = 18 + state.rng.randint(-6, 10)
        if state.anomaly_kind == "co2":
            co2_ppm = state.rng.randint(1100, 1800)
        elif state.anomaly_kind == "pm2_5":
            pm2_5 = state.rng.randint(82, 150)
        elif state.anomaly_kind == "temperature":
            temperature = state.rng.uniform(35.5, 39.5)

        messages.append(
            PublishedMessage(
                topic=_topic(state.profile.identity.gym_id, "env", device_id, "telemetry"),
                payload={
                    "ts": now_s,
                    "temperature": round(temperature, 2),
                    "humidity": round(humidity, 2),
                    "co2_ppm": co2_ppm,
                    "pm2_5": pm2_5,
                    "lux": round(320 + state.rng.uniform(-45, 120), 2),
                },
            )
        )
        return messages

    def _should_emit_status(
        self,
        last_online: bool | None,
        last_status_text: str | None,
        last_status_ts: int | None,
        current_online: bool,
        current_status_text: str,
        now_s: int,
    ) -> bool:
        """Return whether a retained status message should be emitted.

        :param last_online: Previously published online flag.
        :param last_status_text: Previously published status text.
        :param last_status_ts: Timestamp of the previous status publish.
        :param current_online: Current online flag.
        :param current_status_text: Current status text.
        :param now_s: Current Unix timestamp in seconds.
        :return: ``True`` when status changed or the status interval elapsed.
        """
        interval_s = self._settings.intervals.status_interval_s
        if last_online is None or last_status_text is None or last_status_ts is None:
            return True
        if last_online != current_online or last_status_text != current_status_text:
            return True
        return now_s - last_status_ts >= interval_s

    def _equipment_status_text(self, state: EquipmentRuntimeState) -> str:
        """Resolve the public status text for equipment state.

        :param state: Equipment runtime state.
        :return: ``offline``, ``active``, or ``standby``.
        """
        if not state.online:
            return "offline"
        if state.active:
            return "active"
        return "standby"

    def _build_status_payload(
        self,
        *,
        status: str,
        ts: int,
        firmware_version: str,
        mac: str,
    ) -> dict[str, object]:
        """Build a status payload shared by simulated device types.

        :param status: Human-readable status text.
        :param ts: Payload timestamp in Unix seconds.
        :param firmware_version: Simulated firmware version.
        :param mac: Simulated device MAC address.
        :return: JSON-compatible status payload.
        """
        return {
            "ts": ts,
            "status": status,
            "firmware_version": firmware_version,
            "mac": mac,
        }

    def _pick_equipment_binding(self, *, current_equipment_id: str | None, rng: random.Random) -> str | None:
        """Select the next equipment binding for a wristband.

        :param current_equipment_id: Existing equipment binding, if any.
        :param rng: Per-wristband random generator.
        :return: New equipment ID, the current ID, or ``None`` for unbound.
        """
        online_candidates = [device_id for device_id, state in self._equipment.items() if state.online]
        if not online_candidates:
            return None
        if current_equipment_id and rng.random() < 0.35:
            return None
        if current_equipment_id in online_candidates and rng.random() < 0.6:
            return current_equipment_id
        return rng.choice(online_candidates)

    def _maybe_emit_p0_alert(self, state: WristbandRuntimeState, now_s: int, heart_rate: int) -> list[PublishedMessage]:
        """Maybe generate a critical wristband alert.

        :param state: Wristband runtime state.
        :param now_s: Current Unix timestamp in seconds.
        :param heart_rate: Heart rate value generated for this step.
        :return: Empty list or one P0 alert message.
        """
        triggered, state.next_p0_alert_at_s = _consume_scheduled_event(
            rng=state.rng,
            now_s=now_s,
            ratio=self._settings.scenario.p0_alert_ratio,
            interval_ms=self._settings.intervals.wristband_telemetry_ms,
            current_next_at_s=state.next_p0_alert_at_s,
        )
        if not triggered:
            return []
        alert_type = state.rng.choice(["heart_rate_high", "heart_rate_low", "fall_detected"])
        payload: dict[str, object] = {
            "ts": now_s,
            "priority": "P0",
            "level": "critical",
            "alert_type": alert_type,
        }
        if alert_type == "heart_rate_high":
            payload.update(
                {
                    "message": "心率过高：182 bpm，持续 35 s",
                    "value": max(182, heart_rate),
                    "threshold": 180,
                }
            )
        elif alert_type == "heart_rate_low":
            payload.update(
                {
                    "message": "心率过低：38 bpm，持续 20 s",
                    "value": min(38, heart_rate),
                    "threshold": 40,
                }
            )
        else:
            payload.update(
                {
                    "message": "检测到跌倒事件",
                }
            )
        return [
            PublishedMessage(
                topic=_topic(
                    state.profile.identity.gym_id,
                    "wristband",
                    state.profile.identity.device_id,
                    "alert",
                ),
                payload=payload,
            )
        ]
