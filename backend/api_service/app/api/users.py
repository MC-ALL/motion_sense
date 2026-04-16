from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_auth_service, get_event_store, require_admin_user, require_rest_user
from app.models.auth import AuthUser
from app.models.user import UserCreateRequest, UserDeleteResponse, UserSummary, UserUpdateRequest
from app.services.auth_service import AuthService, generate_password_hash
from app.storage.store import Store


router = APIRouter(
    prefix="/api/v1/users",
    tags=["users"],
    dependencies=[Depends(require_admin_user)],
)


@router.get("", response_model=list[UserSummary])
async def list_users(
    store: Store = Depends(get_event_store),
) -> list[UserSummary]:
    return await store.list_users()


@router.post("", response_model=UserSummary, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateRequest,
    store: Store = Depends(get_event_store),
) -> UserSummary:
    try:
        return await store.create_user(
            username=payload.username,
            password_hash=generate_password_hash(payload.password),
            role=payload.role,
            gym_ids=_normalize_scope_items(payload.gym_ids),
            device_ids=_normalize_scope_items(payload.device_ids),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch("/{username}", response_model=UserSummary)
async def update_user(
    username: str,
    payload: UserUpdateRequest,
    store: Store = Depends(get_event_store),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserSummary:
    existing = await store.get_user(username=username)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    if username == auth_service.bootstrap_admin_username:
        if payload.password is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="bootstrap admin password is deployment-managed",
            )
        if payload.role is not None and payload.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="bootstrap admin role cannot be changed",
            )

    password_hash = generate_password_hash(payload.password) if payload.password is not None else None
    updated = await store.update_user(
        username=username,
        password_hash=password_hash,
        role=payload.role,
        gym_ids=(
            _normalize_scope_items(payload.gym_ids)
            if payload.gym_ids is not None
            else None
        ),
        device_ids=(
            _normalize_scope_items(payload.device_ids)
            if payload.device_ids is not None
            else None
        ),
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return updated


@router.delete("/{username}", response_model=UserDeleteResponse)
async def delete_user(
    username: str,
    current_user: AuthUser = Depends(require_rest_user),
    store: Store = Depends(get_event_store),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserDeleteResponse:
    if username == auth_service.bootstrap_admin_username:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="bootstrap admin cannot be deleted",
        )
    if username == current_user.username:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="current user cannot delete itself",
        )
    deleted = await store.delete_user(username=username)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return UserDeleteResponse()


def _normalize_scope_items(items: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized
