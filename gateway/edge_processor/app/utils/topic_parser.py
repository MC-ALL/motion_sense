from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ParsedTopic:
    """Structured form of the gateway MQTT topic contract."""

    gym_id: str
    device_type: str
    device_id: str
    action: str


def parse_topic(topic: str) -> ParsedTopic:
    """Parse a device MQTT topic.

    :param topic: MQTT topic in ``gym/{gym_id}/{device_type}/{device_id}/{action}``
        format.
    :return: Parsed topic fields used by ingestion, rules, and buffering.
    :raises ValueError: If the topic does not match the expected five-part shape.
    """
    parts = topic.split("/")
    if len(parts) != 5 or parts[0] != "gym":
        raise ValueError(f"invalid topic: {topic}")

    return ParsedTopic(
        gym_id=parts[1],
        device_type=parts[2],
        device_id=parts[3],
        action=parts[4],
    )
