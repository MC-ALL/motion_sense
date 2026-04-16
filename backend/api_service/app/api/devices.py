from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_device_config_service, get_event_store, require_rest_user
from app.models.device_registry import (
    DeviceDeleteResponse,
    DeviceRegistrationRequest,
    DeviceRegistrationUpdateRequest,
)
from app.models.device_config import DeviceConfigPublishRequest, DeviceConfigPublishResult
from app.models.ingest import DeviceSummary
from app.services.device_config_service import (
    DeviceConfigConflictError,
    DeviceConfigService,
    DeviceConfigTargetNotFoundError,
)
from app.storage.store import Store


router = APIRouter(
    prefix="/api/v1/devices",
    tags=["devices"],
    dependencies=[Depends(require_rest_user)],
)


@router.get("", response_model=list[DeviceSummary], response_model_exclude_none=True)
async def list_devices(
    type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    store: Store = Depends(get_event_store),
) -> list[DeviceSummary]:
    return await store.list_devices(device_type=type, status=status)


@router.post("", response_model=DeviceSummary, response_model_exclude_none=True)
async def register_device(
    payload: DeviceRegistrationRequest,
    store: Store = Depends(get_event_store),
) -> DeviceSummary:
    gateway_id = _normalize_gateway_id(
        device_type=payload.device_type,
        device_id=payload.device_id,
        gateway_id=payload.gateway_id,
    )
    try:
        return await store.register_device(
            gym_id=payload.gym_id,
            device_type=payload.device_type,
            device_id=payload.device_id,
            gateway_id=gateway_id,
            display_name=payload.display_name,
            location=payload.location,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{device_id}", response_model=DeviceSummary, response_model_exclude_none=True)
async def get_device(
    device_id: str,
    store: Store = Depends(get_event_store),
) -> DeviceSummary:
    device = await store.get_device(device_id=device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="device not found")
    return device


@router.patch("/{device_id}", response_model=DeviceSummary, response_model_exclude_none=True)
async def update_device(
    device_id: str,
    payload: DeviceRegistrationUpdateRequest,
    store: Store = Depends(get_event_store),
) -> DeviceSummary:
    existing = await store.get_device(device_id=device_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="device not found")

    updates = payload.model_dump(exclude_unset=True)
    if "metadata" in updates and updates["metadata"] is None:
        updates["metadata"] = {}
    if "gateway_id" in updates:
        updates["gateway_id"] = _normalize_gateway_id(
            device_type=existing.device_type,
            device_id=existing.device_id,
            gateway_id=updates.get("gateway_id"),
        )

    updated = await store.update_device_registration(device_id=device_id, updates=updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="device not found")
    return updated


@router.delete("/{device_id}", response_model=DeviceDeleteResponse)
async def delete_device(
    device_id: str,
    store: Store = Depends(get_event_store),
) -> DeviceDeleteResponse:
    deleted = await store.delete_device(device_id=device_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="device not found")
    return DeviceDeleteResponse()


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


def _normalize_gateway_id(
    *,
    device_type: str,
    device_id: str,
    gateway_id: str | None,
) -> str | None:
    if device_type == "gateway":
        return gateway_id or device_id
    if gateway_id is None:
        raise HTTPException(status_code=422, detail="gateway_id is required for non-gateway devices")
    return gateway_id
