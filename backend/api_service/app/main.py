from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import alerts, bindings, devices, health, ingest, system_health, telemetry, websocket
from app.services.device_config_service import DeviceConfigService
from app.services.ingest_service import IngestService
from app.services.mqtt_config_publisher import MqttConfigPublisher
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
        config_publisher = MqttConfigPublisher(runtime_settings)
        device_config_service = DeviceConfigService(
            store=event_store,
            publisher=config_publisher,
            topic_prefix=runtime_settings.mqtt.topic_prefix,
            default_qos=runtime_settings.mqtt.default_qos,
            default_retain=runtime_settings.mqtt.default_retain,
        )
        app.state.event_store = event_store
        app.state.websocket_manager = websocket_manager
        app.state.realtime_service = realtime_service
        app.state.ingest_service = IngestService(event_store, realtime_service)
        app.state.config_publisher = config_publisher
        app.state.device_config_service = device_config_service
        await event_store.initialize()
        await realtime_service.start()
        await config_publisher.start()
        yield
        await config_publisher.stop()
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
    app.include_router(system_health.router)
    app.include_router(websocket.router)
    return app


app = create_app()
