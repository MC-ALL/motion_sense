from __future__ import annotations

from dataclasses import dataclass
import time

from app.utils.topic_parser import ParsedTopic


@dataclass(slots=True, frozen=True)
class DeviceIdentity:
    gym_id: str
    device_type: str
    device_id: str


@dataclass(slots=True, frozen=True)
class DeviceTransition:
    identity: DeviceIdentity
    observed_at_s: int


@dataclass(slots=True)
class _DevicePresenceState:
    last_seen_s: int
    is_offline: bool


class DevicePresenceTracker:
    def __init__(self) -> None:
        self._states: dict[DeviceIdentity, _DevicePresenceState] = {}

    def mark_seen(
        self,
        parsed_topic: ParsedTopic,
        payload: dict[str, Any],
        now_s: int | None = None,
    ) -> DeviceTransition | None:
        if parsed_topic.device_type == "gateway":
            return None

        identity = DeviceIdentity(
            gym_id=parsed_topic.gym_id,
            device_type=parsed_topic.device_type,
            device_id=parsed_topic.device_id,
        )
        observed_at_s = int(now_s if now_s is not None else time.time())
        state = self._states.get(identity)
        if state is None:
            self._states[identity] = _DevicePresenceState(last_seen_s=observed_at_s, is_offline=False)
            return None

        if observed_at_s > state.last_seen_s:
            state.last_seen_s = observed_at_s

        if not state.is_offline:
            return None

        state.is_offline = False
        return DeviceTransition(identity=identity, observed_at_s=observed_at_s)

    def collect_new_offline(self, timeout_s: int, now_s: int | None = None) -> list[DeviceTransition]:
        if timeout_s <= 0:
            return []

        current = int(now_s if now_s is not None else time.time())
        transitions: list[DeviceTransition] = []

        for identity, state in self._states.items():
            if state.is_offline:
                continue
            if current - state.last_seen_s < timeout_s:
                continue
            state.is_offline = True
            transitions.append(DeviceTransition(identity=identity, observed_at_s=current))

        return transitions
