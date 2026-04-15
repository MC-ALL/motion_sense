from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.services.observer_service import OpsObserverService
from app.services.ops_websocket_manager import OpsWebSocketManager


router = APIRouter(tags=["ops"])


@router.get("/api/v1/ops/health")
async def get_ops_health(request: Request) -> dict:
    service: OpsObserverService = request.app.state.observer_service
    return (await service.get_health()).model_dump()


@router.get("/api/v1/ops/health/{module_id}")
async def get_ops_health_detail(request: Request, module_id: str) -> dict:
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
) -> dict:
    service: OpsObserverService = request.app.state.observer_service
    return (await service.get_alerts(limit=limit, status=status)).model_dump()


@router.patch("/api/v1/ops/alerts/{alert_id}/close")
async def close_ops_alert(request: Request, alert_id: int) -> dict:
    service: OpsObserverService = request.app.state.observer_service
    alert = await service.close_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"alert not found: {alert_id}")
    return alert.model_dump()


@router.get("/api/v1/ops/stats")
async def get_ops_stats(request: Request) -> dict:
    service: OpsObserverService = request.app.state.observer_service
    return (await service.get_stats()).model_dump()


@router.websocket("/api/ws/ops")
async def ops_websocket(websocket: WebSocket) -> None:
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
