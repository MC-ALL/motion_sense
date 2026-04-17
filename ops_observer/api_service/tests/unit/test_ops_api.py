from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.observer_service import OpsObserverService
from app.services.ops_websocket_manager import OpsWebSocketManager
from app.services.sqlite_store import OpsSqliteStore
from app.settings import AlertThresholdSettings, RuntimeSettings, UpstreamModuleSettings


def build_settings(
    database_path: Path,
    *,
    ws_enabled: bool = False,
    auth_token: str | None = None,
    auth_username: str | None = None,
    auth_password: str | None = None,
    enforce_rest_auth: bool = False,
    enforce_ws_auth: bool = False,
    access_secret: str | None = None,
) -> RuntimeSettings:
    return RuntimeSettings(
        database_path=str(database_path),
        poll_interval_s=3600,
        ws_snapshot_interval_s=3600,
        upstream_ws_ping_interval_s=3600,
        upstream_ws_retry_interval_s=1,
        alert_threshold=AlertThresholdSettings(stale_after_s=120, emit_recovery_alert=True),
        auth={
            "enforce_rest": enforce_rest_auth,
            "enforce_ws": enforce_ws_auth,
            "issuer": "motion_sense_backend",
            "audience": "motion_sense_api",
            "jwt": {
                "access_secret": access_secret,
            },
        },
        upstream_modules=[
            UpstreamModuleSettings(
                module_id="gateway:gw-001",
                module_type="gateway",
                display_name="网关 gw-001",
                base_url="http://gateway.local",
                ws_enabled=ws_enabled,
                auth_token=auth_token,
                auth_username=auth_username,
                auth_password=auth_password,
            ),
            UpstreamModuleSettings(
                module_id="backend:api-main",
                module_type="backend",
                display_name="后台 API",
                base_url="http://backend.local",
                ws_enabled=ws_enabled,
                auth_token=auth_token,
                auth_username=auth_username,
                auth_password=auth_password,
            ),
        ],
    )


def build_access_token(
    *,
    secret: str,
    role: str = "admin",
    username: str = "ops-admin",
    expires_in_s: int = 900,
) -> str:
    now_s = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": username,
        "role": role,
        "gym_ids": [],
        "device_ids": [],
        "typ": "access",
        "iat": now_s,
        "exp": now_s + expires_in_s,
        "iss": "motion_sense_backend",
        "aud": "motion_sense_api",
        "jti": "ops-test-token",
    }
    encoded_header = _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    encoded_payload = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}"
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("utf-8")


def fresh_checked_at(seconds_ago: int = 0) -> str:
    return (datetime.now(UTC) - timedelta(seconds=seconds_ago)).isoformat()


def test_ops_health_and_detail(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "gateway.local":
            if request.url.path == "/ops/v1/health":
                return httpx.Response(
                    200,
                    json={
                        "module_id": "gateway:gw-001",
                        "module_type": "gateway",
                        "gateway_id": "gw-001",
                        "gym_id": "gym-gz-01",
                        "online": True,
                        "health_status": "healthy",
                        "checked_at": fresh_checked_at(5),
                        "component_total": 3,
                        "healthy_components": 3,
                        "degraded_components": 0,
                        "offline_components": 0,
                    },
                )
            if request.url.path == "/ops/v1/health/components":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "component_id": "edge_processor",
                            "component_type": "edge_processor",
                            "display_name": "边缘处理主服务",
                            "online": True,
                            "health_status": "healthy",
                            "checked_at": fresh_checked_at(5),
                            "detail": "running",
                        }
                    ],
                )
            if request.url.path == "/ops/v1/stats":
                return httpx.Response(
                    200,
                    json={
                        "module_id": "gateway:gw-001",
                        "module_type": "gateway",
                        "gateway_id": "gw-001",
                        "gym_id": "gym-gz-01",
                        "started_at": "2026-04-15T08:00:00+00:00",
                        "uptime_s": 3600,
                        "active_ops_ws_connections": 0,
                        "mqtt_events_received_total": 12,
                        "telemetry_events_total": 8,
                        "alert_events_total": 1,
                        "binding_events_total": 1,
                        "status_events_total": 2,
                        "generated_alerts_total": 1,
                        "generated_status_total": 2,
                        "command_polls_total": 5,
                        "commands_executed_total": 3,
                        "command_failures_total": 0,
                        "batch_upload_success_total": 4,
                        "batch_upload_failure_total": 0,
                        "last_batch_size": 2,
                        "health_report_success_total": 4,
                        "health_report_failure_total": 0,
                        "last_known_health_status": "healthy",
                        "batch_interval_s": 5,
                        "command_poll_interval_s": 5,
                        "health_interval_s": 15,
                        "replay_batch_size": 100,
                    },
                )
        if request.url.host == "backend.local":
            if request.url.path == "/ops/v1/health":
                return httpx.Response(
                    200,
                    json={
                        "module_id": "backend:api-main",
                        "module_type": "backend",
                        "online": True,
                        "health_status": "healthy",
                        "checked_at": fresh_checked_at(3),
                        "component_total": 4,
                        "healthy_components": 4,
                        "degraded_components": 0,
                        "offline_components": 0,
                    },
                )
            if request.url.path == "/ops/v1/health/components":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "component_id": "api_service",
                            "component_type": "api_service",
                            "display_name": "后台 API",
                            "online": True,
                            "health_status": "healthy",
                            "checked_at": fresh_checked_at(3),
                            "detail": "process alive",
                        }
                    ],
                )
            if request.url.path == "/ops/v1/stats":
                return httpx.Response(
                    200,
                    json={
                        "module_id": "backend:api-main",
                        "module_type": "backend",
                        "started_at": "2026-04-15T08:00:00+00:00",
                        "uptime_s": 3600,
                        "storage_backend": "memory",
                        "realtime_backend": "local",
                        "rest_auth_enabled": False,
                        "ws_auth_enabled": False,
                        "active_business_ws_connections": 0,
                        "active_ops_ws_connections": 0,
                        "ingest_batches_total": 6,
                        "ingest_items_total": 42,
                        "published_telemetry_total": 18,
                        "published_alert_total": 2,
                        "published_device_status_total": 3,
                        "config_commands_created_total": 2,
                        "command_results_reported_total": 2,
                        "command_result_failures_total": 0,
                        "last_known_health_status": "healthy",
                    },
                )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app = create_app(build_settings(tmp_path / "ops.sqlite3"), http_client=client)

    with TestClient(app) as test_client:
        response = test_client.get("/api/v1/ops/health")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["items"]) == 2
        assert payload["items"][0]["module_id"] == "backend:api-main"
        assert payload["items"][1]["module_id"] == "gateway:gw-001"

        detail_response = test_client.get("/api/v1/ops/health/gateway:gw-001")
        assert detail_response.status_code == 200
        detail_payload = detail_response.json()
        assert detail_payload["summary"]["display_name"] == "网关 gw-001"
        assert detail_payload["components"][0]["component_id"] == "edge_processor"
        assert detail_payload["stats"]["data"]["mqtt_events_received_total"] == 12

        stats_response = test_client.get("/api/v1/ops/stats")
        assert stats_response.status_code == 200
        assert len(stats_response.json()["items"]) == 2

        with test_client.websocket_connect("/api/ws/ops") as websocket:
            message = websocket.receive_json()
            assert message["type"] == "ops_snapshot"
            assert len(message["data"]["items"]) == 2
            websocket.send_json({"type": "ping"})
            assert websocket.receive_json() == {"type": "pong"}

    asyncio.run(client.aclose())


def test_ops_alert_close_flow(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "gateway.local":
            if request.url.path == "/ops/v1/health":
                return httpx.Response(
                    200,
                    json={
                        "module_id": "gateway:gw-001",
                        "module_type": "gateway",
                        "online": True,
                        "health_status": "healthy",
                        "checked_at": fresh_checked_at(5),
                        "component_total": 1,
                        "healthy_components": 1,
                        "degraded_components": 0,
                        "offline_components": 0,
                    },
                )
            if request.url.path == "/ops/v1/health/components":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "component_id": "edge_processor",
                            "component_type": "edge_processor",
                            "display_name": "边缘处理主服务",
                            "online": True,
                            "health_status": "healthy",
                            "checked_at": fresh_checked_at(5),
                        }
                    ],
                )
            if request.url.path == "/ops/v1/stats":
                return httpx.Response(200, json={"module_id": "gateway:gw-001", "module_type": "gateway"})
        if request.url.host == "backend.local":
            raise httpx.ConnectError("backend unavailable", request=request)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app = create_app(build_settings(tmp_path / "ops_alert.sqlite3"), http_client=client)

    with TestClient(app) as test_client:
        response = test_client.get("/api/v1/ops/alerts")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["items"]) == 1
        alert_id = payload["items"][0]["id"]
        assert payload["items"][0]["module_id"] == "backend:api-main"
        assert payload["items"][0]["severity"] == "critical"
        assert payload["items"][0]["alert_type"] == "module_offline"

        close_response = test_client.patch(f"/api/v1/ops/alerts/{alert_id}/close")
        assert close_response.status_code == 200
        close_payload = close_response.json()
        assert close_payload["status"] == "closed"
        assert close_payload["closed_at"] is not None

        closed_list = test_client.get("/api/v1/ops/alerts", params={"status": "closed"})
        assert closed_list.status_code == 200
        assert len(closed_list.json()["items"]) == 1

    asyncio.run(client.aclose())


def test_ops_observer_logs_in_before_polling_protected_backend(tmp_path: Path) -> None:
    requests_seen: list[tuple[str, str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(
            (
                request.method,
                f"{request.url.host}{request.url.path}",
                request.headers.get("Authorization"),
            )
        )
        if request.url.host == "gateway.local":
            if request.url.path == "/ops/v1/health":
                return httpx.Response(
                    200,
                    json={
                        "module_id": "gateway:gw-001",
                        "module_type": "gateway",
                        "online": True,
                        "health_status": "healthy",
                        "checked_at": fresh_checked_at(5),
                        "component_total": 1,
                        "healthy_components": 1,
                        "degraded_components": 0,
                        "offline_components": 0,
                    },
                )
            if request.url.path == "/ops/v1/health/components":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "component_id": "edge_processor",
                            "component_type": "edge_processor",
                            "display_name": "边缘处理主服务",
                            "online": True,
                            "health_status": "healthy",
                            "checked_at": fresh_checked_at(5),
                        }
                    ],
                )
            if request.url.path == "/ops/v1/stats":
                return httpx.Response(200, json={"module_id": "gateway:gw-001", "module_type": "gateway"})

        if request.url.host == "backend.local":
            if request.url.path == "/api/v1/auth/login":
                assert request.content == b'{"username":"ops_bot","password":"secret-123"}'
                return httpx.Response(
                    200,
                    json={
                        "access_token": "access-123",
                        "refresh_token": "refresh-123",
                        "token_type": "bearer",
                        "expires_in": 900,
                        "refresh_expires_in": 604800,
                        "user": {"username": "ops_bot", "role": "admin"},
                    },
                )
            if request.headers.get("Authorization") != "Bearer access-123":
                return httpx.Response(401, json={"detail": "missing bearer token"})
            if request.url.path == "/ops/v1/health":
                return httpx.Response(
                    200,
                    json={
                        "module_id": "backend:api-main",
                        "module_type": "backend",
                        "online": True,
                        "health_status": "healthy",
                        "checked_at": fresh_checked_at(3),
                        "component_total": 1,
                        "healthy_components": 1,
                        "degraded_components": 0,
                        "offline_components": 0,
                    },
                )
            if request.url.path == "/ops/v1/health/components":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "component_id": "api_service",
                            "component_type": "api_service",
                            "display_name": "后台 API",
                            "online": True,
                            "health_status": "healthy",
                            "checked_at": fresh_checked_at(3),
                        }
                    ],
                )
            if request.url.path == "/ops/v1/stats":
                return httpx.Response(
                    200,
                    json={"module_id": "backend:api-main", "module_type": "backend", "rest_auth_enabled": True},
                )

        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = build_settings(
        tmp_path / "ops_auth.sqlite3",
        auth_username="ops_bot",
        auth_password="secret-123",
    )
    app = create_app(settings, http_client=client)

    with TestClient(app) as test_client:
        response = test_client.get("/api/v1/ops/health")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["items"]) == 2
        assert any(
            method == "POST" and path == "backend.local/api/v1/auth/login"
            for method, path, _ in requests_seen
        )
        assert any(
            method == "GET" and path == "backend.local/ops/v1/health" and auth == "Bearer access-123"
            for method, path, auth in requests_seen
        )

    asyncio.run(client.aclose())


def test_upstream_ws_message_triggers_refresh(tmp_path: Path) -> None:
    settings = build_settings(tmp_path / "ops_ws.sqlite3", ws_enabled=True, auth_token="token-123")
    store = OpsSqliteStore(str(tmp_path / "ops_ws.sqlite3"))
    manager = OpsWebSocketManager()
    service = OpsObserverService(settings, store, manager, http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))))

    called: list[str] = []

    async def fake_refresh(module: UpstreamModuleSettings) -> None:
        called.append(f"refresh:{module.module_id}")

    async def fake_broadcast() -> None:
        called.append("broadcast")

    service.refresh_module = fake_refresh  # type: ignore[method-assign]
    service.broadcast_snapshot = fake_broadcast  # type: ignore[method-assign]

    asyncio.run(service._handle_upstream_ws_message(settings.upstream_modules[0], '{"type":"ops_snapshot","data":{}}'))

    assert called == ["refresh:gateway:gw-001", "broadcast"]
    assert asyncio.run(service._build_ws_url(settings.upstream_modules[0])) == "ws://gateway.local/ops/ws?token=token-123"

    asyncio.run(service._http_client.aclose())


def test_ops_api_requires_admin_bearer_token_when_enabled(tmp_path: Path) -> None:
    secret = "ops-observer-access-secret"
    admin_token = build_access_token(secret=secret, role="admin")
    teacher_token = build_access_token(secret=secret, role="teacher")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "gateway.local" and request.url.path.endswith("/ops/v1/health"):
            return httpx.Response(
                200,
                json={
                    "module_id": "gateway:gw-001",
                    "module_type": "gateway",
                    "online": True,
                    "health_status": "healthy",
                    "checked_at": fresh_checked_at(5),
                    "component_total": 0,
                    "healthy_components": 0,
                    "degraded_components": 0,
                    "offline_components": 0,
                },
            )
        if request.url.host == "gateway.local" and request.url.path.endswith("/ops/v1/health/components"):
            return httpx.Response(200, json=[])
        if request.url.host == "gateway.local" and request.url.path.endswith("/ops/v1/stats"):
            return httpx.Response(200, json={"module_id": "gateway:gw-001", "module_type": "gateway"})
        if request.url.host == "backend.local" and request.url.path.endswith("/ops/v1/health"):
            return httpx.Response(
                200,
                json={
                    "module_id": "backend:api-main",
                    "module_type": "backend",
                    "online": True,
                    "health_status": "healthy",
                    "checked_at": fresh_checked_at(4),
                    "component_total": 0,
                    "healthy_components": 0,
                    "degraded_components": 0,
                    "offline_components": 0,
                },
            )
        if request.url.host == "backend.local" and request.url.path.endswith("/ops/v1/health/components"):
            return httpx.Response(200, json=[])
        if request.url.host == "backend.local" and request.url.path.endswith("/ops/v1/stats"):
            return httpx.Response(200, json={"module_id": "backend:api-main", "module_type": "backend"})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app = create_app(
        build_settings(
            tmp_path / "ops_api_auth.sqlite3",
            enforce_rest_auth=True,
            access_secret=secret,
        ),
        http_client=client,
    )

    with TestClient(app) as test_client:
        assert test_client.get("/api/v1/ops/health").status_code == 401
        assert test_client.get(
            "/api/v1/ops/health",
            headers={"Authorization": "Bearer invalid-token"},
        ).status_code == 401
        assert test_client.get(
            "/api/v1/ops/health",
            headers={"Authorization": f"Bearer {teacher_token}"},
        ).status_code == 403

        response = test_client.get(
            "/api/v1/ops/health",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 2

    asyncio.run(client.aclose())


def test_ops_websocket_requires_admin_token_when_enabled(tmp_path: Path) -> None:
    secret = "ops-observer-access-secret"
    admin_token = build_access_token(secret=secret, role="admin")
    student_token = build_access_token(secret=secret, role="student")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "gateway.local" and request.url.path.endswith("/ops/v1/health"):
            return httpx.Response(
                200,
                json={
                    "module_id": "gateway:gw-001",
                    "module_type": "gateway",
                    "online": True,
                    "health_status": "healthy",
                    "checked_at": fresh_checked_at(5),
                    "component_total": 0,
                    "healthy_components": 0,
                    "degraded_components": 0,
                    "offline_components": 0,
                },
            )
        if request.url.host == "gateway.local" and request.url.path.endswith("/ops/v1/health/components"):
            return httpx.Response(200, json=[])
        if request.url.host == "gateway.local" and request.url.path.endswith("/ops/v1/stats"):
            return httpx.Response(200, json={"module_id": "gateway:gw-001", "module_type": "gateway"})
        if request.url.host == "backend.local" and request.url.path.endswith("/ops/v1/health"):
            return httpx.Response(
                200,
                json={
                    "module_id": "backend:api-main",
                    "module_type": "backend",
                    "online": True,
                    "health_status": "healthy",
                    "checked_at": fresh_checked_at(4),
                    "component_total": 0,
                    "healthy_components": 0,
                    "degraded_components": 0,
                    "offline_components": 0,
                },
            )
        if request.url.host == "backend.local" and request.url.path.endswith("/ops/v1/health/components"):
            return httpx.Response(200, json=[])
        if request.url.host == "backend.local" and request.url.path.endswith("/ops/v1/stats"):
            return httpx.Response(200, json={"module_id": "backend:api-main", "module_type": "backend"})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app = create_app(
        build_settings(
            tmp_path / "ops_ws_auth.sqlite3",
            enforce_ws_auth=True,
            access_secret=secret,
        ),
        http_client=client,
    )

    with TestClient(app) as test_client:
        for path in ("/api/ws/ops", "/api/ws/ops?token=invalid-token", f"/api/ws/ops?token={student_token}"):
            try:
                with test_client.websocket_connect(path) as websocket:
                    websocket.receive_json()
            except Exception:
                continue
            raise AssertionError(f"websocket should fail for path: {path}")

        with test_client.websocket_connect(f"/api/ws/ops?token={admin_token}") as websocket:
            message = websocket.receive_json()
            assert message["type"] == "ops_snapshot"

    asyncio.run(client.aclose())
