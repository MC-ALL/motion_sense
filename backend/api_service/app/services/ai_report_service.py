from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from app.models.ai import AiReportDetail
from app.models.user import StoredUser
from app.models.workout import WorkoutSessionSummary
from app.services.realtime_service import RealtimeService
from app.settings import RuntimeSettings
from app.storage.store import Store


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

    async def start(self) -> None:
        if not self._settings.ai.auto_process or self._worker_task is not None:
            return
        await self.recover_pending_reports()
        self._worker_task = asyncio.create_task(self._run_loop(), name="backend-ai-report-worker")

    async def stop(self) -> None:
        if self._worker_task is None:
            return
        self._worker_task.cancel()
        try:
            await self._worker_task
        except asyncio.CancelledError:
            pass
        self._worker_task = None

    def enqueue_report(self, report_id: str) -> None:
        if not self._settings.ai.auto_process:
            return
        self._report_queue.put_nowait(report_id)

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
        target_user = await self._store.get_user(username=report.user_id)
        if target_user is None:
            raise RuntimeError("user not found for ai report generation")

        generating_report = await self._store.update_ai_report(report_id=report_id, status="generating")
        if generating_report is not None:
            await self.publish_report_update(generating_report, target_user=target_user)
        try:
            completed_payload = await self._build_completed_payload(report)
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

        if self._settings.ai.provider == "openai_compatible":
            payload = await asyncio.to_thread(
                self._generate_via_openai_compatible,
                target_user,
                report,
                sessions,
            )
            payload["evidence_session_ids"] = normalized_session_ids
            return payload

        payload = _generate_builtin_report(target_user=target_user, report=report, sessions=sessions)
        payload["evidence_session_ids"] = normalized_session_ids
        return payload

    def _generate_via_openai_compatible(
        self,
        target_user: StoredUser,
        report: AiReportDetail,
        sessions: list[WorkoutSessionSummary],
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
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是一名高校智慧体育系统的训练分析助手。"
                        "你必须只输出一个合法 JSON 对象，不要输出 Markdown 代码块，不要输出额外解释。"
                        "所有自然语言字段必须使用简体中文。"
                        "JSON 必须包含 summary_title、summary、insights、recommendations、raw_markdown 五个字段。"
                        "其中 summary_title 和 summary 必须是字符串；"
                        "insights 和 recommendations 必须是非空字符串数组；"
                        "raw_markdown 必须是中文 Markdown 文本，内容要与前述字段一致。"
                        "如果训练样本不足，也要明确说明数据不足，并给出中文建议。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请基于以下训练数据生成中文训练分析报告，并严格按要求返回 JSON。\n"
                        "输出要求：\n"
                        "1. `summary_title`：简短中文标题。\n"
                        "2. `summary`：1 段中文总结，优先概括训练时长、动作量、心率、能耗、器材覆盖。\n"
                        "3. `insights`：2 到 5 条中文观察结论。\n"
                        "4. `recommendations`：2 到 5 条中文训练建议。\n"
                        "5. `raw_markdown`：完整中文 Markdown 报告。\n"
                        "6. 不要输出英文标题或英文建议，除非设备 ID、用户名等原始标识本身就是英文。\n\n"
                        "训练数据如下：\n"
                        f"{json.dumps({'user': {'username': target_user.username, 'role': target_user.role, 'gym_ids': target_user.gym_ids, 'device_ids': target_user.device_ids}, 'report': {'report_id': report.report_id, 'start': report.start, 'end': report.end}, 'sessions': [item.model_dump(exclude_none=True) for item in sessions]}, ensure_ascii=False)}"
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
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("ai provider returned empty content")
        parsed = json.loads(content)
        insights = [str(item).strip() for item in parsed.get("insights", []) if str(item).strip()]
        recommendations = [
            str(item).strip() for item in parsed.get("recommendations", []) if str(item).strip()
        ]
        return {
            "summary_title": str(parsed.get("summary_title") or f"{target_user.username} 训练分析报告"),
            "summary": str(parsed.get("summary") or ""),
            "insights": insights,
            "recommendations": recommendations,
            "raw_markdown": str(parsed.get("raw_markdown") or ""),
        }


def _generate_builtin_report(
    *,
    target_user: StoredUser,
    report: AiReportDetail,
    sessions: list[WorkoutSessionSummary],
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
    equipment_label = "、".join(aggregate["equipment_ids"][:4]) or "无器材"
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
