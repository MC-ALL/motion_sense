from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
import websockets
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from app.models.ops import (
    ModuleComponent,
    ModuleHealthSummary,
    ModuleStats,
    OpsAlertListResponse,
    OpsAlertRecord,
    OpsHealthDetailResponse,
    OpsHealthListResponse,
    OpsSnapshotMessage,
    OpsStatsResponse,
)
from app.services.ops_websocket_manager import OpsWebSocketManager
from app.services.sqlite_store import OpsSqliteStore
from app.settings import RuntimeSettings, UpstreamModuleSettings


@dataclass
class _ModuleState:
    online: bool
    health_status: str


@dataclass
class _UpstreamAuthSession:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime


class OpsObserverService:
    def __init__(
        self,
        settings: RuntimeSettings,
        store: OpsSqliteStore,
        websocket_manager: OpsWebSocketManager,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._store = store
        self._websocket_manager = websocket_manager
        self._http_client = http_client or httpx.AsyncClient()
        self._owns_http_client = http_client is None
        self._refresh_task: asyncio.Task[None] | None = None
        self._snapshot_task: asyncio.Task[None] | None = None
        self._module_ws_tasks: dict[str, asyncio.Task[None]] = {}
        self._last_states: dict[str, _ModuleState] = {}
        self._module_auth_sessions: dict[str, _UpstreamAuthSession] = {}
        self._refresh_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._refresh_task is not None:
            return
        await self.refresh_once()
        self._refresh_task = asyncio.create_task(self._refresh_loop(), name="ops-observer-refresh")
        self._snapshot_task = asyncio.create_task(
            self._snapshot_loop(),
            name="ops-observer-ws-snapshot",
        )
        for module in self._settings.upstream_modules:
            if not module.ws_enabled:
                continue
            self._module_ws_tasks[module.module_id] = asyncio.create_task(
                self._module_ops_ws_loop(module),
                name=f"ops-observer-upstream-ws-{module.module_id}",
            )

    async def stop(self) -> None:
        for task in (*self._module_ws_tasks.values(), self._refresh_task, self._snapshot_task):
            if task is None:
                continue
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._refresh_task = None
        self._snapshot_task = None
        self._module_ws_tasks = {}
        if self._owns_http_client:
            await self._http_client.aclose()

    async def refresh_once(self) -> None:
        for module in self._settings.upstream_modules:
            await self.refresh_module(module)
        await self.broadcast_snapshot()

    async def refresh_module(self, module: UpstreamModuleSettings) -> None:
        async with self._refresh_lock:
            persisted_at = self._now_iso()
            summary, components, stats = await self._collect_module_snapshot(module)
            await self._store.save_module_snapshot(summary, components, stats, persisted_at)
            await self._emit_transition_alerts(summary)

    async def get_health(self) -> OpsHealthListResponse:
        items = await self._store.list_health()
        updated_at = await self._store.latest_updated_at()
        return OpsHealthListResponse(items=items, updated_at=updated_at)

    async def get_health_detail(self, module_id: str) -> OpsHealthDetailResponse | None:
        summary, components, stats = await self._store.get_health_detail(module_id)
        if summary is None:
            return None
        return OpsHealthDetailResponse(summary=summary, components=components, stats=stats)

    async def get_alerts(self, *, limit: int, status: str | None) -> OpsAlertListResponse:
        return OpsAlertListResponse(items=await self._store.list_alerts(limit=limit, status=status))

    async def close_alert(self, alert_id: int) -> OpsAlertRecord | None:
        alert = await self._store.close_alert(alert_id, self._now_iso())
        if alert is not None:
            await self._websocket_manager.broadcast({"type": "ops_alert", "data": alert.model_dump()})
        return alert

    async def get_stats(self) -> OpsStatsResponse:
        items = await self._store.list_stats()
        updated_at = await self._store.latest_updated_at()
        return OpsStatsResponse(items=items, updated_at=updated_at)

    async def broadcast_snapshot(self) -> None:
        snapshot = await self.get_health()
        await self._websocket_manager.broadcast(OpsSnapshotMessage(data=snapshot).model_dump())

    async def _refresh_loop(self) -> None:
        while True:
            await asyncio.sleep(self._settings.poll_interval_s)
            await self.refresh_once()

    async def _snapshot_loop(self) -> None:
        while True:
            await asyncio.sleep(self._settings.ws_snapshot_interval_s)
            await self.broadcast_snapshot()

    async def _module_ops_ws_loop(self, module: UpstreamModuleSettings) -> None:
        while True:
            try:
                ws_url = await self._build_ws_url(module)
                async with websockets.connect(ws_url) as websocket:
                    ping_task = asyncio.create_task(
                        self._upstream_ping_loop(websocket),
                        name=f"ops-observer-upstream-ping-{module.module_id}",
                    )
                    try:
                        async for raw_message in websocket:
                            await self._handle_upstream_ws_message(module, raw_message)
                    finally:
                        ping_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await ping_task
            except asyncio.CancelledError:
                raise
            except (ConnectionClosedOK, ConnectionClosedError, OSError, websockets.WebSocketException):
                self._invalidate_module_access_token(module)
                await asyncio.sleep(self._settings.upstream_ws_retry_interval_s)

    async def _upstream_ping_loop(self, websocket) -> None:
        while True:
            await asyncio.sleep(self._settings.upstream_ws_ping_interval_s)
            await websocket.send('{"type":"ping"}')

    async def _handle_upstream_ws_message(
        self,
        module: UpstreamModuleSettings,
        raw_message: str,
    ) -> None:
        try:
            message = json.loads(raw_message)
        except Exception:
            return
        if message.get("type") != "ops_snapshot":
            return
        await self.refresh_module(module)
        await self.broadcast_snapshot()

    async def _collect_module_snapshot(
        self,
        module: UpstreamModuleSettings,
    ) -> tuple[ModuleHealthSummary, list[ModuleComponent], ModuleStats | None]:
        try:
            summary_payload = await self._get_json(module, "/ops/v1/health")
            summary = ModuleHealthSummary.model_validate(
                {
                    **summary_payload,
                    "display_name": module.display_name,
                    "module_type": module.module_type,
                    "last_error": None,
                }
            )
        except Exception as exc:
            return self._build_unreachable_snapshot(module, str(exc))

        components: list[ModuleComponent] = []
        stats: ModuleStats | None = None
        last_error: str | None = None

        try:
            components_payload = await self._get_json(module, "/ops/v1/health/components")
            components = [
                ModuleComponent.model_validate({"module_id": summary.module_id, **item})
                for item in components_payload
            ]
        except Exception as exc:
            last_error = f"fetch components failed: {exc}"
            components = [
                ModuleComponent(
                    module_id=summary.module_id,
                    component_id="ops_components_api",
                    component_type="other",
                    display_name="组件明细接口",
                    online=True,
                    health_status="degraded",
                    checked_at=self._now_iso(),
                    endpoint=f"{module.base_url}/ops/v1/health/components",
                    detail=last_error,
                )
            ]

        try:
            stats_payload = await self._get_json(module, "/ops/v1/stats")
            stats = ModuleStats(
                module_id=summary.module_id,
                module_type=summary.module_type,
                updated_at=self._now_iso(),
                data=stats_payload,
            )
        except Exception as exc:
            last_error = f"fetch stats failed: {exc}"

        summary = self._apply_summary_adjustments(summary, components, last_error)
        return summary, components, stats

    async def _get_json(self, module: UpstreamModuleSettings, path: str) -> Any:
        response = await self._authorized_request(module, "GET", path)
        response.raise_for_status()
        return response.json()

    async def _authorized_request(
        self,
        module: UpstreamModuleSettings,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        response = await self._http_client.request(
            method,
            f"{module.base_url.rstrip('/')}{path}",
            headers=await self._build_auth_headers(module),
            json=json_body,
            timeout=module.timeout_s,
        )
        if response.status_code != 401 or not self._module_uses_dynamic_auth(module):
            return response

        self._invalidate_module_access_token(module)
        return await self._http_client.request(
            method,
            f"{module.base_url.rstrip('/')}{path}",
            headers=await self._build_auth_headers(module),
            json=json_body,
            timeout=module.timeout_s,
        )

    async def _build_auth_headers(self, module: UpstreamModuleSettings) -> dict[str, str]:
        token = await self._get_access_token(module)
        if token is None:
            return {}
        return {"Authorization": f"Bearer {token}"}

    async def _get_access_token(self, module: UpstreamModuleSettings) -> str | None:
        if module.auth_token:
            return module.auth_token
        if not self._module_uses_dynamic_auth(module):
            return None

        now = datetime.now(UTC)
        session = self._module_auth_sessions.get(module.module_id)
        if session is not None and session.access_expires_at - timedelta(seconds=30) > now:
            return session.access_token

        if session is not None and session.refresh_expires_at - timedelta(seconds=30) > now:
            refreshed = await self._refresh_upstream_session(module, session.refresh_token)
            if refreshed is not None:
                self._module_auth_sessions[module.module_id] = refreshed
                return refreshed.access_token

        logged_in = await self._login_upstream(module)
        if logged_in is None:
            return None

        self._module_auth_sessions[module.module_id] = logged_in
        return logged_in.access_token

    def _module_uses_dynamic_auth(self, module: UpstreamModuleSettings) -> bool:
        return bool(module.auth_username and module.auth_password)

    def _invalidate_module_access_token(self, module: UpstreamModuleSettings) -> None:
        session = self._module_auth_sessions.get(module.module_id)
        if session is None:
            return
        self._module_auth_sessions[module.module_id] = _UpstreamAuthSession(
            access_token="",
            refresh_token=session.refresh_token,
            access_expires_at=datetime.now(UTC),
            refresh_expires_at=session.refresh_expires_at,
        )

    async def _login_upstream(
        self,
        module: UpstreamModuleSettings,
    ) -> _UpstreamAuthSession | None:
        if not self._module_uses_dynamic_auth(module):
            return None
        response = await self._http_client.post(
            f"{module.base_url.rstrip('/')}/api/v1/auth/login",
            json={
                "username": module.auth_username,
                "password": module.auth_password,
            },
            timeout=module.timeout_s,
        )
        response.raise_for_status()
        return self._build_auth_session(response.json())

    async def _refresh_upstream_session(
        self,
        module: UpstreamModuleSettings,
        refresh_token: str,
    ) -> _UpstreamAuthSession | None:
        response = await self._http_client.post(
            f"{module.base_url.rstrip('/')}/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
            timeout=module.timeout_s,
        )
        if response.status_code == 401:
            return None
        response.raise_for_status()
        return self._build_auth_session(response.json())

    def _build_auth_session(self, payload: dict[str, Any]) -> _UpstreamAuthSession:
        now = datetime.now(UTC)
        return _UpstreamAuthSession(
            access_token=str(payload["access_token"]),
            refresh_token=str(payload["refresh_token"]),
            access_expires_at=now + timedelta(seconds=int(payload.get("expires_in", 0))),
            refresh_expires_at=now + timedelta(seconds=int(payload.get("refresh_expires_in", 0))),
        )

    def _build_unreachable_snapshot(
        self,
        module: UpstreamModuleSettings,
        error: str,
    ) -> tuple[ModuleHealthSummary, list[ModuleComponent], ModuleStats | None]:
        checked_at = self._now_iso()
        summary = ModuleHealthSummary(
            module_id=module.module_id,
            module_type=module.module_type,
            display_name=module.display_name,
            online=False,
            health_status="offline",
            checked_at=checked_at,
            component_total=1,
            healthy_components=0,
            degraded_components=0,
            offline_components=1,
            last_error=error,
        )
        components = [
            ModuleComponent(
                module_id=module.module_id,
                component_id="ops_health_api",
                component_type="other",
                display_name="自观测健康接口",
                online=False,
                health_status="offline",
                checked_at=checked_at,
                endpoint=f"{module.base_url.rstrip('/')}/ops/v1/health",
                detail=error,
            )
        ]
        return summary, components, None

    def _apply_summary_adjustments(
        self,
        summary: ModuleHealthSummary,
        components: list[ModuleComponent],
        last_error: str | None,
    ) -> ModuleHealthSummary:
        now = datetime.now(UTC)
        checked_at = self._parse_datetime(summary.checked_at)
        stale_after_s = self._settings.alert_threshold.stale_after_s

        healthy_components = sum(1 for item in components if item.online and item.health_status == "healthy")
        degraded_components = sum(1 for item in components if item.online and item.health_status == "degraded")
        offline_components = sum(1 for item in components if (not item.online) or item.health_status == "offline")
        component_total = len(components)

        online = summary.online
        health_status = summary.health_status
        computed_last_error = last_error

        if checked_at is None:
            health_status = "degraded" if online else "offline"
            computed_last_error = computed_last_error or "invalid checked_at"
        elif (now - checked_at).total_seconds() > stale_after_s:
            health_status = "degraded" if online else "offline"
            computed_last_error = computed_last_error or f"stale snapshot > {stale_after_s}s"
        elif offline_components > 0:
            health_status = "offline"
            online = False
        elif degraded_components > 0 and health_status == "healthy":
            health_status = "degraded"
        elif last_error is not None and health_status == "healthy":
            health_status = "degraded"

        return summary.model_copy(
            update={
                "online": online,
                "health_status": health_status,
                "component_total": component_total,
                "healthy_components": healthy_components,
                "degraded_components": degraded_components,
                "offline_components": offline_components,
                "last_error": computed_last_error,
            }
        )

    async def _emit_transition_alerts(self, summary: ModuleHealthSummary) -> None:
        previous = self._last_states.get(summary.module_id)
        current = _ModuleState(online=summary.online, health_status=summary.health_status)
        self._last_states[summary.module_id] = current
        if previous is not None and previous == current:
            return

        alert: OpsAlertRecord | None = None
        payload = summary.model_dump()
        if not summary.online or summary.health_status == "offline":
            alert = await self._store.create_alert(
                module_id=summary.module_id,
                module_type=summary.module_type,
                alert_type="module_offline",
                severity="critical",
                title=f"{summary.display_name or summary.module_id} 离线",
                detail=summary.last_error or "module became offline",
                payload=payload,
                created_at=self._now_iso(),
            )
        elif summary.health_status == "degraded":
            alert = await self._store.create_alert(
                module_id=summary.module_id,
                module_type=summary.module_type,
                alert_type="module_degraded",
                severity="warning",
                title=f"{summary.display_name or summary.module_id} 降级",
                detail=summary.last_error or "module health degraded",
                payload=payload,
                created_at=self._now_iso(),
            )
        elif (
            previous is not None
            and self._settings.alert_threshold.emit_recovery_alert
            and (not previous.online or previous.health_status in {"offline", "degraded"})
        ):
            alert = await self._store.create_alert(
                module_id=summary.module_id,
                module_type=summary.module_type,
                alert_type="module_recovered",
                severity="info",
                title=f"{summary.display_name or summary.module_id} 恢复",
                detail="module recovered to healthy",
                payload=payload,
                created_at=self._now_iso(),
            )

        if alert is not None:
            await self._websocket_manager.broadcast({"type": "ops_alert", "data": alert.model_dump()})

    def _parse_datetime(self, value: str) -> datetime | None:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    async def _build_ws_url(self, module: UpstreamModuleSettings) -> str:
        parsed = urlsplit(module.base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        access_token = await self._get_access_token(module)
        query = urlencode({"token": access_token}) if access_token else ""
        path = module.ws_path if module.ws_path.startswith("/") else f"/{module.ws_path}"
        return urlunsplit((scheme, parsed.netloc, path, query, ""))

    def _now_iso(self) -> str:
        return datetime.now(UTC).isoformat()
