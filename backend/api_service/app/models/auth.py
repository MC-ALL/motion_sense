from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


AuthRole = Literal["admin", "teacher", "student", "anonymous"]


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class AuthRefreshRequest(BaseModel):
    refresh_token: str


class AuthLogoutRequest(BaseModel):
    refresh_token: str


class AuthUser(BaseModel):
    username: str
    role: AuthRole = "admin"
    gym_ids: list[str] = Field(default_factory=list)
    device_ids: list[str] = Field(default_factory=list)


class AuthTokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="access token 剩余有效秒数")
    refresh_expires_in: int = Field(description="refresh token 剩余有效秒数")
    user: AuthUser


class AuthLogoutResponse(BaseModel):
    ok: bool = True
