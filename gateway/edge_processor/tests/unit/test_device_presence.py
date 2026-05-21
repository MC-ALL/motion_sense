from app.services.device_presence import DevicePresenceTracker
from app.utils.topic_parser import parse_topic


def test_device_presence_marks_offline_and_recovers() -> None:
    """Verify offline transition emits once and resets after recovery.

    :return: None. Assertions cover first timeout, duplicate suppression,
        recovery, and a second offline transition.
    """
    tracker = DevicePresenceTracker()
    topic = parse_topic("gym/gym-gz-01/equipment/eq-001/telemetry")

    assert tracker.mark_seen(topic, {"ts": 100, "power_w": 120.0}, now_s=100) is None
    assert tracker.collect_new_offline(timeout_s=30, now_s=120) == []

    offline = tracker.collect_new_offline(timeout_s=30, now_s=131)
    assert len(offline) == 1
    assert offline[0].identity.device_id == "eq-001"

    assert tracker.collect_new_offline(timeout_s=30, now_s=150) == []

    recovered = tracker.mark_seen(topic, {"ts": 151, "power_w": 90.0}, now_s=151)
    assert recovered is not None
    assert recovered.identity.device_id == "eq-001"

    offline_again = tracker.collect_new_offline(timeout_s=30, now_s=190)
    assert len(offline_again) == 1
    assert offline_again[0].identity.device_id == "eq-001"


def test_device_presence_uses_gateway_receive_time_instead_of_device_ts() -> None:
    """Verify offline checks use gateway receive time, not payload timestamp.

    :return: None. Assertions confirm a stale device timestamp does not force
        an offline transition while the gateway receive time is still fresh.
    """
    tracker = DevicePresenceTracker()
    topic = parse_topic("gym/gym-gz-01/equipment/eq-001/telemetry")

    assert tracker.mark_seen(topic, {"ts": 1712640000, "power_w": 120.0}, now_s=200) is None
    assert tracker.collect_new_offline(timeout_s=30, now_s=220) == []


def test_device_presence_ignores_binding_events() -> None:
    """Verify binding events do not imply wristband connectivity.

    :return: None. Assertions confirm binding messages alone never create a
        tracked device that can later time out.
    """
    tracker = DevicePresenceTracker()
    topic = parse_topic("gym/gym-gz-01/wristband/wb-001/binding")

    assert tracker.mark_seen(topic, {"ts": 100, "equipment_id": "eq-001", "bound": True}, now_s=100) is None
    assert tracker.collect_new_offline(timeout_s=30, now_s=131) == []
