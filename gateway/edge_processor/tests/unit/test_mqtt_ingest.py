from app.services.mqtt_ingest import _is_internal_edge_event
from app.utils.topic_parser import parse_topic


def test_internal_edge_alert_or_status_is_ignored() -> None:
    alert_topic = parse_topic("gym/gym-gz-01/equipment/eq-001/alert")
    status_topic = parse_topic("gym/gym-gz-01/equipment/eq-001/status")
    telemetry_topic = parse_topic("gym/gym-gz-01/equipment/eq-001/telemetry")

    assert _is_internal_edge_event(alert_topic, {"source": "edge_processor"}) is True
    assert _is_internal_edge_event(status_topic, {"source": "edge_processor"}) is True
    assert _is_internal_edge_event(telemetry_topic, {"source": "edge_processor"}) is False
    assert _is_internal_edge_event(alert_topic, {"source": "device"}) is False
