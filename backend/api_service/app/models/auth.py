from __future__ import annotations

from pydantic import BaseModel


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class AuthRefreshRequest(BaseModel):
    refresh_token: str

