from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from app.services.auth_service import generate_password_hash
from app.settings import RuntimeSettings


def test_websocket_ping_pong_and_subscription() -> None:
    settings = RuntimeSettings(realtime_telemetry_flush_interval_ms=10)

    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/api/ws") as websocket:
            websocket.send_json({"type": "ping"})
            assert websocket.receive_json() == {"type": "pong"}

            websocket.send_json(
                {"type": "subscribe", "data": {"device_ids": ["eq-002"]}}
            )

            ingest_response = client.post(
                "/api/v1/ingest/batch",
                json={
                    "gateway_id": "gw-001",
                    "sent_at": "2026-04-14T15:30:00Z",
                    "items": [
                        {
                            "kind": "telemetry",
                            "topic": "gym/gym-gz-01/equipment/eq-002/telemetry",
                            "payload": {
                                "ts": 1712345680,
                                "device_id": "eq-002",
                                "power_w": 420.0,
                            },
                        }
                    ],
                },
            )

            assert ingest_response.status_code == 200
            pushed = websocket.receive_json()
            assert pushed["type"] == "telemetry"
            assert pushed["data"]["device_id"] == "eq-002"
            assert pushed["data"]["power_w"] == 420.0


def test_websocket_coalesces_realtime_telemetry_by_device() -> None:
    settings = RuntimeSettings(
        realtime_backend="local",
        realtime_telemetry_flush_interval_ms=10,
    )

    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/api/ws") as websocket:
            response = client.post(
                "/api/v1/ingest/batch",
                json={
                    "gateway_id": "gw-001",
                    "sent_at": "2026-04-14T15:30:00Z",
                    "items": [
                        {
                            "kind": "telemetry",
                            "topic": "gym/gym-gz-01/equipment/eq-002/telemetry",
                            "payload": {"ts": 1712345680, "power_w": 420.0},
                        },
                        {
                            "kind": "telemetry",
                            "topic": "gym/gym-gz-01/equipment/eq-002/telemetry",
                            "payload": {"ts": 1712345681, "power_w": 430.0},
                        },
                    ],
                },
            )

            assert response.status_code == 200
            pushed = websocket.receive_json()
            assert pushed["type"] == "telemetry"
            assert pushed["data"]["device_id"] == "eq-002"
            assert pushed["data"]["power_w"] == 430.0


def test_websocket_alert_broadcast_in_local_realtime_mode() -> None:
    settings = RuntimeSettings(realtime_backend="local")

    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/api/ws") as websocket:
            response = client.post(
                "/api/v1/ingest/batch",
                json={
                    "gateway_id": "gw-001",
                    "sent_at": "2026-04-14T16:30:00Z",
                    "items": [
                        {
                            "kind": "alert",
                            "topic": "gym/gym-gz-01/wristband/wb-009/alert",
                            "payload": {
                                "ts": 1712349000,
                                "code": "FALL_DETECTED",
                                "level": "critical",
                                "message": "fall detected",
                                "priority": "P0",
                            },
                        }
                    ],
                },
            )

            assert response.status_code == 200
            pushed = websocket.receive_json()
            assert pushed["type"] == "alert"
            assert pushed["data"]["device_id"] == "wb-009"
            assert pushed["data"]["code"] == "FALL_DETECTED"


def test_websocket_receives_device_registry_events_in_local_realtime_mode() -> None:
    settings = RuntimeSettings(realtime_backend="local")

    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/api/ws") as websocket:
            create_response = client.post(
                "/api/v1/devices",
                json={
                    "gym_id": "gym-gz-01",
                    "device_type": "equipment",
                    "device_id": "eq-101",
                    "gateway_id": "gw-001",
                    "display_name": "测试设备 101",
                },
            )
            assert create_response.status_code == 200

            created_message = websocket.receive_json()
            assert created_message["type"] == "device_upsert"
            assert created_message["data"]["device_id"] == "eq-101"
            assert created_message["data"]["display_name"] == "测试设备 101"

            update_response = client.patch(
                "/api/v1/devices/eq-101",
                json={
                    "display_name": "测试设备 101 Pro",
                    "location": "三楼测试区",
                },
            )
            assert update_response.status_code == 200

            updated_message = websocket.receive_json()
            assert updated_message["type"] == "device_upsert"
            assert updated_message["data"]["device_id"] == "eq-101"
            assert updated_message["data"]["display_name"] == "测试设备 101 Pro"
            assert updated_message["data"]["location"] == "三楼测试区"

            delete_response = client.delete("/api/v1/devices/eq-101")
            assert delete_response.status_code == 200

            deleted_message = websocket.receive_json()
            assert deleted_message == {
                "type": "device_delete",
                "data": {
                    "device_id": "eq-101",
                    "device_type": "equipment",
                    "gym_id": "gym-gz-01",
                },
            }


def test_websocket_receives_acknowledged_alert_update_in_local_realtime_mode() -> None:
    settings = RuntimeSettings(realtime_backend="local")

    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/api/ws") as websocket:
            create_response = client.post(
                "/api/v1/ingest/batch",
                json={
                    "gateway_id": "gw-001",
                    "sent_at": "2026-04-22T10:00:00Z",
                    "items": [
                        {
                            "kind": "alert",
                            "topic": "gym/gym-gz-01/wristband/wb-010/alert",
                            "payload": {
                                "ts": 1713770400,
                                "code": "HR_HIGH",
                                "level": "warning",
                                "message": "high heart rate",
                                "priority": "P0",
                            },
                        }
                    ],
                },
            )
            assert create_response.status_code == 200

            created_message = websocket.receive_json()
            assert created_message["type"] == "alert"
            assert created_message["data"]["device_id"] == "wb-010"
            assert created_message["data"]["is_ack"] is False
            alert_id = created_message["data"]["id"]

            ack_response = client.patch(f"/api/v1/alerts/{alert_id}/ack")
            assert ack_response.status_code == 200

            updated_message = websocket.receive_json()
            assert updated_message["type"] == "alert"
            assert updated_message["data"]["id"] == alert_id
            assert updated_message["data"]["is_ack"] is True


def test_websocket_receives_ai_report_updates_in_local_realtime_mode() -> None:
    settings = RuntimeSettings(realtime_backend="local")

    with TestClient(create_app(settings)) as client:
        create_user_response = client.post(
            "/api/v1/users",
            json={
                "username": "student_ai_ws",
                "password": "student123",
                "role": "student",
                "gym_ids": ["gym-gz-01"],
                "device_ids": ["wb-001"],
            },
        )
        assert create_user_response.status_code == 201

        with client.websocket_connect("/api/ws") as websocket:
            analyze_response = client.post(
                "/api/v1/ai/analyze",
                json={
                    "user_id": "student_ai_ws",
                    "start": "2026-04-20T00:00:00Z",
                    "end": "2026-04-20T23:59:59Z",
                },
            )
            assert analyze_response.status_code == 201
            created_report_id = analyze_response.json()["report_id"]

            queued_message = websocket.receive_json()
            assert queued_message["type"] == "ai_report"
            assert queued_message["data"]["report_id"] == created_report_id
            assert queued_message["data"]["status"] == "queued"

            generating_message = websocket.receive_json()
            assert generating_message["type"] == "ai_report"
            assert generating_message["data"]["report_id"] == created_report_id
            assert generating_message["data"]["status"] == "generating"

            completed_message = websocket.receive_json()
            assert completed_message["type"] == "ai_report"
            assert completed_message["data"]["report_id"] == created_report_id
            assert completed_message["data"]["status"] == "completed"
            assert completed_message["data"]["summary_title"] == "student_ai_ws 训练分析报告"


def test_websocket_receives_binding_events_without_marking_device_online() -> None:
    settings = RuntimeSettings(realtime_backend="local")

    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/api/ws") as websocket:
            bind_response = client.post(
                "/api/v1/ingest/batch",
                json={
                    "gateway_id": "gw-001",
                    "sent_at": "2026-04-22T11:00:00Z",
                    "items": [
                        {
                            "kind": "binding",
                            "topic": "gym/gym-gz-01/wristband/wb-020/binding",
                            "payload": {
                                "ts": 1713774000,
                                "wristband_id": "wb-020",
                                "equipment_id": "eq-020",
                                "action": "bind",
                                "reason": "ble_connected",
                            },
                        }
                    ],
                },
            )
            assert bind_response.status_code == 200

            bind_message = websocket.receive_json()
            assert bind_message["type"] == "binding_upsert"
            assert bind_message["data"]["wristband_id"] == "wb-020"
            assert bind_message["data"]["equipment_id"] == "eq-020"
            assert bind_message["data"]["status"] == "registered"

            wristband_detail = client.get("/api/v1/devices/wb-020")
            assert wristband_detail.status_code == 200
            assert wristband_detail.json()["online"] is False
            assert wristband_detail.json().get("last_seen_ts") is None
            assert wristband_detail.json()["last_payload"]["current_equipment_id"] == "eq-020"

            unbind_response = client.post(
                "/api/v1/ingest/batch",
                json={
                    "gateway_id": "gw-001",
                    "sent_at": "2026-04-22T11:05:00Z",
                    "items": [
                        {
                            "kind": "binding",
                            "topic": "gym/gym-gz-01/wristband/wb-020/binding",
                            "payload": {
                                "ts": 1713774300,
                                "wristband_id": "wb-020",
                                "equipment_id": "eq-020",
                                "action": "unbind",
                                "reason": "exercise_completed",
                            },
                        }
                    ],
                },
            )
            assert unbind_response.status_code == 200

            unbind_message = websocket.receive_json()
            assert unbind_message["type"] == "binding_remove"
            assert unbind_message["data"]["wristband_id"] == "wb-020"
            assert unbind_message["data"]["equipment_id"] == "eq-020"
            assert unbind_message["data"]["status"] == "registered"

            wristband_detail_after_unbind = client.get("/api/v1/devices/wb-020")
            assert wristband_detail_after_unbind.status_code == 200
            assert wristband_detail_after_unbind.json()["online"] is False
            assert wristband_detail_after_unbind.json().get("last_seen_ts") is None
            assert wristband_detail_after_unbind.json()["last_payload"]["current_equipment_id"] is None


def test_websocket_requires_token_when_enabled() -> None:
    settings = RuntimeSettings(
        auth={
            "enforce_ws": True,
            "admin": {
                "username": "admin",
                "password_hash": generate_password_hash("admin123"),
            },
            "jwt": {
                "access_secret": "access-secret-for-ws-tests",
                "refresh_secret": "refresh-secret-for-ws-tests",
            },
        }
    )

    with TestClient(create_app(settings)) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/ws"):
                pass

        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert login.status_code == 200
        access_token = login.json()["access_token"]

        with client.websocket_connect(f"/api/ws?token={access_token}") as websocket:
            websocket.send_json({"type": "ping"})
            assert websocket.receive_json() == {"type": "pong"}
