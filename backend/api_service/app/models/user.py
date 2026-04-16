from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


UserRole = Literal["admin", "teacher", "student"]

_USERNAME_PATTERN = r"^[a-z0-9_][a-z0-9_.-]{2,63}$"


class UserSummary(BaseModel):
    username: str
    role: UserRole
    gym_ids: list[str] = Field(default_factory=list)
    device_ids: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=_USERNAME_PATTERN)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole
    gym_ids: list[str] = Field(default_factory=list)
    device_ids: list[str] = Field(default_factory=list)


class UserUpdateRequest(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: UserRole | None = None
    gym_ids: list[str] | None = None
    device_ids: list[str] | None = None


class UserDeleteResponse(BaseModel):
    ok: bool = True


class StoredUser(UserSummary):
    password_hash: str
