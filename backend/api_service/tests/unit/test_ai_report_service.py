from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from app.services.ai_report_service import AiReportService
from app.services.auth_service import generate_password_hash
from app.models.workout import WorkoutSessionMetrics, WorkoutSessionSegment
from app.settings import RuntimeSettings
from app.storage.memory_store import EventStore


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

        service = AiReportService(RuntimeSettings(), store)
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
        service = AiReportService(settings, store)
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
        service = AiReportService(settings, store)
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
