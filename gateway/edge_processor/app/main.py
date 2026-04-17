from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.health import build_health_router
from app.api.ops import router as ops_router
from app.services.ops_websocket_manager import OpsWebSocketManager
from app.services.runner import EdgeProcessorRunner
from app.settings import DEFAULT_CONFIG_PATH, RuntimeSettings, load_settings


def configure_logging(settings: RuntimeSettings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def get_config_path() -> Path:
    return Path(os.environ.get("EDGE_PROCESSOR_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))


def build_app(settings: RuntimeSettings | None = None) -> FastAPI:
    runtime_settings = settings or load_settings(get_config_path())
    configure_logging(runtime_settings)
    runner = EdgeProcessorRunner(runtime_settings)
    ops_websocket_manager = OpsWebSocketManager()
    runner.set_ops_websocket_manager(ops_websocket_manager)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await runner.start()
        try:
            yield
        finally:
            await runner.stop()

    app = FastAPI(title=runtime_settings.app_name, lifespan=lifespan)
    app.state.runner = runner
    app.state.ops_websocket_manager = ops_websocket_manager
    app.state.runtime_settings = runtime_settings
    app.include_router(build_health_router(runtime_settings))
    app.include_router(ops_router)
    return app


app = build_app()
