from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class IngestItem(BaseModel):
    """Single MQTT event normalized for backend ingestion."""

    kind: str
    topic: str
    payload: dict[str, Any]


class IngestBatch(BaseModel):
    """Batch envelope sent from the edge processor to the backend."""

    gateway_id: str
    sent_at: str
    items: list[IngestItem]
