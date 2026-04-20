from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_event_store, require_admin_user, require_rest_user, user_can_access_scope
from app.models.auth import AuthUser
from app.models.workout import (
    WorkoutSessionCreateRequest,
    WorkoutSessionStatus,
    WorkoutSessionSummary,
    WorkoutSessionUpdateRequest,
)
from app.storage.store import Store


router = APIRouter(
    prefix="/api/v1/workout-sessions",
    tags=["workout-sessions"],
    dependencies=[Depends(require_rest_user)],
)


@router.get("", response_model=list[WorkoutSessionSummary], response_model_exclude_none=True)
async def list_workout_sessions(
    username: str | None = Query(default=None),
    wristband_id: str | None = Query(default=None),
    gym_id: str | None = Query(default=None),
    status: WorkoutSessionStatus | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    user: AuthUser = Depends(require_rest_user),
    store: Store = Depends(get_event_store),
) -> list[WorkoutSessionSummary]:
    items = await store.list_workout_sessions(
        username=username,
        wristband_id=wristband_id,
        gym_id=gym_id,
        status=status,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )
    return [item for item in items if _workout_session_visible_to_user(user, item)]


@router.get("/{session_id}", response_model=WorkoutSessionSummary, response_model_exclude_none=True)
async def get_workout_session(
    session_id: str,
    user: AuthUser = Depends(require_rest_user),
    store: Store = Depends(get_event_store),
) -> WorkoutSessionSummary:
    session = await store.get_workout_session(session_id=session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="workout session not found")
    if not _workout_session_visible_to_user(user, session):
        raise HTTPException(status_code=403, detail="workout session access forbidden")
    return session


@router.post(
    "",
    response_model=WorkoutSessionSummary,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_workout_session(
    payload: WorkoutSessionCreateRequest,
    _: object = Depends(require_admin_user),
    store: Store = Depends(get_event_store),
) -> WorkoutSessionSummary:
    await _require_user_exists(store=store, username=payload.username)
    wristband = await _require_device_type(
        store=store,
        device_id=payload.wristband_id,
        device_type="wristband",
        not_found_detail="wristband device not found",
    )
    if wristband.gym_id != payload.gym_id:
        raise HTTPException(status_code=409, detail="session gym_id does not match wristband registration")

    await _require_equipment_devices(
        store=store,
        gym_id=payload.gym_id,
        equipment_ids=_collect_equipment_ids(payload.equipment_ids, payload.segments),
    )

    return await store.create_workout_session(
        username=payload.username,
        wristband_id=payload.wristband_id,
        gym_id=payload.gym_id,
        status=payload.status,
        source=payload.source,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        equipment_ids=payload.equipment_ids,
        segments=payload.segments,
        metrics=payload.metrics,
        notes=payload.notes,
    )


@router.patch("/{session_id}", response_model=WorkoutSessionSummary, response_model_exclude_none=True)
async def update_workout_session(
    session_id: str,
    payload: WorkoutSessionUpdateRequest,
    _: object = Depends(require_admin_user),
    store: Store = Depends(get_event_store),
) -> WorkoutSessionSummary:
    existing = await store.get_workout_session(session_id=session_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="workout session not found")

    await _require_equipment_devices(
        store=store,
        gym_id=existing.gym_id,
        equipment_ids=_collect_equipment_ids(payload.equipment_ids, payload.segments),
    )

    updated = await store.update_workout_session(
        session_id=session_id,
        status=payload.status,
        ended_at=payload.ended_at,
        equipment_ids=payload.equipment_ids,
        segments=payload.segments,
        metrics=payload.metrics,
        notes=payload.notes,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="workout session not found")
    return updated


async def _require_user_exists(*, store: Store, username: str) -> None:
    if await store.get_user(username=username) is None:
        raise HTTPException(status_code=404, detail="user not found")


async def _require_device_type(
    *,
    store: Store,
    device_id: str,
    device_type: str,
    not_found_detail: str,
):
    device = await store.get_device(device_id=device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=not_found_detail)
    if device.device_type != device_type:
        raise HTTPException(status_code=409, detail=f"device is not a {device_type}")
    return device


async def _require_equipment_devices(
    *,
    store: Store,
    gym_id: str,
    equipment_ids: list[str],
) -> None:
    for equipment_id in equipment_ids:
        equipment = await _require_device_type(
            store=store,
            device_id=equipment_id,
            device_type="equipment",
            not_found_detail="equipment device not found",
        )
        if equipment.gym_id != gym_id:
            raise HTTPException(status_code=409, detail="equipment gym_id does not match workout session")


def _collect_equipment_ids(equipment_ids, segments) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for item in equipment_ids or []:
        if item in seen:
            continue
        seen.add(item)
        values.append(item)
    for segment in segments or []:
        if segment.equipment_id in seen:
            continue
        seen.add(segment.equipment_id)
        values.append(segment.equipment_id)
    return values


def _workout_session_visible_to_user(user: AuthUser, session: WorkoutSessionSummary) -> bool:
    if user.role == "student" and session.username == user.username:
        return True
    if user_can_access_scope(user, gym_id=session.gym_id, device_id=session.wristband_id):
        return True
    return any(user_can_access_scope(user, gym_id=session.gym_id, device_id=item) for item in session.equipment_ids)
