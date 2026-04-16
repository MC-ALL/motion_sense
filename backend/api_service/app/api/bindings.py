from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import ensure_known_device_scope, get_event_store, require_rest_user
from app.models.auth import AuthUser
from app.models.ingest import BindingEventRecord
from app.storage.store import Store


router = APIRouter(
    prefix="/api/v1/wristband",
    tags=["bindings"],
    dependencies=[Depends(require_rest_user)],
)


@router.get("/{device_id}/bindings", response_model=list[BindingEventRecord])
async def list_wristband_bindings(
    device_id: str,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    user: AuthUser = Depends(require_rest_user),
    store: Store = Depends(get_event_store),
) -> list[BindingEventRecord]:
    await ensure_known_device_scope(device_id=device_id, user=user, store=store)
    return await store.list_binding_events(
        wristband_id=device_id,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )
