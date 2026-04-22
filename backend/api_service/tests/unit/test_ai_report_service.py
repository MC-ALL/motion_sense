from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import patch

from app.models.ai import AiReportDetail
from app.services.ai_report_service import AiReportService
from app.services.auth_service import generate_password_hash
from app.services.realtime_service import RealtimeService
from app.services.websocket_manager import WebSocketManager
from app.models.workout import WorkoutSessionMetrics, WorkoutSessionSegment
from app.settings import RuntimeSettings
from app.storage.memory_store import EventStore


async def _wait_for_report_status(
    store: EventStore,
    report_id: str,
    expected_status: str,
    *,
    timeout_s: float = 1.0,
) -> AiReportDetail:
    async def poll() -> AiReportDetail:
        while True:
            report = await store.get_ai_report(report_id=report_id)
            if report is not None and report.status == expected_status:
                return report
            await asyncio.sleep(0.01)

    return await asyncio.wait_for(poll(), timeout=timeout_s)


def _create_service(settings: RuntimeSettings, store: EventStore) -> AiReportService:
    return AiReportService(settings, store, RealtimeService(settings, WebSocketManager()))


class _FakeRedisBroker:
    def __init__(self) -> None:
        self._pubsubs: list[_FakePubSub] = []

    def register(self, pubsub: "_FakePubSub") -> None:
        self._pubsubs.append(pubsub)

    def unregister(self, pubsub: "_FakePubSub") -> None:
        if pubsub in self._pubsubs:
            self._pubsubs.remove(pubsub)

    async def publish(self, channel: str, message: str) -> None:
        for pubsub in list(self._pubsubs):
            await pubsub.push(channel=channel, message=message)


class _FakePubSub:
    def __init__(self, broker: _FakeRedisBroker) -> None:
        self._broker = broker
        self._queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
        self._channels: set[str] = set()
        self._closed = False
        self._broker.register(self)

    async def subscribe(self, channel: str) -> None:
        self._channels.add(channel)

    async def listen(self):  # type: ignore[no-untyped-def]
        while not self._closed:
            item = await self._queue.get()
            if item.get("type") == "__close__":
                break
            yield item

    async def push(self, *, channel: str, message: str) -> None:
        if self._closed or channel not in self._channels:
            return
        await self._queue.put({"type": "message", "channel": channel, "data": message})

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._broker.unregister(self)
        await self._queue.put({"type": "__close__", "data": ""})


class _FakeRedis:
    def __init__(self, broker: _FakeRedisBroker) -> None:
        self._broker = broker
        self.published_messages: list[tuple[str, str]] = []
        self.closed = False

    async def ping(self) -> bool:
        return True

    async def publish(self, channel: str, message: str) -> int:
        self.published_messages.append((channel, message))
        await self._broker.publish(channel, message)
        return 1

    def pubsub(self) -> _FakePubSub:
        return _FakePubSub(self._broker)

    async def aclose(self) -> None:
        self.closed = True


def test_ai_report_service_completes_queued_report_with_builtin_generator() -> None:
    async def scenario() -> None:
        store = EventStore()
        await store.initialize()
        await store.create_user(
            username="student_ai_service",
            password_hash=generate_password_hash("student123"),
            role="student",
            gym_ids=["gym-gz-01"],
            device_ids=["wb-001", "eq-001"],
        )
        await store.create_workout_session(
            username="student_ai_service",
            wristband_id="wb-001",
            gym_id="gym-gz-01",
            status="completed",
            source="manual",
            started_at="2026-04-20T08:00:00Z",
            ended_at="2026-04-20T08:30:00Z",
            equipment_ids=["eq-001"],
            segments=[
                WorkoutSessionSegment(
                    equipment_id="eq-001",
                    started_at="2026-04-20T08:00:00Z",
                    ended_at="2026-04-20T08:30:00Z",
                    duration_s=1800,
                    rep_count=36,
                    energy_wh=16.5,
                )
            ],
            metrics=WorkoutSessionMetrics(
                avg_heart_rate=132.5,
                max_heart_rate=158,
                total_steps=3600,
                total_rep_count=36,
                total_energy_wh=16.5,
                alert_count=0,
            ),
            notes="ai service test session",
        )
        report = await store.create_ai_report(
            user_id="student_ai_service",
            status="queued",
            start="2026-04-20T00:00:00Z",
            end="2026-04-20T23:59:59Z",
            summary_title="student_ai_service 训练分析待生成",
            summary="报告已入队，等待后续 AI 生成流程写入正式内容。",
            insights=[],
            recommendations=[],
            evidence_session_ids=[],
            raw_markdown=None,
            error_message=None,
        )

        service = _create_service(RuntimeSettings(), store)
        completed = await service.process_report(report.report_id)

        assert completed is not None
        assert completed.status == "completed"
        assert completed.summary_title == "student_ai_service 训练分析报告"
        assert completed.summary is not None and "累计时长" in completed.summary
        assert completed.finished_at is not None
        assert completed.error_message is None
        assert completed.evidence_session_ids
        assert completed.insights
        assert completed.recommendations
        assert completed.raw_markdown is not None and "# student_ai_service 训练分析报告" in completed.raw_markdown

        await store.close()

    asyncio.run(scenario())


def test_ai_report_service_processes_report_immediately_after_enqueue() -> None:
    async def scenario() -> None:
        store = EventStore()
        await store.initialize()
        await store.create_user(
            username="student_ai_queue",
            password_hash=generate_password_hash("student123"),
            role="student",
            gym_ids=["gym-gz-01"],
            device_ids=["wb-queue-001"],
        )
        service = _create_service(RuntimeSettings(), store)
        await service.start()

        try:
            report = await store.create_ai_report(
                user_id="student_ai_queue",
                status="queued",
                start="2026-04-20T00:00:00Z",
                end="2026-04-20T23:59:59Z",
                summary_title="student_ai_queue 训练分析待生成",
                summary="报告已入队，等待后续 AI 生成流程写入正式内容。",
                insights=[],
                recommendations=[],
                evidence_session_ids=[],
                raw_markdown=None,
                error_message=None,
            )
            service.enqueue_report(report.report_id)

            completed = await _wait_for_report_status(store, report.report_id, "completed")
            assert completed.finished_at is not None
        finally:
            await service.stop()
            await store.close()

    asyncio.run(scenario())


def test_ai_report_service_recovers_generating_report_on_start() -> None:
    async def scenario() -> None:
        store = EventStore()
        await store.initialize()
        await store.create_user(
            username="student_ai_recover",
            password_hash=generate_password_hash("student123"),
            role="student",
            gym_ids=["gym-gz-01"],
            device_ids=["wb-recover-001"],
        )
        report = await store.create_ai_report(
            user_id="student_ai_recover",
            status="generating",
            start="2026-04-20T00:00:00Z",
            end="2026-04-20T23:59:59Z",
            summary_title="student_ai_recover 训练分析待生成",
            summary="报告在重启前停留在 generating。",
            insights=[],
            recommendations=[],
            evidence_session_ids=[],
            raw_markdown=None,
            error_message=None,
        )

        service = _create_service(RuntimeSettings(), store)
        await service.start()
        try:
            completed = await _wait_for_report_status(store, report.report_id, "completed")
            assert completed.summary_title == "student_ai_recover 训练分析报告"
        finally:
            await service.stop()
            await store.close()

    asyncio.run(scenario())


def test_ai_report_service_claims_queued_report_once_under_race() -> None:
    async def scenario() -> None:
        store = EventStore()
        await store.initialize()
        await store.create_user(
            username="student_ai_claim",
            password_hash=generate_password_hash("student123"),
            role="student",
            gym_ids=["gym-gz-01"],
            device_ids=["wb-claim-001"],
        )
        report = await store.create_ai_report(
            user_id="student_ai_claim",
            status="queued",
            start="2026-04-20T00:00:00Z",
            end="2026-04-20T23:59:59Z",
            summary_title="student_ai_claim 训练分析待生成",
            summary="报告已入队，等待后续 AI 生成流程写入正式内容。",
            insights=[],
            recommendations=[],
            evidence_session_ids=[],
            raw_markdown=None,
            error_message=None,
        )

        service = _create_service(RuntimeSettings(), store)
        call_count = 0

        async def fake_build_completed_payload(report_detail: AiReportDetail) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            return {
                "summary_title": f"{report_detail.user_id} 训练分析报告",
                "summary": "测试摘要",
                "insights": ["测试观察"],
                "recommendations": ["测试建议"],
                "evidence_session_ids": [],
                "raw_markdown": "# 测试报告",
            }

        with patch.object(service, "_build_completed_payload", side_effect=fake_build_completed_payload):
            result_a, result_b = await asyncio.gather(
                service.process_report(report.report_id),
                service.process_report(report.report_id),
            )

        completed = await store.get_ai_report(report_id=report.report_id)
        assert call_count == 1
        assert completed is not None and completed.status == "completed"
        assert {result_a.status if result_a is not None else None, result_b.status if result_b is not None else None} <= {
            "generating",
            "completed",
        }

        await store.close()

    asyncio.run(scenario())


def test_ai_report_service_redis_wakeup_can_notify_another_instance() -> None:
    async def scenario() -> None:
        store = EventStore()
        await store.initialize()
        await store.create_user(
            username="student_ai_redis",
            password_hash=generate_password_hash("student123"),
            role="student",
            gym_ids=["gym-gz-01"],
            device_ids=["wb-redis-001"],
        )

        broker = _FakeRedisBroker()
        redis_clients: list[_FakeRedis] = []

        def fake_from_url(*args, **kwargs):  # type: ignore[no-untyped-def]
            client = _FakeRedis(broker)
            redis_clients.append(client)
            return client

        settings = RuntimeSettings(
            ai={
                "auto_process": True,
                "wakeup_backend": "redis",
                "wakeup_channel": "motion_sense:test_ai_report_wakeup",
            }
        )
        service_a = _create_service(settings, store)
        service_b = _create_service(settings, store)

        with patch("app.services.ai_report_service.Redis.from_url", side_effect=fake_from_url):
            await service_a.start()
            await service_b.start()
            await asyncio.sleep(0.05)
            report = await store.create_ai_report(
                user_id="student_ai_redis",
                status="queued",
                start="2026-04-20T00:00:00Z",
                end="2026-04-20T23:59:59Z",
                summary_title="student_ai_redis 训练分析待生成",
                summary="报告已入队，等待后续 AI 生成流程写入正式内容。",
                insights=[],
                recommendations=[],
                evidence_session_ids=[],
                raw_markdown=None,
                error_message=None,
            )

            service_a.enqueue_report = lambda report_id: None  # type: ignore[method-assign]
            try:
                await service_a.wakeup_report(report.report_id)
                completed = await _wait_for_report_status(store, report.report_id, "completed")
                assert completed.finished_at is not None
                assert len(redis_clients) == 2
                assert redis_clients[0].published_messages == [
                    (
                        "motion_sense:test_ai_report_wakeup",
                        json.dumps({"report_id": report.report_id}, separators=(",", ":"), ensure_ascii=True),
                    )
                ]
            finally:
                await service_b.stop()
                await service_a.stop()
                await store.close()

    asyncio.run(scenario())


def test_ai_report_service_marks_report_failed_when_openai_provider_is_misconfigured() -> None:
    async def scenario() -> None:
        store = EventStore()
        await store.initialize()
        await store.create_user(
            username="student_ai_provider",
            password_hash=generate_password_hash("student123"),
            role="student",
            gym_ids=["gym-gz-01"],
            device_ids=["wb-002"],
        )
        report = await store.create_ai_report(
            user_id="student_ai_provider",
            status="queued",
            start="2026-04-20T00:00:00Z",
            end="2026-04-20T23:59:59Z",
            summary_title="student_ai_provider 训练分析待生成",
            summary="报告已入队，等待后续 AI 生成流程写入正式内容。",
            insights=[],
            recommendations=[],
            evidence_session_ids=[],
            raw_markdown=None,
            error_message=None,
        )

        settings = RuntimeSettings(
            ai={
                "provider": "openai_compatible",
                "base_url": "https://api.deepseek.com/v1",
                "model": "deepseek-reasoner",
                "api_key": None,
            }
        )
        service = _create_service(settings, store)
        failed = await service.process_report(report.report_id)

        assert failed is not None
        assert failed.status == "failed"
        assert failed.finished_at is not None
        assert failed.error_message == "ai api_key is required when provider=openai_compatible"

        await store.close()

    asyncio.run(scenario())


def test_ai_report_service_uses_chat_completions_for_reasoner_without_temperature() -> None:
    async def scenario() -> None:
        store = EventStore()
        await store.initialize()
        await store.create_user(
            username="student_ai_provider_ok",
            password_hash=generate_password_hash("student123"),
            role="student",
            gym_ids=["gym-gz-01"],
            device_ids=["wb-003", "eq-003"],
        )
        await store.create_workout_session(
            username="student_ai_provider_ok",
            wristband_id="wb-003",
            gym_id="gym-gz-01",
            status="completed",
            source="manual",
            started_at="2026-04-20T08:00:00Z",
            ended_at="2026-04-20T08:20:00Z",
            equipment_ids=["eq-003"],
            segments=[
                WorkoutSessionSegment(
                    equipment_id="eq-003",
                    started_at="2026-04-20T08:00:00Z",
                    ended_at="2026-04-20T08:20:00Z",
                    duration_s=1200,
                    rep_count=24,
                    energy_wh=10.5,
                )
            ],
            metrics=WorkoutSessionMetrics(
                avg_heart_rate=128.0,
                max_heart_rate=148,
                total_steps=2100,
                total_rep_count=24,
                total_energy_wh=10.5,
                alert_count=0,
            ),
            notes="ai provider request test session",
        )
        report = await store.create_ai_report(
            user_id="student_ai_provider_ok",
            status="queued",
            start="2026-04-20T00:00:00Z",
            end="2026-04-20T23:59:59Z",
            summary_title="student_ai_provider_ok 训练分析待生成",
            summary="报告已入队，等待后续 AI 生成流程写入正式内容。",
            insights=[],
            recommendations=[],
            evidence_session_ids=[],
            raw_markdown=None,
            error_message=None,
        )

        settings = RuntimeSettings(
            ai={
                "provider": "openai_compatible",
                "base_url": "https://api.deepseek.com/v1",
                "model": "deepseek-reasoner",
                "api_key": "test-token",
            }
        )
        service = _create_service(settings, store)
        captured_request: dict[str, object] = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "summary_title": "中文训练分析报告",
                                            "summary": "这是一段中文总结。",
                                            "insights": ["中文观察一", "中文观察二"],
                                            "recommendations": ["中文建议一", "中文建议二"],
                                            "raw_markdown": "# 中文训练分析报告\n\n- 中文内容",
                                        },
                                        ensure_ascii=False,
                                    )
                                }
                            }
                        ]
                    },
                    ensure_ascii=False,
                ).encode("utf-8")

        def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
            captured_request["url"] = request.full_url
            captured_request["timeout"] = timeout
            captured_request["body"] = json.loads(request.data.decode("utf-8"))
            captured_request["headers"] = dict(request.header_items())
            return FakeResponse()

        with patch("app.services.ai_report_service.urllib_request.urlopen", side_effect=fake_urlopen):
            completed = await service.process_report(report.report_id)

        assert completed is not None
        assert completed.status == "completed"
        assert captured_request["url"] == "https://api.deepseek.com/v1/chat/completions"
        request_body = captured_request["body"]
        assert isinstance(request_body, dict)
        assert request_body["model"] == "deepseek-reasoner"
        assert "temperature" not in request_body
        assert request_body["response_format"] == {"type": "json_object"}
        messages = request_body["messages"]
        assert isinstance(messages, list)
        assert "所有自然语言字段必须使用简体中文" in messages[0]["content"]
        assert "请基于以下训练数据生成中文训练分析报告" in messages[1]["content"]

        await store.close()

    asyncio.run(scenario())
