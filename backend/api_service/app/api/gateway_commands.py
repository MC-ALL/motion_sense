from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status

from app.api.deps import (
    get_device_config_service,
    require_admin_user,
)
from app.models.device_config import (
    DeviceConfigCommandRecord,
    GatewayCommandResultRequest,
    GatewayPendingCommandList,
)
from app.services.device_config_service import (
    DeviceConfigCommandGatewayMismatchError,
    DeviceConfigCommandNotFoundError,
    DeviceConfigService,
)
from app.services.gateway_command_websocket_manager import GatewayCommandWebSocketManager


router = APIRouter(prefix="/api/v1/gateway", tags=["gateway-commands"])


@router.get("/{gateway_id}/commands/pending", response_model=GatewayPendingCommandList)
async def list_pending_gateway_commands(
    gateway_id: str,
    service: DeviceConfigService = Depends(get_device_config_service),
) -> GatewayPendingCommandList:
    items = await service.list_pending_commands(gateway_id=gateway_id)
    return GatewayPendingCommandList(gateway_id=gateway_id, items=items)


@router.websocket("/{gateway_id}/commands/ws")
async def gateway_command_websocket_endpoint(
    websocket: WebSocket,
    gateway_id: str,
) -> None:
    gateway_channel_token = websocket.app.state.settings.device_command.gateway_channel_token
    if not gateway_channel_token:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="gateway command channel token not configured",
        )
        return

    token = websocket.query_params.get("token")
    if token != gateway_channel_token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid token")
        return

    manager: GatewayCommandWebSocketManager = websocket.app.state.gateway_command_websocket_manager
    await manager.connect(gateway_id, websocket)

    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await manager.disconnect(gateway_id, websocket)


@router.get("/commands/{command_id}", response_model=DeviceConfigCommandRecord)
async def get_gateway_command(
    command_id: str,
    _: object = Depends(require_admin_user),
    service: DeviceConfigService = Depends(get_device_config_service),
) -> DeviceConfigCommandRecord:
    try:
        return await service.get_command(command_id=command_id)
    except DeviceConfigCommandNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{gateway_id}/commands/{command_id}/result",
    response_model=DeviceConfigCommandRecord,
)
async def report_gateway_command_result(
    gateway_id: str,
    command_id: str,
    payload: GatewayCommandResultRequest,
    service: DeviceConfigService = Depends(get_device_config_service),
) -> DeviceConfigCommandRecord:
    try:
        return await service.report_command_result(
            gateway_id=gateway_id,
            command_id=command_id,
            result=payload,
        )
    except DeviceConfigCommandNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeviceConfigCommandGatewayMismatchError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
