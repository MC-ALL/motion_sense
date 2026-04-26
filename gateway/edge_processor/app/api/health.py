from __future__ import annotations

from fastapi import APIRouter

from app.settings import RuntimeSettings


def build_health_router(settings: RuntimeSettings) -> APIRouter:
    """Build the lightweight local health router.

    :param settings: Runtime settings used to identify the app and gateway.
    :return: Router exposing ``/healthz`` for container and ops checks.
    """
    router = APIRouter()

    @router.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Return a minimal process-alive response."""
        return {
            "status": "ok",
            "app_name": settings.app_name,
            "gateway_id": settings.gateway_id,
        }

    return router
