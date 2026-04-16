from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from typing import Any
from uuid import uuid4

from app.models.auth import AuthTokenPair, AuthUser
from app.models.user import StoredUser
from app.settings import AuthSettings
from app.storage.store import Store


class AuthError(Exception):
    pass

class AuthService:
    def __init__(self, settings: AuthSettings, store: Store) -> None:
        self._settings = settings
        self._store = store

    @property
    def rest_auth_required(self) -> bool:
        return self._settings.enforce_rest

    @property
    def ws_auth_required(self) -> bool:
        return self._settings.enforce_ws

    @property
    def bootstrap_admin_username(self) -> str:
        return self._settings.admin.username

    async def initialize(self) -> None:
        await self._store.delete_expired_refresh_sessions(now_s=int(time.time()))
        if not self._settings.admin.username or not self._settings.admin.password_hash:
            return
        existing = await self._store.get_user(username=self._settings.admin.username)
        if existing is None:
            await self._store.create_user(
                username=self._settings.admin.username,
                password_hash=self._settings.admin.password_hash,
                role="admin",
                gym_ids=[],
                device_ids=[],
            )

    async def issue_token_pair(self, username: str) -> AuthTokenPair:
        user = await self._require_user(username)
        now_s = int(time.time())
        session_id = str(uuid4())
        refresh_jti = str(uuid4())
        await self._store.create_refresh_session(
            session_id=session_id,
            username=username,
            refresh_jti=refresh_jti,
            expires_at_s=now_s + self._settings.refresh_token_ttl_s,
        )
        return self._build_token_pair(
            user=user,
            session_id=session_id,
            refresh_jti=refresh_jti,
            now_s=now_s,
        )

    async def login(self, username: str, password: str) -> AuthTokenPair:
        user = await self._store.get_user(username=username)
        if user is None:
            raise AuthError("invalid username or password")
        if not verify_password(password=password, encoded=user.password_hash):
            raise AuthError("invalid username or password")
        return await self.issue_token_pair(username=username)

    async def refresh(self, refresh_token: str) -> AuthTokenPair:
        claims = self._decode_token(
            token=refresh_token,
            secret=self._settings.jwt.refresh_secret,
            expected_type="refresh",
        )
        session_id = _require_str_claim(claims, "sid")
        session = await self._store.get_refresh_session(session_id=session_id)
        if session is None:
            raise AuthError("refresh session expired or revoked")
        now_s = int(time.time())
        if session.expires_at_s <= now_s:
            await self._store.delete_refresh_session(session_id=session_id)
            raise AuthError("refresh session expired or revoked")
        if session.username != _require_str_claim(claims, "sub"):
            await self._store.delete_refresh_session(session_id=session_id)
            raise AuthError("refresh session mismatch")
        if session.refresh_jti != _require_str_claim(claims, "jti"):
            await self._store.delete_refresh_session(session_id=session_id)
            raise AuthError("refresh token has been rotated")

        user = await self._require_user(session.username)
        refresh_jti = str(uuid4())
        updated_session = await self._store.update_refresh_session(
            session_id=session_id,
            refresh_jti=refresh_jti,
            expires_at_s=now_s + self._settings.refresh_token_ttl_s,
        )
        if updated_session is None:
            raise AuthError("refresh session expired or revoked")
        return self._build_token_pair(
            user=user,
            session_id=session_id,
            refresh_jti=refresh_jti,
            now_s=now_s,
        )

    async def logout(self, refresh_token: str) -> None:
        claims = self._decode_token(
            token=refresh_token,
            secret=self._settings.jwt.refresh_secret,
            expected_type="refresh",
        )
        session_id = _require_str_claim(claims, "sid")
        await self._store.delete_refresh_session(session_id=session_id)

    def verify_access_token(self, token: str) -> AuthUser:
        claims = self._decode_token(
            token=token,
            secret=self._settings.jwt.access_secret,
            expected_type="access",
        )
        return AuthUser(
            username=_require_str_claim(claims, "sub"),
            role=_require_str_claim(claims, "role"),
            gym_ids=_require_str_list_claim(claims, "gym_ids"),
            device_ids=_require_str_list_claim(claims, "device_ids"),
        )

    def anonymous_user(self) -> AuthUser:
        return AuthUser(username="anonymous", role="anonymous", gym_ids=[], device_ids=[])

    async def _require_user(self, username: str) -> StoredUser:
        user = await self._store.get_user(username=username)
        if user is None:
            raise AuthError("user not found or disabled")
        return user

    def _build_token_pair(
        self,
        *,
        user: StoredUser,
        session_id: str,
        refresh_jti: str,
        now_s: int,
    ) -> AuthTokenPair:
        access_payload = {
            "sub": user.username,
            "role": user.role,
            "gym_ids": user.gym_ids,
            "device_ids": user.device_ids,
            "typ": "access",
            "iat": now_s,
            "exp": now_s + self._settings.access_token_ttl_s,
            "iss": self._settings.issuer,
            "aud": self._settings.audience,
            "jti": str(uuid4()),
        }
        refresh_payload = {
            "sub": user.username,
            "role": user.role,
            "gym_ids": user.gym_ids,
            "device_ids": user.device_ids,
            "typ": "refresh",
            "iat": now_s,
            "exp": now_s + self._settings.refresh_token_ttl_s,
            "iss": self._settings.issuer,
            "aud": self._settings.audience,
            "sid": session_id,
            "jti": refresh_jti,
        }
        access_token = self._encode_token(secret=self._settings.jwt.access_secret, payload=access_payload)
        refresh_token = self._encode_token(secret=self._settings.jwt.refresh_secret, payload=refresh_payload)
        auth_user = AuthUser(
            username=user.username,
            role=user.role,
            gym_ids=list(user.gym_ids),
            device_ids=list(user.device_ids),
        )
        return AuthTokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self._settings.access_token_ttl_s,
            refresh_expires_in=self._settings.refresh_token_ttl_s,
            user=auth_user,
        )

    def _encode_token(self, *, secret: str, payload: dict[str, Any]) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        encoded_header = _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        encoded_payload = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        signing_input = f"{encoded_header}.{encoded_payload}"
        signature = hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
        return f"{signing_input}.{_b64url_encode(signature)}"

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


def generate_password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1)
    return "scrypt$16384$8$1$%s$%s" % (
        _b64url_encode(salt),
        _b64url_encode(digest),
    )


def verify_password(*, password: str, encoded: str) -> bool:
    try:
        algorithm, n_raw, r_raw, p_raw, salt_raw, digest_raw = encoded.split("$", 5)
    except ValueError:
        return False
    if algorithm != "scrypt":
        return False
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=_b64url_decode(salt_raw),
        n=int(n_raw),
        r=int(r_raw),
        p=int(p_raw),
    )
    return hmac.compare_digest(digest, _b64url_decode(digest_raw))


def generate_runtime_secret() -> str:
    return secrets.token_urlsafe(48)


def generate_bootstrap_password() -> str:
    return secrets.token_urlsafe(12)


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("utf-8")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def _require_str_claim(claims: dict[str, Any], key: str) -> str:
    value = claims.get(key)
    if not isinstance(value, str) or not value:
        raise AuthError(f"invalid token claim: {key}")
    return value


def _require_str_list_claim(claims: dict[str, Any], key: str) -> list[str]:
    value = claims.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise AuthError(f"invalid token claim: {key}")
    items = [item for item in value if isinstance(item, str) and item]
    if len(items) != len(value):
        raise AuthError(f"invalid token claim: {key}")
    return items
