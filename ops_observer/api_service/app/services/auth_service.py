from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from app.settings import OpsApiAuthSettings


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class AuthUser:
    username: str
    role: str
    gym_ids: list[str]
    device_ids: list[str]


class AuthService:
    def __init__(self, settings: OpsApiAuthSettings) -> None:
        self._settings = settings

    @property
    def rest_auth_required(self) -> bool:
        return self._settings.enforce_rest

    @property
    def ws_auth_required(self) -> bool:
        return self._settings.enforce_ws

    def verify_access_token(self, token: str) -> AuthUser:
        secret = self._settings.jwt.access_secret
        if not secret:
            raise AuthError("missing access secret")

        claims = self._decode_token(
            token=token,
            secret=secret,
            expected_type="access",
        )
        return AuthUser(
            username=_require_str_claim(claims, "sub"),
            role=_require_str_claim(claims, "role"),
            gym_ids=_require_str_list_claim(claims, "gym_ids"),
            device_ids=_require_str_list_claim(claims, "device_ids"),
        )

    def _decode_token(self, *, token: str, secret: str, expected_type: str) -> dict[str, Any]:
        try:
            encoded_header, encoded_payload, encoded_signature = token.split(".")
        except ValueError as exc:
            raise AuthError("invalid token format") from exc

        signing_input = f"{encoded_header}.{encoded_payload}"
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            signing_input.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        try:
            actual_signature = _b64url_decode(encoded_signature)
        except (ValueError, binascii.Error) as exc:
            raise AuthError("invalid token signature") from exc
        if not hmac.compare_digest(actual_signature, expected_signature):
            raise AuthError("invalid token signature")

        try:
            header = json.loads(_b64url_decode(encoded_header))
            payload = json.loads(_b64url_decode(encoded_payload))
        except (json.JSONDecodeError, ValueError, binascii.Error) as exc:
            raise AuthError("invalid token payload") from exc

        if header.get("alg") != "HS256":
            raise AuthError("unsupported token algorithm")
        if payload.get("typ") != expected_type:
            raise AuthError("unexpected token type")
        if payload.get("iss") != self._settings.issuer:
            raise AuthError("invalid token issuer")
        if payload.get("aud") != self._settings.audience:
            raise AuthError("invalid token audience")
        if int(payload.get("exp", 0)) <= int(time.time()):
            raise AuthError("token expired")
        return payload


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _require_str_claim(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, str):
        return value
    raise AuthError(f"invalid token claim: {key}")


def _require_str_list_claim(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise AuthError(f"invalid token claim: {key}")
    return list(value)
