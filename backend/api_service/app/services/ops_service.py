from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from redis.asyncio import Redis

from app.models.ops import BackendOpsComponent, BackendOpsHealthSummary, BackendOpsStats
from app.services.ops_websocket_manager import OpsWebSocketManager
from app.services.websocket_manager import WebSocketManager
from app.settings import RuntimeSettings
from app.storage.memory_store import EventStore
from app.storage.postgres_store import PostgresStore


class BackendOpsService:
    def __init__(
        self,
        settings: RuntimeSettings,
        store,
        websocket_manager: WebSocketManager,
        ops_websocket_manager: OpsWebSocketManager,
    ) -> None:
        self._settings = settings
        self._store = store
        self._websocket_manager = websocket_manager
        self._ops_websocket_manager = ops_websocket_manager
        self._started_at = datetime.now(UTC)
        self._latest_components: list[BackendOpsComponent] = []
        self._last_health_checked_at: str | None = None
        self._last_health_error: str | None = None
        self._refresh_task: asyncio.Task[None] | None = None
        self._ingest_batches_total = 0
        self._ingest_items_total = 0
        self._published_telemetry_total = 0
        self._published_alert_total = 0
        self._published_device_status_total = 0
        self._config_commands_created_total = 0
        self._command_results_reported_total = 0
        self._command_result_failures_total = 0
        self._last_ingest_at: str | None = None

    async def start(self) -> None:
        if self._refresh_task is not None:
            return
        self._refresh_task = asyncio.create_task(self._refresh_loop(), name="backend-ops-refresh")

    async def stop(self) -> None:
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None

    def record_ingest_batch(self, item_count: int) -> None:
        self._ingest_batches_total += 1
        self._ingest_items_total += item_count
        self._last_ingest_at = datetime.now(UTC).isoformat()

    def record_realtime_message(self, message_type: str) -> None:
        if message_type == "telemetry":
            self._published_telemetry_total += 1
        elif message_type == "alert":
            self._published_alert_total += 1
        elif message_type == "device_status":
            self._published_device_status_total += 1

    def record_config_command_created(self) -> None:
        self._config_commands_created_total += 1

    def record_command_result(self, status: str) -> None:
        self._command_results_reported_total += 1
        if status != "succeeded":
            self._command_result_failures_total += 1

    async def get_health_components(self) -> list[BackendOpsComponent]:
        if not self._latest_components:
            await self.refresh_health_snapshot()
        return list(self._latest_components)

    async def get_health_summary(self) -> BackendOpsHealthSummary:
        components = await self.get_health_components()
        return self._build_summary(components)

    async def get_stats(self) -> BackendOpsStats:
        business_ws = await self._websocket_manager.connection_count()
        ops_ws = await self._ops_websocket_manager.connection_count()
        last_known_health_status = self._build_summary(self._latest_components).health_status if self._latest_components else "unknown"
        return BackendOpsStats(
            module_id="backend:api-main",
            started_at=self._started_at.isoformat(),
            uptime_s=max(int((datetime.now(UTC) - self._started_at).total_seconds()), 0),
            storage_backend=self._settings.storage_backend,
            realtime_backend=self._settings.realtime_backend,
            rest_auth_enabled=self._settings.auth.enforce_rest,
            ws_auth_enabled=self._settings.auth.enforce_ws,
            active_business_ws_connections=business_ws,
            active_ops_ws_connections=ops_ws,
            ingest_batches_total=self._ingest_batches_total,
            ingest_items_total=self._ingest_items_total,
            published_telemetry_total=self._published_telemetry_total,
            published_alert_total=self._published_alert_total,
            published_device_status_total=self._published_device_status_total,
            config_commands_created_total=self._config_commands_created_total,
            command_results_reported_total=self._command_results_reported_total,
            command_result_failures_total=self._command_result_failures_total,
            last_ingest_at=self._last_ingest_at,
            last_health_checked_at=self._last_health_checked_at,
            last_health_error=self._last_health_error,
            last_known_health_status=last_known_health_status,
        )

    async def refresh_health_snapshot(self) -> None:
        checked_at = datetime.now(UTC).isoformat()
        components = [
            self._api_component(checked_at),
            await self._database_component(checked_at),
            await self._redis_component(checked_at),
            await self._websocket_component(checked_at),
        ]
        self._latest_components = components
        self._last_health_checked_at = checked_at
        self._last_health_error = None
        await self._ops_websocket_manager.broadcast(
            {"type": "ops_snapshot", "data": self._build_summary(components).model_dump()}
        )

    async def _refresh_loop(self) -> None:
        while True:
            try:
                await self.refresh_health_snapshot()
            except Exception as exc:
                self._last_health_error = str(exc)
            await asyncio.sleep(self._settings.ops_refresh_interval_s)

    def _api_component(self, checked_at: str) -> BackendOpsComponent:
        return BackendOpsComponent(
            component_id="api_service",
            component_type="api_service",
            display_name="后台 API",
            online=True,
            health_status="healthy",
            checked_at=checked_at,
            endpoint=f"http://127.0.0.1:{self._settings.port}/healthz",
            detail="process alive",
        )

    async def _database_component(self, checked_at: str) -> BackendOpsComponent:
        start = time.monotonic()
        if isinstance(self._store, EventStore):
            return BackendOpsComponent(
                component_id="database",
                component_type="database",
                display_name="内存存储",
                online=True,
                health_status="healthy",
                checked_at=checked_at,
                detail="memory store active",
            )

        if isinstance(self._store, PostgresStore):
            try:
                async with self._store._pool.connection() as connection:
                    async with connection.cursor() as cursor:
                        await cursor.execute("SELECT 1 AS ready")
                        row = await cursor.fetchone()
                return BackendOpsComponent(
                    component_id="database",
                    component_type="database",
                    display_name="PostgreSQL / TimescaleDB",
                    online=True,
                    health_status="healthy",
                    checked_at=checked_at,
                    endpoint=self._settings.database.dsn(),
                    latency_ms=max(int((time.monotonic() - start) * 1000), 0),
                    detail=f"ready={row['ready']}",
                )
            except Exception as exc:
                return BackendOpsComponent(
                    component_id="database",
                    component_type="database",
                    display_name="PostgreSQL / TimescaleDB",
                    online=False,
                    health_status="offline",
                    checked_at=checked_at,
                    endpoint=self._settings.database.dsn(),
                    latency_ms=max(int((time.monotonic() - start) * 1000), 0),
                    detail=str(exc),
                )

        return BackendOpsComponent(
            component_id="database",
            component_type="database",
            display_name="数据库",
            online=False,
            health_status="unknown",
            checked_at=checked_at,
            detail="unsupported store implementation",
        )

    async def _redis_component(self, checked_at: str) -> BackendOpsComponent:
        start = time.monotonic()
        if self._settings.realtime_backend != "redis":
            return BackendOpsComponent(
                component_id="redis",
                component_type="redis",
                display_name="Redis",
                online=True,
                health_status="healthy",
                checked_at=checked_at,
                detail="local realtime backend active",
            )

        client = Redis.from_url(self._settings.redis.url(), decode_responses=True)
        try:
            await client.ping()
            return BackendOpsComponent(
                component_id="redis",
                component_type="redis",
                display_name="Redis",
                online=True,
                health_status="healthy",
                checked_at=checked_at,
                endpoint=self._settings.redis.url(),
                latency_ms=max(int((time.monotonic() - start) * 1000), 0),
                detail="ping ok",
            )
        except Exception as exc:
            return BackendOpsComponent(
                component_id="redis",
                component_type="redis",
                display_name="Redis",
                online=False,
                health_status="offline",
                checked_at=checked_at,
                endpoint=self._settings.redis.url(),
                latency_ms=max(int((time.monotonic() - start) * 1000), 0),
                detail=str(exc),
            )
        finally:
            await client.aclose()

    async def _websocket_component(self, checked_at: str) -> BackendOpsComponent:
        active_connections = await self._websocket_manager.connection_count()
        return BackendOpsComponent(
            component_id="websocket_hub",
            component_type="websocket_hub",
            display_name="业务 WebSocket",
            online=True,
            health_status="healthy",
            checked_at=checked_at,
            detail=f"active_connections={active_connections}",
        )

    def _build_summary(self, components: list[BackendOpsComponent]) -> BackendOpsHealthSummary:
        component_total = len(components)
        healthy_components = sum(1 for item in components if item.online and item.health_status == "healthy")
        degraded_components = sum(1 for item in components if item.online and item.health_status == "degraded")
        offline_components = sum(1 for item in components if (not item.online) or item.health_status == "offline")

        if component_total == 0:
            online = False
            health_status = "unknown"
            checked_at = self._last_health_checked_at or self._started_at.isoformat()
        elif offline_components > 0:
            online = False
            health_status = "offline"
            checked_at = components[0].checked_at
        elif degraded_components > 0:
            online = True
            health_status = "degraded"
            checked_at = components[0].checked_at
        else:
            online = True
            health_status = "healthy"
            checked_at = components[0].checked_at

        return BackendOpsHealthSummary(
            module_id="backend:api-main",
            online=online,
            health_status=health_status,
            checked_at=checked_at,
            component_total=component_total,
            healthy_components=healthy_components,
            degraded_components=degraded_components,
            offline_components=offline_components,
        )
