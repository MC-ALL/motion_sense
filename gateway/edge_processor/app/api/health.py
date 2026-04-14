from __future__ import annotations

from fastapi import APIRouter

from app.settings import RuntimeSettings


def build_health_router(settings: RuntimeSettings) -> APIRouter:
    router = APIRouter()

    @router.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {
            "status": "ok",
            "app_name": settings.app_name,
            "gateway_id": settings.gateway_id,
        }

    return router
