from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_event_store
from app.models.ingest import TelemetryRecord
from app.storage.store import Store


router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])


@router.get("/wristband/{device_id}", response_model=list[TelemetryRecord])
async def list_wristband_telemetry(
    device_id: str,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    store: Store = Depends(get_event_store),
) -> list[TelemetryRecord]:
    return await store.list_telemetry(
        device_type="wristband",
        device_id=device_id,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )


@router.get("/equipment/{device_id}", response_model=list[TelemetryRecord])
async def list_equipment_telemetry(
    device_id: str,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    store: Store = Depends(get_event_store),
) -> list[TelemetryRecord]:
    return await store.list_telemetry(
        device_type="equipment",
        device_id=device_id,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )


@router.get("/env/{device_id}", response_model=list[TelemetryRecord])
async def list_env_telemetry(
    device_id: str,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    store: Store = Depends(get_event_store),
) -> list[TelemetryRecord]:
    return await store.list_telemetry(
        device_type="env",
        device_id=device_id,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )
