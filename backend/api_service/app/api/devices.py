from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_event_store
from app.models.ingest import DeviceSummary
from app.storage.store import Store


router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


@router.get("", response_model=list[DeviceSummary])
async def list_devices(
    type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    store: Store = Depends(get_event_store),
) -> list[DeviceSummary]:
    return await store.list_devices(device_type=type, status=status)


@router.get("/{device_id}", response_model=DeviceSummary)
async def get_device(
    device_id: str,
    store: Store = Depends(get_event_store),
) -> DeviceSummary:
    device = await store.get_device(device_id=device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="device not found")
    return device
