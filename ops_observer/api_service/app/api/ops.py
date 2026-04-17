from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from starlette.websockets import WebSocketState

from app.api.deps import require_admin_user
from app.services.auth_service import AuthError, AuthService
from app.services.observer_service import OpsObserverService
from app.services.ops_websocket_manager import OpsWebSocketManager


router = APIRouter(tags=["ops"])


@router.get("/api/v1/ops/health")
async def get_ops_health(
    request: Request,
    _: object = Depends(require_admin_user),
) -> dict:
    service: OpsObserverService = request.app.state.observer_service
    return (await service.get_health()).model_dump()


@router.get("/api/v1/ops/health/{module_id}")
async def get_ops_health_detail(
    request: Request,
    module_id: str,
    _: object = Depends(require_admin_user),
) -> dict:
    service: OpsObserverService = request.app.state.observer_service
    detail = await service.get_health_detail(module_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"module not found: {module_id}")
    return detail.model_dump()


@router.get("/api/v1/ops/alerts")
async def get_ops_alerts(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    status: str | None = Query(default=None, pattern="^(open|closed)$"),
    _: object = Depends(require_admin_user),
) -> dict:
    service: OpsObserverService = request.app.state.observer_service
    return (await service.get_alerts(limit=limit, status=status)).model_dump()


@router.patch("/api/v1/ops/alerts/{alert_id}/close")
async def close_ops_alert(
    request: Request,
    alert_id: int,
    _: object = Depends(require_admin_user),
) -> dict:
    service: OpsObserverService = request.app.state.observer_service
    alert = await service.close_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"alert not found: {alert_id}")
    return alert.model_dump()


@router.get("/api/v1/ops/stats")
async def get_ops_stats(
    request: Request,
    _: object = Depends(require_admin_user),
) -> dict:
    service: OpsObserverService = request.app.state.observer_service
    return (await service.get_stats()).model_dump()


@router.websocket("/api/ws/ops")
async def ops_websocket(websocket: WebSocket) -> None:
    auth_service: AuthService = websocket.app.state.auth_service
    if auth_service.ws_auth_required:
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="missing token")
            return
        try:
            user = auth_service.verify_access_token(token)
        except AuthError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid token")
            return
        if user.role != "admin":
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="admin role required")
            return

    manager: OpsWebSocketManager = websocket.app.state.ops_websocket_manager
    service: OpsObserverService = websocket.app.state.observer_service
    await manager.connect(websocket)

    try:
        await websocket.send_json({"type": "ops_snapshot", "data": (await service.get_health()).model_dump()})
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        if websocket.application_state == WebSocketState.CONNECTED:
            await manager.disconnect(websocket)
    finally:
        await manager.disconnect(websocket)
