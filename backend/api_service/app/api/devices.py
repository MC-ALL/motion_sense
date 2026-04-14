from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_device_config_service, get_event_store
from app.models.device_config import DeviceConfigPublishRequest, DeviceConfigPublishResult
from app.models.ingest import DeviceSummary
from app.services.device_config_service import (
    DeviceConfigConflictError,
    DeviceConfigService,
    DeviceConfigTargetNotFoundError,
)
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


@router.post("/{device_id}/config", response_model=DeviceConfigPublishResult)
async def publish_device_config(
    device_id: str,
    payload: DeviceConfigPublishRequest,
    service: DeviceConfigService = Depends(get_device_config_service),
) -> DeviceConfigPublishResult:
    try:
        return await service.publish_config(device_id=device_id, request=payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DeviceConfigTargetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeviceConfigConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
