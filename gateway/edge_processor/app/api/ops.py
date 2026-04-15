from __future__ import annotations

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.services.ops_websocket_manager import OpsWebSocketManager
from app.services.runner import EdgeProcessorRunner


router = APIRouter(tags=["ops"])


@router.get("/ops/v1/health")
async def get_gateway_ops_health(request: Request) -> dict:
    runner: EdgeProcessorRunner = request.app.state.runner
    summary = await runner.get_ops_health_summary()
    return summary.model_dump()


@router.get("/ops/v1/health/components")
async def get_gateway_ops_components(request: Request) -> list[dict]:
    runner: EdgeProcessorRunner = request.app.state.runner
    components = await runner.get_ops_components()
    return [item.model_dump() for item in components]


@router.get("/ops/v1/stats")
async def get_gateway_ops_stats(request: Request) -> dict:
    runner: EdgeProcessorRunner = request.app.state.runner
    stats = await runner.get_ops_stats()
    return stats.model_dump()


@router.websocket("/ops/ws")
async def gateway_ops_websocket(websocket: WebSocket) -> None:
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
