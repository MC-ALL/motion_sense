from __future__ import annotations

from fastapi import Request

from app.services.device_config_service import DeviceConfigService
from app.services.ingest_service import IngestService
from app.services.websocket_manager import WebSocketManager
from app.storage.store import Store


def get_event_store(request: Request) -> Store:
    return request.app.state.event_store


def get_ingest_service(request: Request) -> IngestService:
    return request.app.state.ingest_service


def get_device_config_service(request: Request) -> DeviceConfigService:
    return request.app.state.device_config_service


def get_websocket_manager(request: Request) -> WebSocketManager:
    return request.app.state.websocket_manager
