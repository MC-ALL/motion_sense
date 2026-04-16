from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.models.auth import AuthUser
from app.services.auth_service import AuthError, AuthService
from app.services.device_config_service import DeviceConfigService
from app.services.ingest_service import IngestService
from app.services.websocket_manager import WebSocketManager
from app.storage.store import Store


bearer_scheme = HTTPBearer(auto_error=False)


def get_event_store(request: Request) -> Store:
    return request.app.state.event_store


def get_ingest_service(request: Request) -> IngestService:
    return request.app.state.ingest_service


def get_device_config_service(request: Request) -> DeviceConfigService:
    return request.app.state.device_config_service


def get_websocket_manager(request: Request) -> WebSocketManager:
    return request.app.state.websocket_manager


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


def require_admin_user(user: AuthUser = Depends(require_rest_user)) -> AuthUser:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin role required",
        )
    return user
