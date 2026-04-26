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
    """Configure process-wide logging from runtime settings.

    :param settings: Validated runtime settings containing the requested log level.
    """
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def get_config_path() -> Path:
    """Return the settings file path selected for this process.

    :return: Path from ``EDGE_PROCESSOR_CONFIG_PATH`` or the container default.
    """
    return Path(os.environ.get("EDGE_PROCESSOR_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))


def build_app(settings: RuntimeSettings | None = None) -> FastAPI:
    """Build the FastAPI application and wire long-running gateway services.

    :param settings: Optional prevalidated settings, mainly used by tests.
    :return: Configured FastAPI application with health and ops routers attached.
    """
    runtime_settings = settings or load_settings(get_config_path())
    configure_logging(runtime_settings)
    runner = EdgeProcessorRunner(runtime_settings)
    ops_websocket_manager = OpsWebSocketManager()
    runner.set_ops_websocket_manager(ops_websocket_manager)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        """Start and stop background services with the FastAPI lifespan."""
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
