#!/bin/sh
set -eu

runtime_dir="/runtime/config/backend/api_service"
defaults_dir="/opt/motion_sense/deployment/backend/api_service/defaults"
bootstrap_admin_path="$runtime_dir/bootstrap_admin.txt"

mkdir -p "$runtime_dir" /runtime/secrets

if [ ! -f "$runtime_dir/app_settings.yaml" ]; then
  cp "$defaults_dir/default_app_settings.yaml" "$runtime_dir/app_settings.yaml"
fi

python - <<'PY'
from __future__ import annotations

import hashlib
import secrets
from pathlib import Path

import yaml


def b64url(value: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("utf-8")


def generate_secret() -> str:
    return secrets.token_urlsafe(48)


def generate_password() -> str:
    return secrets.token_urlsafe(12)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1)
    return "scrypt$16384$8$1$%s$%s" % (b64url(salt), b64url(digest))


runtime_dir = Path("/runtime/config/backend/api_service")
config_path = runtime_dir / "app_settings.yaml"
bootstrap_path = runtime_dir / "bootstrap_admin.txt"

raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
auth = raw.setdefault("auth", {})
admin = auth.setdefault("admin", {})
jwt = auth.setdefault("jwt", {})

admin_username = admin.get("username") or "admin"
admin_password = None
changed = False

if admin.get("password_hash") == "__GENERATE_PASSWORD_HASH__":
    admin_password = generate_password()
    admin["password_hash"] = hash_password(admin_password)
    changed = True

if jwt.get("access_secret") == "__GENERATE_ACCESS_SECRET__":
    jwt["access_secret"] = generate_secret()
    changed = True

if jwt.get("refresh_secret") == "__GENERATE_REFRESH_SECRET__":
    jwt["refresh_secret"] = generate_secret()
    changed = True

if changed:
    config_path.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

if admin_password is not None and not bootstrap_path.exists():
    bootstrap_path.write_text(
        f"username: {admin_username}\npassword: {admin_password}\n",
        encoding="utf-8",
    )
    bootstrap_path.chmod(0o600)
PY

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
