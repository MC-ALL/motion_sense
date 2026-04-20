from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_event_store, is_unrestricted_user, require_rest_user
from app.models.auth import AuthUser
from app.models.workout import (
    UserTrainingProfileResponse,
    UserTrainingProfileSummary,
    UserWristbandBindingSummary,
    WorkoutSessionSummary,
)
from app.storage.store import Store


router = APIRouter(
    prefix="/api/v1/users",
    tags=["user-training-profiles"],
    dependencies=[Depends(require_rest_user)],
)


@router.get("/{username}/training-profile", response_model=UserTrainingProfileResponse)
async def get_user_training_profile(
    username: str,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    binding_limit: int = Query(default=10, ge=1, le=100),
    session_limit: int = Query(default=20, ge=1, le=200),
    user: AuthUser = Depends(require_rest_user),
    store: Store = Depends(get_event_store),
) -> UserTrainingProfileResponse:
    target_user = await store.get_user(username=username)
    if target_user is None:
        raise HTTPException(status_code=404, detail="user not found")
    _ensure_training_profile_scope(current_user=user, target_user=target_user)

    recent_bindings = await store.list_user_wristband_bindings(
        username=username,
        limit=binding_limit,
        offset=0,
    )
    active_binding = next((item for item in recent_bindings if item.is_active), None)
    recent_sessions = await store.list_workout_sessions(
        username=username,
        start=start,
        end=end,
        limit=session_limit,
        offset=0,
    )
    summary_sessions = await store.list_workout_sessions(
        username=username,
        start=start,
        end=end,
        limit=5000,
        offset=0,
    )

    return UserTrainingProfileResponse(
        user=target_user,
        query_start=start,
        query_end=end,
        active_binding=active_binding,
        recent_bindings=recent_bindings,
        recent_sessions=recent_sessions,
        summary=_build_training_profile_summary(summary_sessions),
    )


def _ensure_training_profile_scope(*, current_user: AuthUser, target_user) -> None:
    if is_unrestricted_user(current_user):
        return
    if current_user.username == target_user.username:
        return
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="training profile access forbidden")

    teacher_gym_ids = set(current_user.gym_ids)
    teacher_device_ids = set(current_user.device_ids)
    target_gym_ids = set(target_user.gym_ids)
    target_device_ids = set(target_user.device_ids)
    if teacher_gym_ids.intersection(target_gym_ids):
        return
    if teacher_device_ids.intersection(target_device_ids):
        return
    raise HTTPException(status_code=403, detail="training profile access forbidden")


def _build_training_profile_summary(sessions: list[WorkoutSessionSummary]) -> UserTrainingProfileSummary:
    equipment_ids: list[str] = []
    seen_equipment_ids: set[str] = set()
    total_duration_s = 0
    total_rep_count = 0
    total_energy_wh = 0.0
    max_heart_rate: int | None = None
    weighted_heart_rate_sum = 0.0
    weighted_heart_rate_duration = 0
    average_heart_rate_values: list[float] = []
    last_session_at: str | None = None

    for session in sessions:
        if last_session_at is None and session.ended_at is not None:
            last_session_at = session.ended_at
        elif last_session_at is None:
            last_session_at = session.started_at

        for equipment_id in session.equipment_ids:
            if equipment_id in seen_equipment_ids:
                continue
            seen_equipment_ids.add(equipment_id)
            equipment_ids.append(equipment_id)

        duration_s = session.duration_s or 0
        total_duration_s += duration_s
        total_rep_count += session.metrics.total_rep_count or 0
        total_energy_wh += session.metrics.total_energy_wh or 0

        if session.metrics.max_heart_rate is not None:
            max_heart_rate = (
                session.metrics.max_heart_rate
                if max_heart_rate is None
                else max(max_heart_rate, session.metrics.max_heart_rate)
            )

        if session.metrics.avg_heart_rate is not None:
            if duration_s > 0:
                weighted_heart_rate_sum += session.metrics.avg_heart_rate * duration_s
                weighted_heart_rate_duration += duration_s
            else:
                average_heart_rate_values.append(session.metrics.avg_heart_rate)

    if weighted_heart_rate_duration > 0:
        avg_heart_rate = weighted_heart_rate_sum / weighted_heart_rate_duration
    elif average_heart_rate_values:
        avg_heart_rate = sum(average_heart_rate_values) / len(average_heart_rate_values)
    else:
        avg_heart_rate = None

    return UserTrainingProfileSummary(
        total_sessions=len(sessions),
        completed_sessions=sum(1 for item in sessions if item.status == "completed"),
        open_sessions=sum(1 for item in sessions if item.status == "open"),
        cancelled_sessions=sum(1 for item in sessions if item.status == "cancelled"),
        total_duration_s=total_duration_s,
        total_rep_count=total_rep_count,
        total_energy_wh=round(total_energy_wh, 2),
        avg_heart_rate=round(avg_heart_rate, 1) if avg_heart_rate is not None else None,
        max_heart_rate=max_heart_rate,
        equipment_ids=equipment_ids,
        last_session_at=last_session_at,
    )
