from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import build_app
from app.models.system_health import GatewayHealthComponentInput, GatewayHealthReportRequest
from app.services.runner import EdgeProcessorRunner
from app.settings import RuntimeSettings


async def _noop_start(self: EdgeProcessorRunner) -> None:
    """Replace runner startup during API tests.

    :param self: Runner instance owned by the FastAPI app.
    :return: None.
    """
    return None


async def _noop_stop(self: EdgeProcessorRunner) -> None:
    """Replace runner shutdown during API tests.

    :param self: Runner instance owned by the FastAPI app.
    :return: None.
    """
    return None


def _sample_report() -> GatewayHealthReportRequest:
    """Build a representative gateway health report snapshot.

    :return: Health report containing healthy and offline components for ops
        endpoint assertions.
    """
    return GatewayHealthReportRequest(
        gateway_id="gw-test-001",
        gym_id="gym-gz-01",
        reported_at="2026-04-15T10:00:00Z",
        components=[
            GatewayHealthComponentInput(
                component_id="gateway_api",
                component_type="gateway_api",
                display_name="网关 API",
                online=True,
                health_status="healthy",
                checked_at="2026-04-15T10:00:00Z",
                endpoint="http://127.0.0.1:8080/healthz",
                latency_ms=5,
            ),
            GatewayHealthComponentInput(
                component_id="edge_processor",
                component_type="edge_processor",
                display_name="边缘处理服务",
                online=True,
                health_status="healthy",
                checked_at="2026-04-15T10:00:00Z",
                detail="process alive",
            ),
            GatewayHealthComponentInput(
                component_id="mqtt_broker",
                component_type="mqtt_broker",
                display_name="Mosquitto",
                online=False,
                health_status="offline",
                checked_at="2026-04-15T10:00:00Z",
                detail="connection refused",
            ),
        ],
    )


def test_gateway_ops_endpoints_return_latest_snapshot(monkeypatch) -> None:
    """Verify ops REST endpoints expose latest health and counter state.

    :param monkeypatch: Pytest fixture used to disable runner background
        startup and shutdown.
    :return: None. Assertions validate health summary, component list, and
        stats payload.
    """
    monkeypatch.setattr(EdgeProcessorRunner, "start", _noop_start)
    monkeypatch.setattr(EdgeProcessorRunner, "stop", _noop_stop)

    app = build_app(RuntimeSettings(gateway_id="gw-test-001", gym_id="gym-gz-01"))
    app.state.runner._latest_health_report = _sample_report()
    app.state.runner._last_health_checked_at = "2026-04-15T10:00:00Z"
    app.state.runner._health_check_success_total = 1
    app.state.runner._batch_upload_success_total = 2
    app.state.runner._last_batch_size = 10
    app.state.runner._mqtt_events_received_total = 12
    app.state.runner._telemetry_events_total = 7

    with TestClient(app) as client:
        summary_response = client.get("/ops/v1/health")
        assert summary_response.status_code == 200
        assert summary_response.json()["module_id"] == "gateway:gw-test-001"
        assert summary_response.json()["health_status"] == "offline"
        assert summary_response.json()["offline_components"] == 1

        components_response = client.get("/ops/v1/health/components")
        assert components_response.status_code == 200
        assert len(components_response.json()) == 3

        stats_response = client.get("/ops/v1/stats")
        assert stats_response.status_code == 200
        payload = stats_response.json()
        assert payload["module_id"] == "gateway:gw-test-001"
        assert payload["health_check_success_total"] == 1
        assert payload["batch_upload_success_total"] == 2
        assert payload["last_batch_size"] == 10
        assert payload["mqtt_events_received_total"] == 12
        assert payload["telemetry_events_total"] == 7


def test_gateway_ops_websocket_ping_pong(monkeypatch) -> None:
    """Verify ops WebSocket sends an initial snapshot and responds to ping.

    :param monkeypatch: Pytest fixture used to disable runner background
        startup and shutdown.
    :return: None. Assertions validate the snapshot envelope and pong reply.
    """
    monkeypatch.setattr(EdgeProcessorRunner, "start", _noop_start)
    monkeypatch.setattr(EdgeProcessorRunner, "stop", _noop_stop)

    app = build_app(RuntimeSettings(gateway_id="gw-test-001", gym_id="gym-gz-01"))
    app.state.runner._latest_health_report = _sample_report()

    with TestClient(app) as client:
        with client.websocket_connect("/ops/ws") as websocket:
            initial = websocket.receive_json()
            assert initial["type"] == "ops_snapshot"
            assert initial["data"]["module_id"] == "gateway:gw-test-001"

            websocket.send_json({"type": "ping"})
            assert websocket.receive_json() == {"type": "pong"}


def test_gateway_ops_rest_requires_token_when_enabled(monkeypatch) -> None:
    """Verify REST ops endpoints enforce bearer token authentication.

    :param monkeypatch: Pytest fixture used to disable runner background
        startup and shutdown.
    :return: None. Assertions cover missing, invalid, and valid token cases.
    """
    monkeypatch.setattr(EdgeProcessorRunner, "start", _noop_start)
    monkeypatch.setattr(EdgeProcessorRunner, "stop", _noop_stop)

    app = build_app(
        RuntimeSettings(
            gateway_id="gw-test-001",
            gym_id="gym-gz-01",
            ops_auth={
                "enforce_rest": True,
                "token": "ops-token-123",
            },
        )
    )
    app.state.runner._latest_health_report = _sample_report()

    with TestClient(app) as client:
        assert client.get("/ops/v1/health").status_code == 401
        assert client.get(
            "/ops/v1/health",
            headers={"Authorization": "Bearer invalid-token"},
        ).status_code == 403

        response = client.get(
            "/ops/v1/health",
            headers={"Authorization": "Bearer ops-token-123"},
        )
        assert response.status_code == 200
        assert response.json()["module_id"] == "gateway:gw-test-001"


def test_gateway_ops_websocket_requires_token_when_enabled(monkeypatch) -> None:
    """Verify ops WebSocket enforces token authentication.

    :param monkeypatch: Pytest fixture used to disable runner background
        startup and shutdown.
    :return: None. Assertions cover missing, invalid, and valid token cases.
    """
    monkeypatch.setattr(EdgeProcessorRunner, "start", _noop_start)
    monkeypatch.setattr(EdgeProcessorRunner, "stop", _noop_stop)

    app = build_app(
        RuntimeSettings(
            gateway_id="gw-test-001",
            gym_id="gym-gz-01",
            ops_auth={
                "enforce_ws": True,
                "token": "ops-token-123",
            },
        )
    )
    app.state.runner._latest_health_report = _sample_report()

    with TestClient(app) as client:
        try:
            with client.websocket_connect("/ops/ws") as websocket:
                websocket.receive_json()
        except Exception:
            pass
        else:
            raise AssertionError("websocket without token should fail")

        try:
            with client.websocket_connect("/ops/ws?token=invalid-token") as websocket:
                websocket.receive_json()
        except Exception:
            pass
        else:
            raise AssertionError("websocket with invalid token should fail")

        with client.websocket_connect("/ops/ws?token=ops-token-123") as websocket:
            initial = websocket.receive_json()
            assert initial["type"] == "ops_snapshot"
