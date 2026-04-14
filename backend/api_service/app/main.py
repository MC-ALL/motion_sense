from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import alerts, devices, health, ingest, websocket
from app.services.event_store import EventStore
from app.services.ingest_service import IngestService
from app.services.websocket_manager import WebSocketManager
from app.settings import RuntimeSettings, load_settings


def create_app(settings: RuntimeSettings | None = None) -> FastAPI:
    runtime_settings = settings or load_settings()
    app = FastAPI(title=runtime_settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    event_store = EventStore()
    websocket_manager = WebSocketManager()
    app.state.event_store = event_store
    app.state.websocket_manager = websocket_manager
    app.state.ingest_service = IngestService(event_store, websocket_manager)

    app.include_router(health.router)
    app.include_router(ingest.router)
    app.include_router(devices.router)
    app.include_router(alerts.router)
    app.include_router(websocket.router)
    return app


app = create_app()
