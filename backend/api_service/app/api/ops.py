from __future__ import annotations

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect, status
from starlette.websockets import WebSocketState

from app.api.deps import require_rest_user
from app.services.auth_service import AuthError, AuthService
from app.services.ops_service import BackendOpsService
from app.services.ops_websocket_manager import OpsWebSocketManager


router = APIRouter(tags=["ops"])


@router.get("/ops/v1/health")
async def get_backend_ops_health(
    request: Request,
    _: object = Depends(require_rest_user),
) -> dict:
    service: BackendOpsService = request.app.state.ops_service
    return (await service.get_health_summary()).model_dump()


@router.get("/ops/v1/health/components")
async def get_backend_ops_components(
    request: Request,
    _: object = Depends(require_rest_user),
) -> list[dict]:
    service: BackendOpsService = request.app.state.ops_service
    return [item.model_dump() for item in await service.get_health_components()]


@router.get("/ops/v1/stats")
async def get_backend_ops_stats(
    request: Request,
    _: object = Depends(require_rest_user),
) -> dict:
    service: BackendOpsService = request.app.state.ops_service
    return (await service.get_stats()).model_dump()


@router.websocket("/ops/ws")
async def backend_ops_websocket(websocket: WebSocket) -> None:
    auth_service: AuthService = websocket.app.state.auth_service
    if auth_service.ws_auth_required:
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="missing token")
            return
        try:
            auth_service.verify_access_token(token)
        except AuthError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid token")
            return

    manager: OpsWebSocketManager = websocket.app.state.ops_websocket_manager
    service: BackendOpsService = websocket.app.state.ops_service
    await manager.connect(websocket)

    try:
        await websocket.send_json({"type": "ops_snapshot", "data": (await service.get_health_summary()).model_dump()})
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        if websocket.application_state == WebSocketState.CONNECTED:
            await manager.disconnect(websocket)
    finally:
        await manager.disconnect(websocket)
