from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.models.auth import AuthUser
from app.models.ingest import AlertRecord, DeviceSummary
from app.services.auth_service import AuthError, AuthService
from app.services.device_config_service import DeviceConfigService
from app.services.ingest_service import IngestService
from app.services.realtime_service import RealtimeService
from app.services.workout_aggregation_service import WorkoutAggregationService
from app.services.websocket_manager import WebSocketManager
from app.storage.store import Store


bearer_scheme = HTTPBearer(auto_error=False)


def get_event_store(request: Request) -> Store:
    return request.app.state.event_store


def get_ingest_service(request: Request) -> IngestService:
    return request.app.state.ingest_service


def get_device_config_service(request: Request) -> DeviceConfigService:
    return request.app.state.device_config_service

def get_workout_aggregation_service(request: Request) -> WorkoutAggregationService:
    return request.app.state.workout_aggregation_service


def get_websocket_manager(request: Request) -> WebSocketManager:
    return request.app.state.websocket_manager


def get_realtime_service(request: Request) -> RealtimeService:
    return request.app.state.realtime_service


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


def require_rest_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthUser:
    if credentials is None:
        if auth_service.rest_auth_required:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return auth_service.anonymous_user()

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unsupported authorization scheme",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return auth_service.verify_access_token(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_roles(*allowed_roles: str):
    def dependency(user: AuthUser = Depends(require_rest_user)) -> AuthUser:
        if user.role == "anonymous":
            return user
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"required roles: {', '.join(allowed_roles)}",
            )
        return user

    return dependency


require_admin_user = require_roles("admin")
require_admin_or_teacher_user = require_roles("admin", "teacher")


def is_unrestricted_user(user: AuthUser) -> bool:
    return user.role in {"admin", "anonymous"}


def user_can_access_scope(
    user: AuthUser,
    *,
    gym_id: str | None = None,
    device_id: str | None = None,
) -> bool:
    if is_unrestricted_user(user):
        return True

    gym_ids = set(user.gym_ids)
    device_ids = set(user.device_ids)

    if user.role == "teacher":
        return (device_id is not None and device_id in device_ids) or (gym_id is not None and gym_id in gym_ids)

    if user.role == "student":
        return device_id is not None and device_id in device_ids

    return False


def filter_devices_for_user(user: AuthUser, devices: list[DeviceSummary]) -> list[DeviceSummary]:
    if is_unrestricted_user(user):
        return devices
    return [
        item
        for item in devices
        if user_can_access_scope(user, gym_id=item.gym_id, device_id=item.device_id)
    ]


def filter_alerts_for_user(user: AuthUser, alerts: list[AlertRecord]) -> list[AlertRecord]:
    if is_unrestricted_user(user):
        return alerts
    return [
        item
        for item in alerts
        if user_can_access_scope(user, gym_id=item.gym_id, device_id=item.device_id)
    ]


def ensure_device_scope(user: AuthUser, device: DeviceSummary) -> None:
    if user_can_access_scope(user, gym_id=device.gym_id, device_id=device.device_id):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="device access forbidden")


def ensure_alert_scope(user: AuthUser, alert: AlertRecord) -> None:
    if user_can_access_scope(user, gym_id=alert.gym_id, device_id=alert.device_id):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="alert access forbidden")


async def ensure_known_device_scope(
    *,
    device_id: str,
    user: AuthUser,
    store: Store,
    not_found_detail: str = "device not found",
) -> DeviceSummary | None:
    device = await store.get_device(device_id=device_id)
    if device is not None:
        ensure_device_scope(user, device)
        return device

    if is_unrestricted_user(user) or device_id in set(user.device_ids):
        return None

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_detail)
