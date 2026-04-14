from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.websocket_manager import WebSocketManager


router = APIRouter()


@router.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    manager: WebSocketManager = websocket.app.state.websocket_manager
    await manager.connect(websocket)

    try:
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")
            data = message.get("data", {})

            if message_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif message_type == "subscribe":
                await manager.subscribe(websocket, list(data.get("device_ids", [])))
            elif message_type == "unsubscribe":
                await manager.unsubscribe(websocket, list(data.get("device_ids", [])))
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
