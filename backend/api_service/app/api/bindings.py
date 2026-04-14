from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_event_store
from app.models.ingest import BindingEventRecord
from app.storage.store import Store


router = APIRouter(prefix="/api/v1/wristband", tags=["bindings"])


@router.get("/{device_id}/bindings", response_model=list[BindingEventRecord])
async def list_wristband_bindings(
    device_id: str,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    store: Store = Depends(get_event_store),
) -> list[BindingEventRecord]:
    return await store.list_binding_events(
        wristband_id=device_id,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )
