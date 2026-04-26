from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from app.utils.topic_parser import ParsedTopic


@dataclass(slots=True, frozen=True)
class DeviceIdentity:
    """Stable identity for a non-gateway device observed by this edge processor."""

    gym_id: str
    device_type: str
    device_id: str


@dataclass(slots=True, frozen=True)
class DeviceTransition:
    """Online/offline transition timestamp for a tracked device."""

    identity: DeviceIdentity
    observed_at_s: int


@dataclass(slots=True)
class _DevicePresenceState:
    """Mutable liveness state kept for one device identity."""

    last_seen_s: int
    is_offline: bool


class DevicePresenceTracker:
    """Track device liveness from inbound MQTT messages.

    The tracker only emits transitions. A device that keeps reporting normally
    stays quiet; callers receive an event only when it first times out, or when
    a previously-offline device reports again.
    """

    def __init__(self) -> None:
        """Create an empty presence tracker."""
        self._states: dict[DeviceIdentity, _DevicePresenceState] = {}

    def mark_seen(
        self,
        parsed_topic: ParsedTopic,
        payload: dict[str, Any],
        now_s: int | None = None,
    ) -> DeviceTransition | None:
        """Record a fresh device message.

        :param parsed_topic: Parsed MQTT topic that identifies the reporting device.
        :param payload: Original MQTT payload for the message. The current tracker
            keeps this argument for call-site symmetry and future status rules, but
            only the topic identity is used today.
        :param now_s: Optional Unix timestamp in seconds. Tests pass this value to
            avoid depending on wall-clock time.
        :return: A ``DeviceTransition`` when a previously-offline device reports
            again; otherwise ``None``.
        """
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

        # The first message after an offline timeout is the recovery edge.
        state.is_offline = False
        return DeviceTransition(identity=identity, observed_at_s=observed_at_s)

    def collect_new_offline(self, timeout_s: int, now_s: int | None = None) -> list[DeviceTransition]:
        """Collect devices that newly crossed the offline threshold.

        :param timeout_s: Maximum silence window in seconds before a device is
            considered offline. Non-positive values disable offline checks.
        :param now_s: Optional Unix timestamp in seconds. Tests pass this value to
            make timeout behavior deterministic.
        :return: Devices that became offline during this scan. Devices already
            marked offline are not returned again until they recover and time out
            once more.
        """
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
