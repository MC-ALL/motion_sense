from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_event_store
from app.models.ingest import AlertRecord
from app.services.event_store import EventStore


router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertRecord])
async def list_alerts(
    level: str | None = Query(default=None),
    is_ack: bool | None = Query(default=None),
    store: EventStore = Depends(get_event_store),
) -> list[AlertRecord]:
    return await store.list_alerts(level=level, is_ack=is_ack)
