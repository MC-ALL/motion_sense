from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from starlette.websockets import WebSocketState

from app.services.auth_service import AuthError, AuthService
from app.services.websocket_manager import WebSocketManager


router = APIRouter()


@router.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
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
        if websocket.application_state == WebSocketState.CONNECTED:
            await manager.disconnect(websocket)
