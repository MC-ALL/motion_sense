from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_auth_service
from app.models.auth import (
    AuthLoginRequest,
    AuthLogoutRequest,
    AuthLogoutResponse,
    AuthRefreshRequest,
    AuthTokenPair,
)
from app.services.auth_service import AuthError, AuthService


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=AuthTokenPair)
async def login(
    payload: AuthLoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthTokenPair:
    try:
        return await auth_service.login(username=payload.username, password=payload.password)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


@router.post("/refresh", response_model=AuthTokenPair)
async def refresh_token(
    payload: AuthRefreshRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthTokenPair:
    try:
        return await auth_service.refresh(payload.refresh_token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


@router.post("/logout", response_model=AuthLogoutResponse)
async def logout(
    payload: AuthLogoutRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthLogoutResponse:
    try:
        auth_service.logout(payload.refresh_token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    return AuthLogoutResponse(ok=True)
