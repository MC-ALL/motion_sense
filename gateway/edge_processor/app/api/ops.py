from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from starlette.websockets import WebSocketState

from app.services.ops_websocket_manager import OpsWebSocketManager
from app.services.runner import EdgeProcessorRunner
from app.settings import RuntimeSettings


router = APIRouter(tags=["ops"])


def _require_ops_rest_token(
    request: Request,
) -> None:
    settings: RuntimeSettings = request.app.state.runtime_settings
    if not settings.ops_auth.enforce_rest:
        return

    expected_token = settings.ops_auth.token
    if not expected_token:
        raise HTTPException(status_code=503, detail="ops rest auth token not configured")

    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")

    actual_token = authorization.removeprefix("Bearer ").strip()
    if actual_token != expected_token:
        raise HTTPException(status_code=403, detail="invalid ops token")


@router.get("/ops/v1/health")
async def get_gateway_ops_health(request: Request) -> dict:
    _require_ops_rest_token(request)
    runner: EdgeProcessorRunner = request.app.state.runner
    summary = await runner.get_ops_health_summary()
    return summary.model_dump()


@router.get("/ops/v1/health/components")
async def get_gateway_ops_components(request: Request) -> list[dict]:
    _require_ops_rest_token(request)
    runner: EdgeProcessorRunner = request.app.state.runner
    components = await runner.get_ops_components()
    return [item.model_dump() for item in components]


@router.get("/ops/v1/stats")
async def get_gateway_ops_stats(request: Request) -> dict:
    _require_ops_rest_token(request)
    runner: EdgeProcessorRunner = request.app.state.runner
    stats = await runner.get_ops_stats()
    return stats.model_dump()


@router.websocket("/ops/ws")
async def gateway_ops_websocket(websocket: WebSocket) -> None:
    settings: RuntimeSettings = websocket.app.state.runtime_settings
    if settings.ops_auth.enforce_ws:
        expected_token = settings.ops_auth.token
        if not expected_token:
            await websocket.close(
                code=status.WS_1011_INTERNAL_ERROR,
                reason="ops ws auth token not configured",
            )
            return
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="missing token")
            return
        if token != expected_token:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid ops token")
            return

    manager: OpsWebSocketManager = websocket.app.state.ops_websocket_manager
    runner: EdgeProcessorRunner = websocket.app.state.runner
    await manager.connect(websocket)

    try:
        summary = await runner.get_ops_health_summary()
        await websocket.send_json({"type": "ops_snapshot", "data": summary.model_dump()})
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        if websocket.application_state == WebSocketState.CONNECTED:
            await manager.disconnect(websocket)
    finally:
        await manager.disconnect(websocket)
