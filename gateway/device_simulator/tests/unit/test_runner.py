from app.runner import _publish_group_for_topic


def test_publish_group_for_topic_routes_by_device_type() -> None:
    assert _publish_group_for_topic("gym/gym-gz-01/equipment/eq-001/telemetry") == "equipment"
    assert _publish_group_for_topic("gym/gym-gz-01/wristband/wb-001/status") == "wristband"
    assert _publish_group_for_topic("gym/gym-gz-01/env/env-001/telemetry") == "env"
