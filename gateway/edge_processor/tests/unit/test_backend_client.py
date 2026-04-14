import asyncio
from datetime import UTC, datetime

import httpx

from app.models.device_command import GatewayCommandResultRequest
from app.services.backend_client import BackendClient
from app.settings import RuntimeSettings


def test_backend_client_fetches_and_reports_gateway_commands() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)

        if request.method == "GET" and request.url.path == "/api/v1/gateway/gw-test-001/commands/pending":
            return httpx.Response(
                200,
                json={
                    "gateway_id": "gw-test-001",
                    "items": [
                        {
                            "command_id": "cmd-001",
                            "gateway_id": "gw-test-001",
                            "device_id": "env-a",
                            "gym_id": "gym-gz-01",
                            "device_type": "env",
                            "topic": "gym/gym-gz-01/env/env-a/config",
                            "qos": 1,
                            "retain": False,
                            "payload": {"telemetry_interval_s": 20},
                            "status": "pending",
                            "attempt_count": 1,
                            "max_attempts": 3,
                            "retry_backoff_s": 5,
                            "last_attempt_at": "2026-04-15T08:00:01Z",
                            "next_retry_at": "2026-04-15T08:00:00Z",
                            "leased_until": "2026-04-15T08:00:16Z",
                            "expires_at": "2026-04-15T08:05:00Z",
                            "created_at": "2026-04-15T08:00:00Z",
                            "updated_at": "2026-04-15T08:00:00Z",
                            "result_detail": None,
                            "result_payload": {},
                        }
                    ],
                },
            )

        if request.method == "POST" and request.url.path == "/api/v1/gateway/gw-test-001/commands/cmd-001/result":
            return httpx.Response(
                200,
                json={
                    "command_id": "cmd-001",
                    "gateway_id": "gw-test-001",
                    "device_id": "env-a",
                    "gym_id": "gym-gz-01",
                    "device_type": "env",
                    "topic": "gym/gym-gz-01/env/env-a/config",
                    "qos": 1,
                    "retain": False,
                    "payload": {"telemetry_interval_s": 20},
                    "status": "succeeded",
                    "attempt_count": 1,
                    "max_attempts": 3,
                    "retry_backoff_s": 5,
                    "last_attempt_at": "2026-04-15T08:00:01Z",
                    "next_retry_at": None,
                    "leased_until": None,
                    "expires_at": "2026-04-15T08:05:00Z",
                    "created_at": "2026-04-15T08:00:00Z",
                    "updated_at": "2026-04-15T08:01:00Z",
                    "result_detail": "applied",
                    "result_payload": {"applied": True},
                },
            )

        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    settings = RuntimeSettings(gateway_id="gw-test-001")
    client = BackendClient(settings)
    original_client = client._client
    client._client = httpx.AsyncClient(
        base_url=settings.backend.base_url,
        timeout=settings.backend.request_timeout_s,
        transport=transport,
    )

    async def scenario() -> None:
        await original_client.aclose()
        commands = await client.fetch_pending_commands()
        assert len(commands) == 1
        assert commands[0].command_id == "cmd-001"
        assert commands[0].attempt_count == 1
        assert commands[0].leased_until is not None

        result = GatewayCommandResultRequest(
            status="succeeded",
            reported_at=datetime.now(UTC).isoformat(),
            detail="applied",
            result_payload={"applied": True},
        )
        updated = await client.report_command_result(command_id="cmd-001", result=result)
        assert updated.status == "succeeded"
        assert updated.result_payload["applied"] is True
        await client.close()

    asyncio.run(scenario())

    assert requests[0].url.path == "/api/v1/gateway/gw-test-001/commands/pending"
    assert requests[1].url.path == "/api/v1/gateway/gw-test-001/commands/cmd-001/result"
