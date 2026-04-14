from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_event_store
from app.models.ingest import DeviceSummary
from app.services.event_store import EventStore


router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


@router.get("", response_model=list[DeviceSummary])
async def list_devices(
    type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    store: EventStore = Depends(get_event_store),
) -> list[DeviceSummary]:
    return await store.list_devices(device_type=type, status=status)
