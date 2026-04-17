from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, ops
from app.services.auth_service import AuthService
from app.services.observer_service import OpsObserverService
from app.services.ops_websocket_manager import OpsWebSocketManager
from app.services.sqlite_store import OpsSqliteStore
from app.settings import RuntimeSettings, load_settings


def create_app(
    settings: RuntimeSettings | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> FastAPI:
    runtime_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = OpsSqliteStore(runtime_settings.database_path)
        ops_websocket_manager = OpsWebSocketManager()
        observer_service = OpsObserverService(
            runtime_settings,
            store,
            ops_websocket_manager,
            http_client=http_client,
        )
        auth_service = AuthService(runtime_settings.auth)
        app.state.store = store
        app.state.ops_websocket_manager = ops_websocket_manager
        app.state.observer_service = observer_service
        app.state.auth_service = auth_service
        await store.initialize()
        await observer_service.start()
        yield
        await observer_service.stop()
        await store.close()

    app = FastAPI(title=runtime_settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(ops.router)
    return app


app = create_app()
