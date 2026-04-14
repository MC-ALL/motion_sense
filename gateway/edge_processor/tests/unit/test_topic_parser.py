import pytest

from app.utils.topic_parser import parse_topic


def test_parse_topic_supports_gateway_action() -> None:
    parsed = parse_topic("gym/gym-gz-01/gateway/gw-001/config")

    assert parsed.gym_id == "gym-gz-01"
    assert parsed.device_type == "gateway"
    assert parsed.device_id == "gw-001"
    assert parsed.action == "config"


def test_parse_topic_rejects_invalid_topics() -> None:
    with pytest.raises(ValueError):
        parse_topic("bad/topic")
