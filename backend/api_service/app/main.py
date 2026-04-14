from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    alerts,
    bindings,
    devices,
    gateway_commands,
    health,
    ingest,
    system_health,
    telemetry,
    websocket,
)
from app.services.device_config_service import DeviceConfigService
from app.services.ingest_service import IngestService
from app.services.realtime_service import RealtimeService
from app.services.websocket_manager import WebSocketManager
from app.settings import RuntimeSettings, load_settings
from app.storage import create_store


def create_app(settings: RuntimeSettings | None = None) -> FastAPI:
    runtime_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        event_store = create_store(runtime_settings)
        websocket_manager = WebSocketManager()
        realtime_service = RealtimeService(runtime_settings, websocket_manager)
        device_config_service = DeviceConfigService(
            store=event_store,
            topic_prefix=runtime_settings.device_command.topic_prefix,
            default_qos=runtime_settings.device_command.default_qos,
            default_retain=runtime_settings.device_command.default_retain,
            pending_fetch_limit=runtime_settings.device_command.pending_fetch_limit,
        )
        app.state.event_store = event_store
        app.state.websocket_manager = websocket_manager
        app.state.realtime_service = realtime_service
        app.state.ingest_service = IngestService(event_store, realtime_service)
        app.state.device_config_service = device_config_service
        await event_store.initialize()
        await realtime_service.start()
        yield
        await realtime_service.stop()
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
    app.include_router(telemetry.router)
    app.include_router(bindings.router)
    app.include_router(gateway_commands.router)
    app.include_router(system_health.router)
    app.include_router(websocket.router)
    return app


app = create_app()
