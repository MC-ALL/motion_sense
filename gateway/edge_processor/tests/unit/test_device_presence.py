from app.services.device_presence import DevicePresenceTracker
from app.utils.topic_parser import parse_topic


def test_device_presence_marks_offline_and_recovers() -> None:
    tracker = DevicePresenceTracker()
    topic = parse_topic("gym/gym-gz-01/equipment/eq-001/telemetry")

    assert tracker.mark_seen(topic, {"ts": 100, "power_w": 120.0}) is None
    assert tracker.collect_new_offline(timeout_s=30, now_s=120) == []

    offline = tracker.collect_new_offline(timeout_s=30, now_s=131)
    assert len(offline) == 1
    assert offline[0].identity.device_id == "eq-001"

    assert tracker.collect_new_offline(timeout_s=30, now_s=150) == []

    recovered = tracker.mark_seen(topic, {"ts": 151, "power_w": 90.0})
    assert recovered is not None
    assert recovered.identity.device_id == "eq-001"

    offline_again = tracker.collect_new_offline(timeout_s=30, now_s=190)
    assert len(offline_again) == 1
    assert offline_again[0].identity.device_id == "eq-001"
