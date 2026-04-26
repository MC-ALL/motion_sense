import pytest

from app.utils.topic_parser import parse_topic


def test_parse_topic_supports_gateway_action() -> None:
    """Verify gateway config topics are parsed into structured fields.

    :return: None. Assertions validate gym ID, gateway identity, and action.
    """
    parsed = parse_topic("gym/gym-gz-01/gateway/gw-001/config")

    assert parsed.gym_id == "gym-gz-01"
    assert parsed.device_type == "gateway"
    assert parsed.device_id == "gw-001"
    assert parsed.action == "config"


def test_parse_topic_rejects_invalid_topics() -> None:
    """Verify malformed MQTT topics are rejected.

    :return: None. Assertion expects ``ValueError`` for invalid topic shape.
    """
    with pytest.raises(ValueError):
        parse_topic("bad/topic")
