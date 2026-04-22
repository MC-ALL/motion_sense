from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import (
    ensure_device_scope,
    filter_devices_for_user,
    get_device_config_service,
    get_event_store,
    get_realtime_service,
    require_admin_user,
    require_rest_user,
)
from app.models.auth import AuthUser
from app.models.device_config import DeviceConfigPublishRequest, DeviceConfigPublishResult
from app.models.device_registry import (
    DeviceDeleteResponse,
    DeviceRegistrationRequest,
    DeviceRegistrationUpdateRequest,
)
from app.models.ingest import DeviceSummary
from app.services.device_config_service import (
    DeviceConfigConflictError,
    DeviceConfigService,
    DeviceConfigTargetNotFoundError,
)
from app.services.realtime_service import RealtimeService
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
    user: AuthUser = Depends(require_rest_user),
    store: Store = Depends(get_event_store),
) -> list[DeviceSummary]:
    devices = await store.list_devices(device_type=type, status=status)
    return filter_devices_for_user(user, devices)


@router.post("", response_model=DeviceSummary, response_model_exclude_none=True)
async def register_device(
    payload: DeviceRegistrationRequest,
    _: object = Depends(require_admin_user),
    store: Store = Depends(get_event_store),
    realtime_service: RealtimeService = Depends(get_realtime_service),
) -> DeviceSummary:
    gateway_id = _normalize_gateway_id(
        device_type=payload.device_type,
        device_id=payload.device_id,
        gateway_id=payload.gateway_id,
    )
    try:
        device = await store.register_device(
            gym_id=payload.gym_id,
            device_type=payload.device_type,
            device_id=payload.device_id,
            gateway_id=gateway_id,
            display_name=payload.display_name,
            location=payload.location,
            metadata=payload.metadata,
        )
        await realtime_service.publish({"type": "device_upsert", "data": device.model_dump()})
        return device
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{device_id}", response_model=DeviceSummary, response_model_exclude_none=True)
async def get_device(
    device_id: str,
    user: AuthUser = Depends(require_rest_user),
    store: Store = Depends(get_event_store),
) -> DeviceSummary:
    device = await store.get_device(device_id=device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="device not found")
    ensure_device_scope(user, device)
    return device


@router.patch("/{device_id}", response_model=DeviceSummary, response_model_exclude_none=True)
async def update_device(
    device_id: str,
    payload: DeviceRegistrationUpdateRequest,
    _: object = Depends(require_admin_user),
    store: Store = Depends(get_event_store),
    realtime_service: RealtimeService = Depends(get_realtime_service),
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
    await realtime_service.publish({"type": "device_upsert", "data": updated.model_dump()})
    return updated


@router.delete("/{device_id}", response_model=DeviceDeleteResponse)
async def delete_device(
    device_id: str,
    _: object = Depends(require_admin_user),
    store: Store = Depends(get_event_store),
    realtime_service: RealtimeService = Depends(get_realtime_service),
) -> DeviceDeleteResponse:
    existing = await store.get_device(device_id=device_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="device not found")
    deleted = await store.delete_device(device_id=device_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="device not found")
    await realtime_service.publish(
        {
            "type": "device_delete",
            "data": {
                "device_id": existing.device_id,
                "device_type": existing.device_type,
                "gym_id": existing.gym_id,
            },
        }
    )
    return DeviceDeleteResponse()


@router.post("/{device_id}/config", response_model=DeviceConfigPublishResult)
async def publish_device_config(
    device_id: str,
    payload: DeviceConfigPublishRequest,
    _: object = Depends(require_admin_user),
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
