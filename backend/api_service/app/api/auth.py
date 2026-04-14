from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.ai import ReservedApiResponse
from app.models.auth import AuthLoginRequest, AuthRefreshRequest


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _reserved_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=501,
        detail=ReservedApiResponse(
            status="reserved",
            detail=detail,
            reserved_for="phase_2_auth_integration",
            docs_ref="docs/05-后台端.md#31-首次初始化与重启规则",
        ).model_dump(),
    )


@router.post("/login", response_model=ReservedApiResponse)
async def login(_: AuthLoginRequest) -> ReservedApiResponse:
    raise _reserved_error("认证接口已预留，当前版本未接入用户存储、密码校验与 JWT 签发")


@router.post("/refresh", response_model=ReservedApiResponse)
async def refresh_token(_: AuthRefreshRequest) -> ReservedApiResponse:
    raise _reserved_error("刷新接口已预留，当前版本未接入 refresh token 校验与轮换")
