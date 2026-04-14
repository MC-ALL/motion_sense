from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ParsedTopic:
    gym_id: str
    device_type: str
    device_id: str
    action: str


def parse_topic(topic: str) -> ParsedTopic:
    parts = topic.split("/")
    if len(parts) != 5 or parts[0] != "gym":
        raise ValueError(f"invalid topic: {topic}")

    return ParsedTopic(
        gym_id=parts[1],
        device_type=parts[2],
        device_id=parts[3],
        action=parts[4],
    )
