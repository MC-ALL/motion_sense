from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from pydantic import BaseModel, Field
from redis.asyncio import Redis

from app.models.ingest import AlertRecord, DeviceSummary, TelemetryRecord
from app.models.ai import AiReportDetail
from app.models.user import StoredUser
from app.models.workout import WorkoutSessionSummary
from app.services.realtime_service import RealtimeService
from app.settings import RuntimeSettings
from app.storage.store import Store


MAX_CONTEXT_TELEMETRY_RECORDS = 5000
MAX_TELEMETRY_SAMPLES = 12
WRISTBAND_TELEMETRY_FIELDS = ("heart_rate", "step_count", "battery_pct")
EQUIPMENT_TELEMETRY_FIELDS = (
    "rep_count",
    "power_w",
    "energy_wh",
    "axis_angle",
    "voltage_v",
    "current_ma",
)
ENV_TELEMETRY_FIELDS = ("temperature", "temperature_c", "humidity", "co2_ppm", "pm2_5", "pm10", "lux")
COUNTER_FIELDS = {"step_count", "rep_count", "energy_wh"}


class AiReportSegmentAssessment(BaseModel):
    equipment_id: str
    equipment_name: str | None = None
    equipment_kind: str | None = None
    summary: str = Field(min_length=1)
    observations: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class AiReportEvidenceItem(BaseModel):
    source_type: str = Field(min_length=1)
    reference_id: str | None = None
    description: str = Field(min_length=1)


class AiReportProviderOutput(BaseModel):
    summary_title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    insights: list[str] = Field(min_length=1)
    recommendations: list[str] = Field(min_length=1)
    segment_assessments: list[AiReportSegmentAssessment] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    evidence: list[AiReportEvidenceItem] = Field(default_factory=list)
    raw_markdown: str = Field(min_length=1)


class AiReportService:
    def __init__(
        self,
        settings: RuntimeSettings,
        store: Store,
        realtime_service: RealtimeService,
    ) -> None:
        self._settings = settings
        self._store = store
        self._realtime_service = realtime_service
        self._worker_task: asyncio.Task[None] | None = None
        self._report_queue: asyncio.Queue[str] = asyncio.Queue()
        self._wakeup_redis: Redis | None = None
        self._wakeup_listener_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if not self._settings.ai.auto_process or self._worker_task is not None:
            return
        await self._start_wakeup_listener()
        try:
            await self.recover_pending_reports()
            self._worker_task = asyncio.create_task(self._run_loop(), name="backend-ai-report-worker")
        except Exception:
            await self._stop_wakeup_listener()
            raise

    async def stop(self) -> None:
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        await self._stop_wakeup_listener()

    def enqueue_report(self, report_id: str) -> None:
        if not self._settings.ai.auto_process:
            return
        self._report_queue.put_nowait(report_id)

    async def wakeup_report(self, report_id: str) -> None:
        if not self._settings.ai.auto_process:
            return
        self.enqueue_report(report_id)
        if self._settings.ai.wakeup_backend != "redis":
            return
        if self._wakeup_redis is None:
            raise RuntimeError("redis ai wakeup service is not started")
        await self._wakeup_redis.publish(
            self._settings.ai.wakeup_channel,
            json.dumps({"report_id": report_id}, separators=(",", ":"), ensure_ascii=True),
        )

    async def recover_pending_reports(self) -> int:
        queued_report_ids = await self._list_report_ids(status="queued")
        generating_report_ids = await self._list_report_ids(status="generating")
        for report_id in generating_report_ids:
            await self._store.update_ai_report(
                report_id=report_id,
                status="queued",
                error_message=None,
                finished_at=None,
            )
        for report_id in [*queued_report_ids, *generating_report_ids]:
            self.enqueue_report(report_id)
        return len(queued_report_ids) + len(generating_report_ids)

    async def process_report(self, report_id: str) -> AiReportDetail | None:
        report = await self._store.get_ai_report(report_id=report_id)
        if report is None or report.status != "queued":
            return report
        generating_report = await self._store.claim_ai_report(
            report_id=report_id,
            from_status="queued",
            to_status="generating",
        )
        if generating_report is None:
            return await self._store.get_ai_report(report_id=report_id)
        target_user = await self._store.get_user(username=generating_report.user_id)
        if target_user is None:
            raise RuntimeError("user not found for ai report generation")
        if generating_report is not None:
            await self.publish_report_update(generating_report, target_user=target_user)
        try:
            completed_payload = await self._build_completed_payload(generating_report)
        except Exception as exc:
            failed_report = await self._store.update_ai_report(
                report_id=report_id,
                status="failed",
                error_message=str(exc),
                finished_at=_now_iso(),
            )
            if failed_report is not None:
                await self.publish_report_update(failed_report, target_user=target_user)
            return failed_report

        completed_report = await self._store.update_ai_report(
            report_id=report_id,
            status="completed",
            summary_title=completed_payload["summary_title"],
            summary=completed_payload["summary"],
            insights=completed_payload["insights"],
            recommendations=completed_payload["recommendations"],
            evidence_session_ids=completed_payload["evidence_session_ids"],
            raw_markdown=completed_payload["raw_markdown"],
            finished_at=_now_iso(),
        )
        if completed_report is not None:
            await self.publish_report_update(completed_report, target_user=target_user)
        return completed_report

    async def _run_loop(self) -> None:
        while True:
            report_id: str | None = None
            try:
                report_id = await self._report_queue.get()
                try:
                    await self.process_report(report_id)
                except Exception:
                    pass
            finally:
                if report_id is not None:
                    self._report_queue.task_done()

    async def _start_wakeup_listener(self) -> None:
        if self._settings.ai.wakeup_backend != "redis":
            return
        self._wakeup_redis = Redis.from_url(self._settings.redis.url(), decode_responses=True)
        await self._wakeup_redis.ping()
        self._wakeup_listener_task = asyncio.create_task(
            self._listen_for_wakeup(),
            name="backend-ai-report-wakeup-listener",
        )

    async def _stop_wakeup_listener(self) -> None:
        if self._wakeup_listener_task is not None:
            self._wakeup_listener_task.cancel()
            try:
                await self._wakeup_listener_task
            except asyncio.CancelledError:
                pass
            self._wakeup_listener_task = None
        if self._wakeup_redis is not None:
            await self._wakeup_redis.aclose()
            self._wakeup_redis = None

    async def _listen_for_wakeup(self) -> None:
        assert self._wakeup_redis is not None
        pubsub = self._wakeup_redis.pubsub()
        await pubsub.subscribe(self._settings.ai.wakeup_channel)
        try:
            async for item in pubsub.listen():
                if item is None or item.get("type") != "message":
                    continue
                data = item.get("data")
                if not isinstance(data, str):
                    continue
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue
                report_id = payload.get("report_id") if isinstance(payload, dict) else None
                if isinstance(report_id, str) and report_id:
                    self.enqueue_report(report_id)
        finally:
            await pubsub.aclose()

    async def _list_report_ids(self, *, status: str) -> list[str]:
        report_ids: list[str] = []
        offset = 0
        while True:
            reports = await self._store.list_ai_reports(
                status=status,
                limit=self._settings.ai.batch_size,
                offset=offset,
            )
            if not reports:
                break
            report_ids.extend(item.report_id for item in reports)
            if len(reports) < self._settings.ai.batch_size:
                break
            offset += len(reports)
        return report_ids

    async def publish_report_update(
        self,
        report: AiReportDetail,
        *,
        target_user: StoredUser,
    ) -> None:
        await self._realtime_service.publish(
            {
                "type": "ai_report",
                "data": report.model_dump(exclude_none=True),
                "scope": {
                    "user_id": target_user.username,
                    "gym_ids": target_user.gym_ids,
                    "device_ids": target_user.device_ids,
                },
            }
        )

    async def _build_analysis_context(
        self,
        *,
        target_user: StoredUser,
        report: AiReportDetail,
        sessions: list[WorkoutSessionSummary],
    ) -> dict[str, Any]:
        equipment_ids = _collect_equipment_ids(sessions)
        equipment_profiles = await self._load_device_profiles(equipment_ids)
        environment_profiles = await self._load_environment_profiles(target_user=target_user, sessions=sessions)
        alert_device_ids = _dedupe(
            [
                target_user.device_ids,
                [item.wristband_id for item in sessions],
                equipment_ids,
                list(environment_profiles),
            ]
        )
        alert_summary = await self._build_alert_summary(
            device_ids=alert_device_ids,
            start=report.start,
            end=report.end,
        )

        session_contexts: list[dict[str, Any]] = []
        for session in sessions:
            session_start = session.started_at
            session_end = session.ended_at or report.end
            wristband_records = await self._store.list_telemetry(
                device_type="wristband",
                device_id=session.wristband_id,
                start=session_start,
                end=session_end,
                limit=MAX_CONTEXT_TELEMETRY_RECORDS,
                offset=0,
            )
            segments: list[dict[str, Any]] = []
            for segment in session.segments:
                segment_start = segment.started_at
                segment_end = segment.ended_at or session_end
                equipment_records = await self._store.list_telemetry(
                    device_type="equipment",
                    device_id=segment.equipment_id,
                    start=segment_start,
                    end=segment_end,
                    limit=MAX_CONTEXT_TELEMETRY_RECORDS,
                    offset=0,
                )
                segment_wristband_records = await self._store.list_telemetry(
                    device_type="wristband",
                    device_id=session.wristband_id,
                    start=segment_start,
                    end=segment_end,
                    limit=MAX_CONTEXT_TELEMETRY_RECORDS,
                    offset=0,
                )
                equipment_profile = equipment_profiles.get(segment.equipment_id)
                segments.append(
                    {
                        **segment.model_dump(exclude_none=True),
                        "equipment_profile": _compact_device_profile(equipment_profile),
                        "telemetry_summary": {
                            "equipment": _summarize_telemetry_records(
                                equipment_records,
                                fields=EQUIPMENT_TELEMETRY_FIELDS,
                                counter_fields=COUNTER_FIELDS,
                            ),
                            "wristband": _summarize_telemetry_records(
                                segment_wristband_records,
                                fields=WRISTBAND_TELEMETRY_FIELDS,
                                counter_fields=COUNTER_FIELDS,
                            ),
                        },
                    }
                )

            session_contexts.append(
                {
                    **session.model_dump(exclude_none=True),
                    "wristband_telemetry_summary": _summarize_telemetry_records(
                        wristband_records,
                        fields=WRISTBAND_TELEMETRY_FIELDS,
                        counter_fields=COUNTER_FIELDS,
                    ),
                    "segments": segments,
                }
            )

        environment_summaries: list[dict[str, Any]] = []
        for device_id, device in environment_profiles.items():
            records = await self._store.list_telemetry(
                device_type="env",
                device_id=device_id,
                start=report.start,
                end=report.end,
                limit=MAX_CONTEXT_TELEMETRY_RECORDS,
                offset=0,
            )
            environment_summaries.append(
                {
                    "device_profile": _compact_device_profile(device),
                    "telemetry_summary": _summarize_telemetry_records(
                        records,
                        fields=ENV_TELEMETRY_FIELDS,
                        counter_fields=set(),
                    ),
                }
            )

        return {
            "schema_version": "ai_training_context.v1",
            "student": {
                "username": target_user.username,
                "role": target_user.role,
                "gym_ids": target_user.gym_ids,
                "device_ids": target_user.device_ids,
                "health_profile": None,
                "health_profile_note": "not_available_in_current_schema",
            },
            "report": {
                "report_id": report.report_id,
                "start": report.start,
                "end": report.end,
            },
            "equipment_profiles": [
                _compact_device_profile(equipment_profiles[device_id])
                for device_id in equipment_ids
                if device_id in equipment_profiles
            ],
            "environment_profiles": [
                _compact_device_profile(device)
                for _, device in sorted(environment_profiles.items())
            ],
            "sessions": session_contexts,
            "environment_summary": environment_summaries,
            "alert_summary": alert_summary,
        }

    async def _load_device_profiles(self, device_ids: list[str]) -> dict[str, DeviceSummary]:
        profiles: dict[str, DeviceSummary] = {}
        for device_id in device_ids:
            device = await self._store.get_device(device_id=device_id)
            if device is not None:
                profiles[device_id] = device
        return profiles

    async def _load_environment_profiles(
        self,
        *,
        target_user: StoredUser,
        sessions: list[WorkoutSessionSummary],
    ) -> dict[str, DeviceSummary]:
        profiles: dict[str, DeviceSummary] = {}
        for device_id in target_user.device_ids:
            device = await self._store.get_device(device_id=device_id)
            if device is not None and device.device_type == "env":
                profiles[device_id] = device

        scoped_gym_ids = set(target_user.gym_ids)
        if not scoped_gym_ids:
            scoped_gym_ids = {item.gym_id for item in sessions}
        if scoped_gym_ids:
            for device in await self._store.list_devices(device_type="env"):
                if device.gym_id in scoped_gym_ids:
                    profiles.setdefault(device.device_id, device)
        return profiles

    async def _build_alert_summary(
        self,
        *,
        device_ids: list[str],
        start: str,
        end: str,
    ) -> dict[str, Any]:
        alerts: list[AlertRecord] = []
        start_dt = _parse_iso_datetime(start)
        end_dt = _parse_iso_datetime(end)
        for device_id in device_ids:
            for alert in await self._store.list_alerts(device_id=device_id):
                triggered_at = _parse_iso_datetime(alert.triggered_at)
                if start_dt <= triggered_at <= end_dt:
                    alerts.append(alert)

        by_level: dict[str, int] = {}
        by_code: dict[str, int] = {}
        for alert in alerts:
            by_level[alert.level] = by_level.get(alert.level, 0) + 1
            by_code[alert.code] = by_code.get(alert.code, 0) + 1

        return {
            "total": len(alerts),
            "by_level": by_level,
            "by_code": by_code,
            "items": [
                {
                    "id": alert.id,
                    "device_id": alert.device_id,
                    "device_type": alert.device_type,
                    "level": alert.level,
                    "code": alert.code,
                    "message": alert.message,
                    "priority": alert.priority,
                    "triggered_at": alert.triggered_at,
                    "is_ack": alert.is_ack,
                }
                for alert in sorted(alerts, key=lambda item: (item.triggered_at, item.id), reverse=True)[:20]
            ],
        }

    async def _build_completed_payload(self, report: AiReportDetail) -> dict[str, Any]:
        target_user = await self._store.get_user(username=report.user_id)
        if target_user is None:
            raise RuntimeError("user not found for ai report generation")

        sessions = await self._store.list_workout_sessions(
            username=report.user_id,
            start=report.start,
            end=report.end,
            limit=5000,
            offset=0,
        )
        normalized_session_ids = [item.session_id for item in sessions]
        analysis_context = await self._build_analysis_context(
            target_user=target_user,
            report=report,
            sessions=sessions,
        )

        if self._settings.ai.provider == "openai_compatible":
            payload = await asyncio.to_thread(
                self._generate_via_openai_compatible,
                target_user,
                report,
                analysis_context,
            )
            payload["evidence_session_ids"] = normalized_session_ids
            return payload

        payload = _generate_builtin_report(
            target_user=target_user,
            report=report,
            sessions=sessions,
            analysis_context=analysis_context,
        )
        payload["evidence_session_ids"] = normalized_session_ids
        return payload

    def _generate_via_openai_compatible(
        self,
        target_user: StoredUser,
        report: AiReportDetail,
        analysis_context: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._settings.ai.api_key:
            raise RuntimeError("ai api_key is required when provider=openai_compatible")
        if not self._settings.ai.base_url:
            raise RuntimeError("ai base_url is required when provider=openai_compatible")
        if not self._settings.ai.model:
            raise RuntimeError("ai model is required when provider=openai_compatible")

        base_url = self._settings.ai.base_url.rstrip("/")
        request_url = (
            f"{base_url}/chat/completions"
            if base_url.endswith("/v1")
            else f"{base_url}/v1/chat/completions"
        )
        model_name = self._settings.ai.model.strip()
        is_reasoner_model = model_name == "deepseek-reasoner"
        request_body = {
            "model": model_name,
            "stream": False,
            "response_format": {"type": "json_object"},
            "max_tokens": self._settings.ai.max_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是一名高校智慧体育系统的训练分析助手。"
                        "你必须只输出一个合法 JSON 对象，不要输出 Markdown 代码块，不要输出额外解释。"
                        "所有自然语言字段必须使用简体中文。"
                        "JSON 必须符合用户消息中的输出 schema。"
                        "其中 summary_title 和 summary 必须是字符串；"
                        "insights 和 recommendations 必须是非空字符串数组；"
                        "segment_assessments 必须逐段说明器材类型、负荷表现和建议；"
                        "raw_markdown 必须是中文 Markdown 文本，内容要与结构化字段一致。"
                        "只能基于输入 JSON 中明确给出的事实分析；缺失的健康资料、器材信息或原始遥测必须说明缺失，不要编造。"
                        "如果训练样本不足，也要明确说明数据不足，并给出中文建议。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请基于以下训练数据生成中文训练分析报告，并严格按要求返回 JSON。\n"
                        "输出 schema 示例：\n"
                        "{\n"
                        '  "summary_title": "中文标题",\n'
                        '  "summary": "一段中文总结",\n'
                        '  "insights": ["2 到 5 条中文观察"],\n'
                        '  "recommendations": ["2 到 5 条中文建议"],\n'
                        '  "segment_assessments": [\n'
                        "    {\n"
                        '      "equipment_id": "器材 ID",\n'
                        '      "equipment_name": "器材名称，可为空",\n'
                        '      "equipment_kind": "器材类型，可为空",\n'
                        '      "summary": "本段训练中文总结",\n'
                        '      "observations": ["本段观察"],\n'
                        '      "recommendations": ["本段建议"]\n'
                        "    }\n"
                        "  ],\n"
                        '  "risk_flags": ["风险或数据质量提示；没有则为空数组"],\n'
                        '  "evidence": [{"source_type": "session|segment|telemetry|device|alert", "reference_id": "引用 ID", "description": "证据说明"}],\n'
                        '  "raw_markdown": "完整中文 Markdown 报告"\n'
                        "}\n\n"
                        "分析要求：\n"
                        "1. 优先使用 equipment_profiles 和 segment.telemetry_summary 中的器材名称、器材类型、位置与 metadata，不要只写设备 ID。\n"
                        "2. 除总量、平均值、最大值外，要结合分位数、起止值、趋势、计数器增量和采样点分析训练过程。\n"
                        "3. 对环境数据和告警摘要做简短判断；没有告警时明确说明本窗口未见告警。\n"
                        "4. 如果 student.health_profile 为空，不要给出基于身高体重体脂的结论，只说明缺少个体健康资料。\n"
                        "5. 不要输出英文标题或英文建议，除非设备 ID、字段名等原始标识本身就是英文。\n\n"
                        "analysis_context JSON 如下：\n"
                        f"{json.dumps(analysis_context, ensure_ascii=False, separators=(',', ':'))}"
                    ),
                },
            ],
        }
        if not is_reasoner_model:
            request_body["temperature"] = 0.2
        req = urllib_request.Request(
            request_url,
            method="POST",
            data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._settings.ai.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib_request.urlopen(req, timeout=self._settings.ai.request_timeout_s) as response:
                raw_response = json.loads(response.read().decode("utf-8"))
        except urllib_error.HTTPError as exc:
            raise RuntimeError(exc.read().decode("utf-8")) from exc

        choices = raw_response.get("choices") or []
        if not choices:
            raise RuntimeError("ai provider returned empty choices")
        choice = choices[0]
        if choice.get("finish_reason") == "length":
            raise RuntimeError("ai provider response was truncated")
        message = choice.get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("ai provider returned empty content")
        parsed = json.loads(content)
        output = AiReportProviderOutput.model_validate(parsed)
        insights = _normalize_string_list(output.insights)
        recommendations = _normalize_string_list(output.recommendations)
        if not insights:
            raise RuntimeError("ai provider returned empty insights")
        if not recommendations:
            raise RuntimeError("ai provider returned empty recommendations")
        return {
            "summary_title": output.summary_title.strip() or f"{target_user.username} 训练分析报告",
            "summary": output.summary.strip(),
            "insights": insights,
            "recommendations": recommendations,
            "raw_markdown": output.raw_markdown.strip(),
        }


def _collect_equipment_ids(sessions: list[WorkoutSessionSummary]) -> list[str]:
    groups: list[list[str]] = []
    for session in sessions:
        groups.append(session.equipment_ids)
        groups.append([segment.equipment_id for segment in session.segments])
    return _dedupe(groups)


def _dedupe(groups: list[list[str]]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            if not item or item in seen:
                continue
            seen.add(item)
            values.append(item)
    return values


def _compact_device_profile(device: DeviceSummary | None) -> dict[str, Any] | None:
    if device is None:
        return None
    metadata = device.metadata or {}
    equipment_kind = _first_string(metadata, ["equipment_kind", "kind", "type", "category"])
    training_category = _first_string(metadata, ["training_category", "training_type", "sport_category"])
    return {
        "gym_id": device.gym_id,
        "device_type": device.device_type,
        "device_id": device.device_id,
        "display_name": device.display_name,
        "location": device.location,
        "equipment_kind": equipment_kind,
        "training_category": training_category,
        "metadata": metadata,
    }


def _first_string(values: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = values.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _summarize_telemetry_records(
    records: list[TelemetryRecord],
    *,
    fields: tuple[str, ...],
    counter_fields: set[str],
) -> dict[str, Any]:
    ordered = sorted(records, key=lambda item: _parse_iso_datetime(item.ts))
    metrics: dict[str, Any] = {}
    for field in fields:
        points = [
            (_parse_iso_datetime(record.ts), _coerce_float(record.payload.get(field)))
            for record in ordered
        ]
        numeric_points = [(ts, value) for ts, value in points if value is not None]
        if not numeric_points:
            continue
        metrics[field] = _summarize_numeric_points(
            numeric_points,
            include_counter_delta=field in counter_fields,
        )

    return {
        "record_count": len(ordered),
        "start_ts": ordered[0].ts if ordered else None,
        "end_ts": ordered[-1].ts if ordered else None,
        "metrics": metrics,
        "samples": _sample_telemetry_records(ordered, fields=fields),
    }


def _summarize_numeric_points(
    points: list[tuple[datetime, float]],
    *,
    include_counter_delta: bool,
) -> dict[str, Any]:
    values = [value for _, value in points]
    first = values[0]
    last = values[-1]
    result: dict[str, Any] = {
        "count": len(values),
        "first": _round_float(first),
        "last": _round_float(last),
        "min": _round_float(min(values)),
        "max": _round_float(max(values)),
        "avg": _round_float(sum(values) / len(values)),
        "p25": _round_float(_percentile(values, 0.25)),
        "p50": _round_float(_percentile(values, 0.50)),
        "p75": _round_float(_percentile(values, 0.75)),
        "trend": _trend(first, last),
    }
    if include_counter_delta:
        result["delta"] = _round_float(_counter_delta_float(values))
    else:
        result["delta"] = _round_float(last - first)
    return result


def _sample_telemetry_records(records: list[TelemetryRecord], *, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    if not records:
        return []
    if len(records) <= MAX_TELEMETRY_SAMPLES:
        selected = records
    else:
        indexes = {
            round(index * (len(records) - 1) / (MAX_TELEMETRY_SAMPLES - 1))
            for index in range(MAX_TELEMETRY_SAMPLES)
        }
        selected = [records[index] for index in sorted(indexes)]
    samples: list[dict[str, Any]] = []
    for record in selected:
        payload = {
            field: record.payload[field]
            for field in fields
            if field in record.payload and _coerce_float(record.payload.get(field)) is not None
        }
        if payload:
            samples.append({"ts": record.ts, "payload": payload})
    return samples


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * ratio
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return ordered[lower_index] * (1 - fraction) + ordered[upper_index] * fraction


def _trend(first: float, last: float) -> str:
    delta = last - first
    if abs(delta) < max(abs(first), 1.0) * 0.05:
        return "stable"
    return "increasing" if delta > 0 else "decreasing"


def _counter_delta_float(values: list[float]) -> float:
    if not values:
        return 0.0
    total = 0.0
    previous = values[0]
    for value in values[1:]:
        if value >= previous:
            total += value - previous
        else:
            total += value
        previous = value
    return total


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _round_float(value: float) -> int | float:
    rounded = round(value, 3)
    if rounded.is_integer():
        return int(rounded)
    return rounded


def _parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_string_list(values: list[str]) -> list[str]:
    return [item.strip() for item in values if item.strip()]


def _format_equipment_label(equipment_ids: list[str], analysis_context: dict[str, Any] | None) -> str:
    labels: list[str] = []
    profiles = {}
    if analysis_context is not None:
        profiles = {
            item.get("device_id"): item
            for item in analysis_context.get("equipment_profiles", [])
            if isinstance(item, dict)
        }
    for equipment_id in equipment_ids[:4]:
        profile = profiles.get(equipment_id)
        if not isinstance(profile, dict):
            labels.append(equipment_id)
            continue
        display_name = profile.get("display_name")
        equipment_kind = profile.get("equipment_kind")
        if isinstance(display_name, str) and display_name.strip():
            label = display_name.strip()
            if isinstance(equipment_kind, str) and equipment_kind.strip() and equipment_kind.strip() != label:
                label = f"{label}({equipment_kind.strip()})"
            labels.append(label)
        elif isinstance(equipment_kind, str) and equipment_kind.strip():
            labels.append(f"{equipment_kind.strip()}[{equipment_id}]")
        else:
            labels.append(equipment_id)
    return "、".join(labels) or "无器材"


def _generate_builtin_report(
    *,
    target_user: StoredUser,
    report: AiReportDetail,
    sessions: list[WorkoutSessionSummary],
    analysis_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    title = f"{target_user.username} 训练分析报告"
    if not sessions:
        summary = "当前分析窗口内没有训练会话，暂无足够数据生成训练结论。"
        insights = [
            "当前时间窗口内未检索到训练会话，无法判断训练频率与负荷变化。",
            "如学生已经训练，请先检查手环绑定、训练会话回填或时间窗口选择是否正确。",
        ]
        recommendations = [
            "优先确认训练设备绑定关系和训练会话是否已写入系统。",
            "如近期没有训练记录，建议先建立连续 1 到 2 周的数据样本后再做趋势分析。",
        ]
        raw_markdown = "\n".join(
            [
                f"# {title}",
                "",
                f"- 学生：{target_user.username}",
                f"- 分析窗口：{report.start} ~ {report.end}",
                "",
                "## 总结",
                summary,
                "",
                "## 观察",
                *(f"- {item}" for item in insights),
                "",
                "## 建议",
                *(f"- {item}" for item in recommendations),
            ]
        )
        return {
            "summary_title": title,
            "summary": summary,
            "insights": insights,
            "recommendations": recommendations,
            "raw_markdown": raw_markdown,
        }

    aggregate = _aggregate_sessions(sessions)
    avg_duration_s = round(aggregate["total_duration_s"] / max(len(sessions), 1))
    avg_rep_count = round(aggregate["total_rep_count"] / max(len(sessions), 1))
    duration_label = _format_duration(aggregate["total_duration_s"])
    avg_duration_label = _format_duration(avg_duration_s)
    equipment_label = _format_equipment_label(aggregate["equipment_ids"], analysis_context)
    summary = (
        f"在 {report.start} 至 {report.end} 的窗口内，共记录 {aggregate['completed_sessions']} 次已完成训练，"
        f"累计时长 {duration_label}，覆盖 {len(aggregate['equipment_ids'])} 台器材。"
        f"单次平均训练时长约 {avg_duration_label}，平均动作量约 {avg_rep_count} 次。"
    )

    insights = [
        f"训练窗口内共发现 {len(sessions)} 次训练会话，其中已完成 {aggregate['completed_sessions']} 次，最近一次训练结束于 {aggregate['last_session_at'] or report.end}。",
        f"累计动作量 {aggregate['total_rep_count']} 次，累计能耗 {aggregate['total_energy_wh']:.1f} Wh，主要涉及器材：{equipment_label}。",
    ]
    if aggregate["avg_heart_rate"] is not None:
        insights.append(
            f"平均心率约 {aggregate['avg_heart_rate']:.1f}，峰值心率约 {aggregate['max_heart_rate'] or '--'}，可用于观察当前负荷强度。"
        )
    if aggregate["open_sessions"] > 0 or aggregate["cancelled_sessions"] > 0:
        insights.append(
            f"窗口内仍存在 {aggregate['open_sessions']} 次未闭合会话、{aggregate['cancelled_sessions']} 次已取消会话，建议关注数据完整性。"
        )
    else:
        insights.append("当前窗口内训练会话状态完整，适合继续做阶段性趋势分析。")

    recommendations = []
    if len(sessions) < 2:
        recommendations.append("建议继续积累至少 2 到 3 次连续训练记录，再观察训练节奏与负荷变化。")
    else:
        recommendations.append("建议按周对比单次平均时长、动作量和能耗，观察训练负荷是否稳定提升。")
    if aggregate["avg_heart_rate"] is not None and aggregate["avg_heart_rate"] >= 145:
        recommendations.append("平均心率偏高，建议在高强度训练后安排恢复日，并结合主观疲劳度判断是否需要降强度。")
    else:
        recommendations.append("当前心率负荷整体可控，可结合目标动作量逐步增加训练密度或训练时长。")
    if len(aggregate["equipment_ids"]) <= 1:
        recommendations.append("当前器材类型较集中，建议适度增加器材或动作类型，避免训练刺激过于单一。")
    else:
        recommendations.append("器材覆盖较丰富，建议继续保留多器材组合，并关注不同器材间的负荷分配。")

    raw_markdown = "\n".join(
        [
            f"# {title}",
            "",
            f"- 学生：{target_user.username}",
            f"- 分析窗口：{report.start} ~ {report.end}",
            f"- 训练会话数：{len(sessions)}",
            "",
            "## 总结",
            summary,
            "",
            "## 亮点与观察",
            *(f"- {item}" for item in insights),
            "",
            "## 后续建议",
            *(f"- {item}" for item in recommendations),
        ]
    )
    return {
        "summary_title": title,
        "summary": summary,
        "insights": insights,
        "recommendations": recommendations,
        "raw_markdown": raw_markdown,
    }


def _aggregate_sessions(sessions: list[WorkoutSessionSummary]) -> dict[str, Any]:
    equipment_ids: list[str] = []
    seen_equipment_ids: set[str] = set()
    total_duration_s = 0
    total_rep_count = 0
    total_energy_wh = 0.0
    avg_heart_rate_values: list[float] = []
    weighted_avg_heart_rate_sum = 0.0
    weighted_avg_heart_rate_duration = 0
    max_heart_rate: int | None = None
    last_session_at: str | None = None

    for session in sessions:
        if session.ended_at and (last_session_at is None or session.ended_at > last_session_at):
            last_session_at = session.ended_at
        elif last_session_at is None:
            last_session_at = session.started_at

        total_duration_s += session.duration_s or 0
        total_rep_count += session.metrics.total_rep_count or 0
        total_energy_wh += session.metrics.total_energy_wh or 0

        if session.metrics.max_heart_rate is not None:
            max_heart_rate = (
                session.metrics.max_heart_rate
                if max_heart_rate is None
                else max(max_heart_rate, session.metrics.max_heart_rate)
            )

        avg_heart_rate = session.metrics.avg_heart_rate
        if avg_heart_rate is not None:
            if (session.duration_s or 0) > 0:
                weighted_avg_heart_rate_sum += avg_heart_rate * (session.duration_s or 0)
                weighted_avg_heart_rate_duration += session.duration_s or 0
            else:
                avg_heart_rate_values.append(avg_heart_rate)

        for equipment_id in session.equipment_ids:
            if equipment_id in seen_equipment_ids:
                continue
            seen_equipment_ids.add(equipment_id)
            equipment_ids.append(equipment_id)

    avg_heart_rate_result: float | None = None
    if weighted_avg_heart_rate_duration > 0:
        avg_heart_rate_result = weighted_avg_heart_rate_sum / weighted_avg_heart_rate_duration
    elif avg_heart_rate_values:
        avg_heart_rate_result = sum(avg_heart_rate_values) / len(avg_heart_rate_values)

    return {
        "total_duration_s": total_duration_s,
        "total_rep_count": total_rep_count,
        "total_energy_wh": total_energy_wh,
        "equipment_ids": equipment_ids,
        "avg_heart_rate": avg_heart_rate_result,
        "max_heart_rate": max_heart_rate,
        "last_session_at": last_session_at,
        "completed_sessions": sum(1 for item in sessions if item.status == "completed"),
        "open_sessions": sum(1 for item in sessions if item.status == "open"),
        "cancelled_sessions": sum(1 for item in sessions if item.status == "cancelled"),
    }


def _format_duration(duration_s: int) -> str:
    if duration_s <= 0:
        return "0 分钟"
    hours = duration_s // 3600
    minutes = (duration_s % 3600) // 60
    if hours > 0:
        return f"{hours} 小时 {minutes} 分"
    return f"{minutes} 分钟"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
