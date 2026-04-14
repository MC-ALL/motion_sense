from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import alerts, devices, health, ingest, websocket
from app.services.ingest_service import IngestService
from app.services.websocket_manager import WebSocketManager
from app.settings import RuntimeSettings, load_settings
from app.storage import create_store


def create_app(settings: RuntimeSettings | None = None) -> FastAPI:
    runtime_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        event_store = create_store(runtime_settings)
        websocket_manager = WebSocketManager()
        app.state.event_store = event_store
        app.state.websocket_manager = websocket_manager
        app.state.ingest_service = IngestService(event_store, websocket_manager)
        await event_store.initialize()
        yield
        await event_store.close()

    app = FastAPI(title=runtime_settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(ingest.router)
    app.include_router(devices.router)
    app.include_router(alerts.router)
    app.include_router(websocket.router)
    return app


app = create_app()
