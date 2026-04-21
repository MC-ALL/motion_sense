from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_event_store, require_admin_user, require_rest_user, user_can_access_scope
from app.models.auth import AuthUser
from app.models.workout import (
    UserWristbandBindingCreateRequest,
    UserWristbandBindingOverviewResponse,
    UserWristbandBindingSummary,
    UserWristbandBindingUnbindRequest,
)
from app.storage.store import Store


router = APIRouter(
    prefix="/api/v1/user-wristband-bindings",
    tags=["user-wristband-bindings"],
    dependencies=[Depends(require_rest_user)],
)


@router.get("", response_model=list[UserWristbandBindingSummary], response_model_exclude_none=True)
async def list_user_wristband_bindings(
    username: str | None = Query(default=None),
    wristband_id: str | None = Query(default=None),
    gym_id: str | None = Query(default=None),
    active_only: bool | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    user: AuthUser = Depends(require_rest_user),
    store: Store = Depends(get_event_store),
) -> list[UserWristbandBindingSummary]:
    items = await store.list_user_wristband_bindings(
        username=username,
        wristband_id=wristband_id,
        gym_id=gym_id,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )
    return [item for item in items if _binding_visible_to_user(user, item)]


@router.get(
    "/overview",
    response_model=UserWristbandBindingOverviewResponse,
    response_model_exclude_none=True,
)
async def get_user_wristband_binding_overview(
    username: str | None = Query(default=None),
    wristband_id: str | None = Query(default=None),
    gym_id: str | None = Query(default=None),
    active_limit: int = Query(default=500, ge=1, le=5000),
    history_limit: int = Query(default=1000, ge=1, le=5000),
    user: AuthUser = Depends(require_rest_user),
    store: Store = Depends(get_event_store),
) -> UserWristbandBindingOverviewResponse:
    active_items = await store.list_user_wristband_bindings(
        username=username,
        wristband_id=wristband_id,
        gym_id=gym_id,
        active_only=True,
        limit=active_limit,
        offset=0,
    )
    history_items = await store.list_user_wristband_bindings(
        username=username,
        wristband_id=wristband_id,
        gym_id=gym_id,
        limit=history_limit,
        offset=0,
    )
    return UserWristbandBindingOverviewResponse(
        active_bindings=[item for item in active_items if _binding_visible_to_user(user, item)],
        binding_history=[item for item in history_items if _binding_visible_to_user(user, item)],
    )


@router.post(
    "",
    response_model=UserWristbandBindingSummary,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_wristband_binding(
    payload: UserWristbandBindingCreateRequest,
    _: object = Depends(require_admin_user),
    store: Store = Depends(get_event_store),
) -> UserWristbandBindingSummary:
    await _require_user_exists(store=store, username=payload.username)
    wristband = await _require_wristband_device(store=store, wristband_id=payload.wristband_id)
    if wristband.gym_id != payload.gym_id:
        raise HTTPException(status_code=409, detail="binding gym_id does not match wristband registration")

    try:
        return await store.create_user_wristband_binding(
            username=payload.username,
            wristband_id=payload.wristband_id,
            gym_id=payload.gym_id,
            bound_at=payload.bound_at,
            source=payload.source,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/{binding_id}/unbind",
    response_model=UserWristbandBindingSummary,
    response_model_exclude_none=True,
)
async def end_user_wristband_binding(
    binding_id: int,
    payload: UserWristbandBindingUnbindRequest,
    _: object = Depends(require_admin_user),
    store: Store = Depends(get_event_store),
) -> UserWristbandBindingSummary:
    binding = await store.end_user_wristband_binding(
        binding_id=binding_id,
        unbound_at=payload.unbound_at,
        note=payload.note,
    )
    if binding is None:
        raise HTTPException(status_code=404, detail="binding not found")
    return binding


async def _require_user_exists(*, store: Store, username: str) -> None:
    if await store.get_user(username=username) is None:
        raise HTTPException(status_code=404, detail="user not found")


async def _require_wristband_device(*, store: Store, wristband_id: str):
    device = await store.get_device(device_id=wristband_id)
    if device is None:
        raise HTTPException(status_code=404, detail="wristband device not found")
    if device.device_type != "wristband":
        raise HTTPException(status_code=409, detail="device is not a wristband")
    return device


def _binding_visible_to_user(user: AuthUser, binding: UserWristbandBindingSummary) -> bool:
    if user.role == "student" and binding.username == user.username:
        return True
    return user_can_access_scope(
        user,
        gym_id=binding.gym_id,
        device_id=binding.wristband_id,
    )
