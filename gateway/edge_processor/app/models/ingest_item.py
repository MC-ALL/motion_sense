from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class IngestItem(BaseModel):
    kind: str
    topic: str
    payload: dict[str, Any]


class IngestBatch(BaseModel):
    gateway_id: str
    sent_at: str
    items: list[IngestItem]
