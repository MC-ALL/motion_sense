from __future__ import annotations

from fastapi import Request

from app.services.event_store import EventStore
from app.services.ingest_service import IngestService
from app.services.websocket_manager import WebSocketManager


def get_event_store(request: Request) -> EventStore:
    return request.app.state.event_store


def get_ingest_service(request: Request) -> IngestService:
    return request.app.state.ingest_service


def get_websocket_manager(request: Request) -> WebSocketManager:
    return request.app.state.websocket_manager
