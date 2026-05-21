from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.models.ai import AiReportDetail, AiReportStatus, AiReportSummary
from app.models.auth import StoredRefreshSession
from app.models.device_config import DeviceConfigCommandRecord, GatewayCommandResultRequest
from app.models.ingest import (
    AlertRecord,
    BindingEventRecord,
    DeviceSummary,
    EnvTelemetryAggregateRecord,
    TelemetryRecord,
)
from app.models.user import StoredUser, UserRole, UserSummary
from app.models.workout import (
    BindingSource,
    UserWristbandBindingSummary,
    WorkoutSessionMetrics,
    WorkoutSessionSegment,
    WorkoutSessionSource,
    WorkoutSessionStatus,
    WorkoutSessionSummary,
)
from app.storage.telemetry_aggregate import aggregate_env_records


class EventStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._devices: dict[str, DeviceSummary] = {}
        self._users: dict[str, StoredUser] = {}
        self._refresh_sessions: dict[str, StoredRefreshSession] = {}
        self._alerts: list[AlertRecord] = []
        self._bindings: list[BindingEventRecord] = []
        self._user_wristband_bindings: list[UserWristbandBindingSummary] = []
        self._telemetry: list[TelemetryRecord] = []
        self._workout_sessions: dict[str, WorkoutSessionSummary] = {}
        self._ai_reports: dict[str, AiReportDetail] = {}
        self._device_config_commands: dict[str, DeviceConfigCommandRecord] = {}
        self._next_alert_id = 1
        self._next_binding_id = 1
        self._next_user_wristband_binding_id = 1

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def list_users(self) -> list[UserSummary]:
        async with self._lock:
            users = list(self._users.values())
        return [
            UserSummary.model_validate(user.model_dump(exclude={"password_hash"}))
            for user in sorted(users, key=lambda item: item.username)
        ]

    async def get_user(self, *, username: str) -> StoredUser | None:
        async with self._lock:
            return self._users.get(username)

    async def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        role: UserRole,
        gym_ids: list[str],
        device_ids: list[str],
    ) -> UserSummary:
        async with self._lock:
            if username in self._users:
                raise ValueError("username already exists")
            now = _now_iso()
            user = StoredUser(
                username=username,
                role=role,
                gym_ids=list(gym_ids),
                device_ids=list(device_ids),
                password_hash=password_hash,
                created_at=now,
                updated_at=now,
            )
            self._users[username] = user
            return UserSummary.model_validate(user.model_dump(exclude={"password_hash"}))

    async def update_user(
        self,
        *,
        username: str,
        password_hash: str | None = None,
        role: UserRole | None = None,
        gym_ids: list[str] | None = None,
        device_ids: list[str] | None = None,
    ) -> UserSummary | None:
        async with self._lock:
            existing = self._users.get(username)
            if existing is None:
                return None
            updated = existing.model_copy(
                update={
                    "password_hash": password_hash or existing.password_hash,
                    "role": role or existing.role,
                    "gym_ids": list(gym_ids) if gym_ids is not None else existing.gym_ids,
                    "device_ids": list(device_ids) if device_ids is not None else existing.device_ids,
                    "updated_at": _now_iso(),
                }
            )
            self._users[username] = updated
            return UserSummary.model_validate(updated.model_dump(exclude={"password_hash"}))

    async def delete_user(self, *, username: str) -> bool:
        async with self._lock:
            return self._users.pop(username, None) is not None

    async def create_user_wristband_binding(
        self,
        *,
        username: str,
        wristband_id: str,
        gym_id: str,
        bound_at: str | None,
        source: BindingSource,
        note: str | None,
    ) -> UserWristbandBindingSummary:
        async with self._lock:
            self._ensure_active_user_wristband_binding_conflict_locked(
                username=username,
                wristband_id=wristband_id,
            )
            now = _now_iso()
            binding = UserWristbandBindingSummary(
                id=self._next_user_wristband_binding_id,
                username=username,
                wristband_id=wristband_id,
                gym_id=gym_id,
                is_active=True,
                bound_at=_normalize_iso(bound_at) or now,
                unbound_at=None,
                source=source,
                note=note,
                created_at=now,
                updated_at=now,
            )
            self._next_user_wristband_binding_id += 1
            self._user_wristband_bindings.insert(0, binding)
            return binding

    async def end_user_wristband_binding(
        self,
        *,
        binding_id: int,
        unbound_at: str | None,
        note: str | None,
    ) -> UserWristbandBindingSummary | None:
        async with self._lock:
            for index, binding in enumerate(self._user_wristband_bindings):
                if binding.id != binding_id:
                    continue
                if not binding.is_active:
                    return binding
                updated = binding.model_copy(
                    update={
                        "is_active": False,
                        "unbound_at": _normalize_iso(unbound_at) or _now_iso(),
                        "note": note if note is not None else binding.note,
                        "updated_at": _now_iso(),
                    }
                )
                self._user_wristband_bindings[index] = updated
                return updated
        return None

    async def list_user_wristband_bindings(
        self,
        *,
        username: str | None = None,
        wristband_id: str | None = None,
        gym_id: str | None = None,
        active_only: bool | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[UserWristbandBindingSummary]:
        async with self._lock:
            items = list(self._user_wristband_bindings)

        if username is not None:
            items = [item for item in items if item.username == username]
        if wristband_id is not None:
            items = [item for item in items if item.wristband_id == wristband_id]
        if gym_id is not None:
            items = [item for item in items if item.gym_id == gym_id]
        if active_only is not None:
            items = [item for item in items if item.is_active == active_only]

        return items[offset : offset + limit]

    async def create_workout_session(
        self,
        *,
        username: str,
        wristband_id: str,
        gym_id: str,
        status: WorkoutSessionStatus,
        source: WorkoutSessionSource,
        started_at: str,
        ended_at: str | None,
        equipment_ids: list[str],
        segments: list[WorkoutSessionSegment],
        metrics: WorkoutSessionMetrics,
        notes: str | None,
    ) -> WorkoutSessionSummary:
        async with self._lock:
            now = _now_iso()
            normalized_segments = _normalize_segments(segments)
            normalized_equipment_ids = _normalize_equipment_ids(
                equipment_ids=equipment_ids,
                segments=normalized_segments,
            )
            session = WorkoutSessionSummary(
                session_id=str(uuid4()),
                username=username,
                wristband_id=wristband_id,
                gym_id=gym_id,
                status=status,
                source=source,
                started_at=_normalize_iso(started_at) or started_at,
                ended_at=_normalize_iso(ended_at),
                duration_s=_session_duration_s(
                    started_at=_normalize_iso(started_at) or started_at,
                    ended_at=_normalize_iso(ended_at),
                ),
                equipment_ids=normalized_equipment_ids,
                segments=normalized_segments,
                metrics=metrics,
                notes=notes,
                created_at=now,
                updated_at=now,
            )
            self._workout_sessions[session.session_id] = session
            return session

    async def update_workout_session(
        self,
        *,
        session_id: str,
        status: WorkoutSessionStatus | None = None,
        ended_at: str | None = None,
        equipment_ids: list[str] | None = None,
        segments: list[WorkoutSessionSegment] | None = None,
        metrics: WorkoutSessionMetrics | None = None,
        notes: str | None = None,
    ) -> WorkoutSessionSummary | None:
        async with self._lock:
            existing = self._workout_sessions.get(session_id)
            if existing is None:
                return None
            next_segments = (
                _normalize_segments(segments)
                if segments is not None
                else existing.segments
            )
            next_equipment_ids = _normalize_equipment_ids(
                equipment_ids=equipment_ids if equipment_ids is not None else existing.equipment_ids,
                segments=next_segments,
            )
            next_ended_at = _normalize_iso(ended_at) if ended_at is not None else existing.ended_at
            updated = existing.model_copy(
                update={
                    "status": status or existing.status,
                    "ended_at": next_ended_at,
                    "duration_s": _session_duration_s(
                        started_at=existing.started_at,
                        ended_at=next_ended_at,
                    ),
                    "equipment_ids": next_equipment_ids,
                    "segments": next_segments,
                    "metrics": metrics or existing.metrics,
                    "notes": notes if notes is not None else existing.notes,
                    "updated_at": _now_iso(),
                }
            )
            self._workout_sessions[session_id] = updated
            return updated

    async def get_workout_session(
        self,
        *,
        session_id: str,
    ) -> WorkoutSessionSummary | None:
        async with self._lock:
            return self._workout_sessions.get(session_id)

    async def list_workout_sessions(
        self,
        *,
        username: str | None = None,
        wristband_id: str | None = None,
        gym_id: str | None = None,
        status: WorkoutSessionStatus | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[WorkoutSessionSummary]:
        async with self._lock:
            items = sorted(
                self._workout_sessions.values(),
                key=lambda item: (item.started_at, item.session_id),
                reverse=True,
            )

        if username is not None:
            items = [item for item in items if item.username == username]
        if wristband_id is not None:
            items = [item for item in items if item.wristband_id == wristband_id]
        if gym_id is not None:
            items = [item for item in items if item.gym_id == gym_id]
        if status is not None:
            items = [item for item in items if item.status == status]
        if start is not None:
            start_ts = _parse_isoformat(start)
            items = [item for item in items if _parse_isoformat(item.started_at) >= start_ts]
        if end is not None:
            end_ts = _parse_isoformat(end)
            items = [
                item
                for item in items
                if _parse_isoformat(item.ended_at or item.started_at) <= end_ts
            ]

        return items[offset : offset + limit]

    async def create_ai_report(
        self,
        *,
        user_id: str,
        status: AiReportStatus,
        start: str,
        end: str,
        summary_title: str | None,
        summary: str | None,
        insights: list[str],
        recommendations: list[str],
        evidence_session_ids: list[str],
        raw_markdown: str | None,
        error_message: str | None,
    ) -> AiReportDetail:
        async with self._lock:
            now = _now_iso()
            report = AiReportDetail(
                report_id=str(uuid4()),
                user_id=user_id,
                status=status,
                start=_normalize_iso(start) or start,
                end=_normalize_iso(end) or end,
                created_at=now,
                updated_at=now,
                finished_at=None,
                summary_title=summary_title,
                summary=summary,
                insights=list(insights),
                recommendations=list(recommendations),
                evidence_session_ids=list(evidence_session_ids),
                raw_markdown=raw_markdown,
                error_message=error_message,
            )
            self._ai_reports[report.report_id] = report
            return report

    async def update_ai_report(
        self,
        *,
        report_id: str,
        status: AiReportStatus | None = None,
        summary_title: str | None = None,
        summary: str | None = None,
        insights: list[str] | None = None,
        recommendations: list[str] | None = None,
        evidence_session_ids: list[str] | None = None,
        raw_markdown: str | None = None,
        error_message: str | None = None,
        finished_at: str | None = None,
    ) -> AiReportDetail | None:
        async with self._lock:
            existing = self._ai_reports.get(report_id)
            if existing is None:
                return None
            updated = existing.model_copy(
                update={
                    "status": status or existing.status,
                    "summary_title": summary_title if summary_title is not None else existing.summary_title,
                    "summary": summary if summary is not None else existing.summary,
                    "insights": list(insights) if insights is not None else existing.insights,
                    "recommendations": list(recommendations) if recommendations is not None else existing.recommendations,
                    "evidence_session_ids": list(evidence_session_ids)
                    if evidence_session_ids is not None
                    else existing.evidence_session_ids,
                    "raw_markdown": raw_markdown if raw_markdown is not None else existing.raw_markdown,
                    "error_message": error_message if error_message is not None else existing.error_message,
                    "finished_at": _normalize_iso(finished_at) if finished_at is not None else existing.finished_at,
                    "updated_at": _now_iso(),
                }
            )
            self._ai_reports[report_id] = updated
            return updated

    async def claim_ai_report(
        self,
        *,
        report_id: str,
        from_status: AiReportStatus,
        to_status: AiReportStatus,
    ) -> AiReportDetail | None:
        async with self._lock:
            existing = self._ai_reports.get(report_id)
            if existing is None or existing.status != from_status:
                return None
            updated = existing.model_copy(
                update={
                    "status": to_status,
                    "updated_at": _now_iso(),
                }
            )
            self._ai_reports[report_id] = updated
            return updated

    async def get_ai_report(self, *, report_id: str) -> AiReportDetail | None:
        async with self._lock:
            return self._ai_reports.get(report_id)

    async def list_ai_reports(
        self,
        *,
        user_id: str | None = None,
        status: AiReportStatus | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[AiReportSummary]:
        async with self._lock:
            items = sorted(
                self._ai_reports.values(),
                key=lambda item: (item.created_at or "", item.report_id),
                reverse=True,
            )

        if user_id is not None:
            items = [item for item in items if item.user_id == user_id]
        if status is not None:
            items = [item for item in items if item.status == status]
        if start is not None:
            start_ts = _parse_isoformat(start)
            items = [item for item in items if _parse_isoformat(item.start) >= start_ts]
        if end is not None:
            end_ts = _parse_isoformat(end)
            items = [item for item in items if _parse_isoformat(item.end) <= end_ts]

        return [
            AiReportSummary.model_validate(item.model_dump())
            for item in items[offset : offset + limit]
        ]

    async def create_refresh_session(
        self,
        *,
        session_id: str,
        username: str,
        refresh_jti: str,
        expires_at_s: int,
    ) -> StoredRefreshSession:
        session = StoredRefreshSession(
            session_id=session_id,
            username=username,
            refresh_jti=refresh_jti,
            expires_at_s=expires_at_s,
        )
        async with self._lock:
            self._refresh_sessions[session_id] = session
        return session

    async def get_refresh_session(self, *, session_id: str) -> StoredRefreshSession | None:
        async with self._lock:
            return self._refresh_sessions.get(session_id)

    async def update_refresh_session(
        self,
        *,
        session_id: str,
        refresh_jti: str,
        expires_at_s: int,
    ) -> StoredRefreshSession | None:
        async with self._lock:
            existing = self._refresh_sessions.get(session_id)
            if existing is None:
                return None
            updated = existing.model_copy(
                update={
                    "refresh_jti": refresh_jti,
                    "expires_at_s": expires_at_s,
                }
            )
            self._refresh_sessions[session_id] = updated
            return updated

    async def delete_refresh_session(self, *, session_id: str) -> bool:
        async with self._lock:
            return self._refresh_sessions.pop(session_id, None) is not None

    async def delete_expired_refresh_sessions(self, *, now_s: int) -> int:
        async with self._lock:
            expired_ids = [
                session_id
                for session_id, session in self._refresh_sessions.items()
                if session.expires_at_s <= now_s
            ]
            for session_id in expired_ids:
                self._refresh_sessions.pop(session_id, None)
            return len(expired_ids)

    async def upsert_device(
        self,
        *,
        gym_id: str,
        device_type: str,
        device_id: str,
        status: str,
        online: bool,
        last_seen_ts: int | None,
        payload: dict,
    ) -> DeviceSummary:
        async with self._lock:
            key = _device_key(gym_id, device_type, device_id)
            existing = self._devices.get(key)
            if existing is not None and _is_stale_device_update(existing.last_seen_ts, last_seen_ts):
                return existing

            device = DeviceSummary(
                gym_id=gym_id,
                device_type=device_type,
                device_id=device_id,
                gateway_id=(
                    existing.gateway_id
                    if existing is not None and existing.gateway_id is not None
                    else _resolve_gateway_id(device_type=device_type, device_id=device_id, payload=payload)
                ),
                display_name=existing.display_name if existing is not None else None,
                location=existing.location if existing is not None else None,
                metadata=existing.metadata if existing is not None else None,
                status=status,
                online=online,
                last_seen_ts=last_seen_ts,
                last_payload=payload,
                registered_at=existing.registered_at if existing is not None else None,
                updated_at=existing.updated_at if existing is not None else None,
            )
            self._devices[key] = device
            return device

    async def update_wristband_equipment_binding(
        self,
        *,
        gym_id: str,
        wristband_id: str,
        equipment_id: str | None,
        payload: dict,
    ) -> DeviceSummary:
        async with self._lock:
            key = _device_key(gym_id, "wristband", wristband_id)
            existing = self._devices.get(key)
            now = _now_iso()
            binding_payload = {
                **(existing.last_payload if existing is not None else {}),
                **payload,
                "current_equipment_id": equipment_id,
            }
            device = DeviceSummary(
                gym_id=gym_id,
                device_type="wristband",
                device_id=wristband_id,
                gateway_id=existing.gateway_id if existing is not None else None,
                display_name=existing.display_name if existing is not None else None,
                location=existing.location if existing is not None else None,
                metadata=existing.metadata if existing is not None else None,
                status=existing.status if existing is not None else "registered",
                online=existing.online if existing is not None else False,
                last_seen_ts=existing.last_seen_ts if existing is not None else None,
                last_payload=binding_payload,
                registered_at=existing.registered_at if existing is not None else now,
                updated_at=now,
            )
            self._devices[key] = device
            return device

    async def register_device(
        self,
        *,
        gym_id: str,
        device_type: str,
        device_id: str,
        gateway_id: str | None,
        display_name: str | None,
        location: str | None,
        metadata: dict,
    ) -> DeviceSummary:
        async with self._lock:
            existing = self._find_device_by_id_locked(device_id)
            key = _device_key(gym_id, device_type, device_id)
            if existing is not None and _device_key(existing.gym_id, existing.device_type, existing.device_id) != key:
                raise ValueError("device_id already exists with different gym_id or device_type")

            now = _now_iso()
            snapshot = self._devices.get(key)
            device = DeviceSummary(
                gym_id=gym_id,
                device_type=device_type,
                device_id=device_id,
                gateway_id=gateway_id,
                display_name=display_name,
                location=location,
                metadata=metadata,
                status=snapshot.status if snapshot is not None else "registered",
                online=snapshot.online if snapshot is not None else False,
                last_seen_ts=snapshot.last_seen_ts if snapshot is not None else None,
                last_payload=snapshot.last_payload if snapshot is not None else {},
                registered_at=(
                    snapshot.registered_at
                    if snapshot is not None and snapshot.registered_at is not None
                    else now
                ),
                updated_at=now,
            )
            self._devices[key] = device
            return device

    async def update_device_registration(
        self,
        *,
        device_id: str,
        updates: dict,
    ) -> DeviceSummary | None:
        async with self._lock:
            existing = self._find_device_by_id_locked(device_id)
            if existing is None:
                return None

            updated = existing.model_copy(
                update={
                    "gateway_id": updates.get("gateway_id", existing.gateway_id),
                    "display_name": updates.get("display_name", existing.display_name),
                    "location": updates.get("location", existing.location),
                    "metadata": updates.get("metadata", existing.metadata),
                    "updated_at": _now_iso(),
                }
            )
            self._devices[_device_key(existing.gym_id, existing.device_type, existing.device_id)] = updated
            return updated

    async def delete_device(
        self,
        *,
        device_id: str,
    ) -> bool:
        async with self._lock:
            existing = self._find_device_by_id_locked(device_id)
            if existing is None:
                return False
            self._devices.pop(_device_key(existing.gym_id, existing.device_type, existing.device_id), None)
            return True

    async def add_alert(
        self,
        *,
        gym_id: str,
        device_type: str,
        device_id: str,
        level: str,
        code: str,
        message: str,
        priority: str | None,
        triggered_at: str,
        payload: dict,
    ) -> AlertRecord:
        async with self._lock:
            for existing in self._alerts:
                if (
                    existing.gym_id == gym_id
                    and existing.device_type == device_type
                    and existing.device_id == device_id
                    and existing.code == code
                    and existing.triggered_at == triggered_at
                    and existing.message == message
                ):
                    return existing

            alert = AlertRecord(
                id=self._next_alert_id,
                gym_id=gym_id,
                device_type=device_type,
                device_id=device_id,
                level=level,
                code=code,
                message=message,
                priority=priority,
                triggered_at=triggered_at,
                payload=payload,
            )
            self._next_alert_id += 1
            self._alerts.insert(0, alert)
            return alert

    async def record_binding_event(
        self,
        *,
        gym_id: str,
        wristband_id: str,
        equipment_id: str,
        action: str,
        reason: str | None,
        ts: int | None,
    ) -> bool:
        async with self._lock:
            duration_s = None
            event_time = _isoformat_from_ts(ts)
            for existing in self._bindings:
                if (
                    existing.gym_id == gym_id
                    and existing.wristband_id == wristband_id
                    and existing.equipment_id == equipment_id
                    and existing.action == action
                    and existing.reason == reason
                    and existing.ts == event_time
                ):
                    return False

            if action == "unbind":
                for existing in self._bindings:
                    if (
                        existing.gym_id == gym_id
                        and existing.wristband_id == wristband_id
                        and existing.equipment_id == equipment_id
                        and existing.action == "bind"
                    ):
                        duration_s = int(
                            (
                                _parse_isoformat(event_time)
                                - _parse_isoformat(existing.ts)
                            ).total_seconds()
                        )
                        break

            event = BindingEventRecord(
                id=self._next_binding_id,
                wristband_id=wristband_id,
                equipment_id=equipment_id,
                gym_id=gym_id,
                action=action,
                reason=reason,
                ts=event_time,
                duration_s=duration_s,
            )
            self._next_binding_id += 1
            self._bindings.insert(0, event)
            return True

    async def record_telemetry(
        self,
        *,
        gym_id: str,
        device_type: str,
        device_id: str,
        payload: dict,
    ) -> None:
        async with self._lock:
            self._telemetry.insert(
                0,
                TelemetryRecord(
                    ts=_isoformat_from_ts(payload.get("ts")),
                    gym_id=gym_id,
                    device_type=device_type,
                    device_id=device_id,
                    payload=payload,
                ),
            )

    async def list_devices(
        self,
        device_type: str | None = None,
        status: str | None = None,
    ) -> list[DeviceSummary]:
        async with self._lock:
            devices = list(self._devices.values())

        if device_type is not None:
            devices = [item for item in devices if item.device_type == device_type]
        if status is not None:
            devices = [item for item in devices if item.status == status]

        return sorted(devices, key=lambda item: (item.device_type, item.device_id))

    async def get_device(self, *, device_id: str) -> DeviceSummary | None:
        async with self._lock:
            return self._find_device_by_id_locked(device_id)
        return None

    async def list_alerts(
        self,
        level: str | None = None,
        is_ack: bool | None = None,
        device_id: str | None = None,
    ) -> list[AlertRecord]:
        async with self._lock:
            alerts = list(self._alerts)

        if level is not None:
            alerts = [item for item in alerts if item.level == level]
        if is_ack is not None:
            alerts = [item for item in alerts if item.is_ack == is_ack]
        if device_id is not None:
            alerts = [item for item in alerts if item.device_id == device_id]

        return alerts

    async def get_alert(self, *, alert_id: int) -> AlertRecord | None:
        async with self._lock:
            for alert in self._alerts:
                if alert.id == alert_id:
                    return alert
        return None

    async def ack_alert(self, *, alert_id: int) -> AlertRecord | None:
        async with self._lock:
            for index, alert in enumerate(self._alerts):
                if alert.id == alert_id:
                    updated = alert.model_copy(update={"is_ack": True})
                    self._alerts[index] = updated
                    return updated
        return None

    async def batch_ack_alerts(self, *, alert_ids: list[int]) -> list[AlertRecord]:
        updated: list[AlertRecord] = []
        async with self._lock:
            id_set = set(alert_ids)
            for index, alert in enumerate(self._alerts):
                if alert.id in id_set and not alert.is_ack:
                    patched = alert.model_copy(update={"is_ack": True})
                    self._alerts[index] = patched
                    updated.append(patched)
                elif alert.id in id_set:
                    updated.append(alert)
        return sorted(updated, key=lambda item: item.id)

    async def list_telemetry(
        self,
        *,
        device_type: str,
        device_id: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[TelemetryRecord]:
        async with self._lock:
            items = [
                item
                for item in self._telemetry
                if item.device_type == device_type and item.device_id == device_id
            ]

        if start is not None:
            start_ts = _parse_isoformat(start)
            items = [item for item in items if _parse_isoformat(item.ts) >= start_ts]
        if end is not None:
            end_ts = _parse_isoformat(end)
            items = [item for item in items if _parse_isoformat(item.ts) <= end_ts]

        return items[offset : offset + limit]

    async def list_binding_events(
        self,
        *,
        wristband_id: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[BindingEventRecord]:
        async with self._lock:
            items = [item for item in self._bindings if item.wristband_id == wristband_id]

        if start is not None:
            start_ts = _parse_isoformat(start)
            items = [item for item in items if _parse_isoformat(item.ts) >= start_ts]
        if end is not None:
            end_ts = _parse_isoformat(end)
            items = [item for item in items if _parse_isoformat(item.ts) <= end_ts]

        return items[offset : offset + limit]

    async def aggregate_env_telemetry(
        self,
        *,
        device_id: str,
        interval: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[EnvTelemetryAggregateRecord]:
        records = await self.list_telemetry(
            device_type="env",
            device_id=device_id,
            start=start,
            end=end,
            limit=100000,
            offset=0,
        )
        return aggregate_env_records(records, interval, limit=limit, offset=offset)

    async def create_device_config_command(
        self,
        *,
        gateway_id: str,
        gym_id: str,
        device_type: str,
        device_id: str,
        topic: str,
        qos: int,
        retain: bool,
        payload: dict,
        max_attempts: int,
        retry_backoff_s: int,
        next_retry_at: str,
        expires_at: str,
    ) -> DeviceConfigCommandRecord:
        async with self._lock:
            now = _isoformat_from_ts(None)
            record = DeviceConfigCommandRecord(
                command_id=str(uuid4()),
                gateway_id=gateway_id,
                gym_id=gym_id,
                device_type=device_type,
                device_id=device_id,
                topic=topic,
                qos=qos,
                retain=retain,
                payload=payload,
                status="pending",
                attempt_count=0,
                max_attempts=max_attempts,
                retry_backoff_s=retry_backoff_s,
                next_retry_at=next_retry_at,
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
            self._device_config_commands[record.command_id] = record
            return record

    async def list_pending_device_config_commands(
        self,
        *,
        gateway_id: str,
        limit: int = 100,
        delivery_lease_s: int = 15,
    ) -> list[DeviceConfigCommandRecord]:
        async with self._lock:
            now = _isoformat_from_ts(None)
            now_dt = _parse_isoformat(now)

            for command_id, item in list(self._device_config_commands.items()):
                expired = _expire_command_record(item, now=now, now_dt=now_dt)
                if expired is not None:
                    self._device_config_commands[command_id] = expired

            eligible = sorted(
                [
                    item
                    for item in self._device_config_commands.values()
                    if item.gateway_id == gateway_id
                    and item.status == "pending"
                    and _parse_isoformat(item.expires_at) > now_dt
                    and _parse_isoformat(item.next_retry_at or item.created_at) <= now_dt
                    and (
                        item.leased_until is None
                        or _parse_isoformat(item.leased_until) <= now_dt
                    )
                ],
                key=lambda item: (item.created_at, item.command_id),
            )[:limit]

            claimed: list[DeviceConfigCommandRecord] = []
            for item in eligible:
                updated = item.model_copy(
                    update={
                        "attempt_count": item.attempt_count + 1,
                        "last_attempt_at": now,
                        "leased_until": _advance_iso(now, delivery_lease_s),
                        "updated_at": now,
                    }
                )
                self._device_config_commands[item.command_id] = updated
                claimed.append(updated)

        return claimed

    async def get_device_config_command(
        self,
        *,
        command_id: str,
    ) -> DeviceConfigCommandRecord | None:
        async with self._lock:
            return self._device_config_commands.get(command_id)

    async def update_device_config_command_result(
        self,
        *,
        gateway_id: str,
        command_id: str,
        result: GatewayCommandResultRequest,
    ) -> DeviceConfigCommandRecord | None:
        async with self._lock:
            existing = self._device_config_commands.get(command_id)
            if existing is None or existing.gateway_id != gateway_id:
                return None
            if existing.status in {"succeeded", "failed", "timed_out"}:
                return existing

            new_status = result.status
            next_retry_at = existing.next_retry_at
            leased_until = None

            if result.status == "failed":
                reported_at_dt = _parse_isoformat(result.reported_at)
                if reported_at_dt >= _parse_isoformat(existing.expires_at):
                    new_status = "timed_out"
                    next_retry_at = None
                elif existing.attempt_count >= existing.max_attempts:
                    new_status = "failed"
                    next_retry_at = None
                else:
                    new_status = "pending"
                    next_retry_at = _advance_iso(result.reported_at, existing.retry_backoff_s)
            else:
                next_retry_at = None

            updated = existing.model_copy(
                update={
                    "status": new_status,
                    "updated_at": result.reported_at,
                    "result_detail": result.detail,
                    "result_payload": result.result_payload,
                    "next_retry_at": next_retry_at,
                    "leased_until": leased_until,
                }
            )
            self._device_config_commands[command_id] = updated
            return updated

    def _find_device_by_id_locked(self, device_id: str) -> DeviceSummary | None:
        for device in self._devices.values():
            if device.device_id == device_id:
                return device
        return None

    def _ensure_active_user_wristband_binding_conflict_locked(
        self,
        *,
        username: str,
        wristband_id: str,
    ) -> None:
        for binding in self._user_wristband_bindings:
            if not binding.is_active:
                continue
            if binding.username == username:
                raise ValueError("user already has an active wristband binding")
            if binding.wristband_id == wristband_id:
                raise ValueError("wristband already bound to another user")

def coerce_online(status: str) -> bool:
    return status not in {"offline", "disconnected"}


def _is_stale_device_update(existing_ts: int | None, incoming_ts: int | None) -> bool:
    if existing_ts is None:
        return False
    if incoming_ts is None:
        return True
    return incoming_ts < existing_ts


def payload_ts(payload: dict) -> int | None:
    value = payload.get("ts")
    return value if isinstance(value, int) else None


def payload_triggered_at(payload: dict) -> str:
    if isinstance(payload.get("triggered_at"), str):
        return payload["triggered_at"]

    ts = payload_ts(payload)
    if ts is None:
        return datetime.now(UTC).isoformat()

    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def _device_key(gym_id: str, device_type: str, device_id: str) -> str:
    return f"{gym_id}:{device_type}:{device_id}"


def _resolve_gateway_id(*, device_type: str, device_id: str, payload: dict) -> str | None:
    payload_gateway_id = payload.get("gateway_id")
    if isinstance(payload_gateway_id, str) and payload_gateway_id:
        return payload_gateway_id
    if device_type == "gateway":
        return device_id
    return None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _isoformat_from_ts(value: int | None) -> str:
    if isinstance(value, int):
        return datetime.fromtimestamp(value, tz=UTC).isoformat()
    return datetime.now(UTC).isoformat()


def _parse_isoformat(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _advance_iso(value: str, seconds: int) -> str:
    return (_parse_isoformat(value) + timedelta(seconds=seconds)).isoformat()


def _expire_command_record(
    item: DeviceConfigCommandRecord,
    *,
    now: str,
    now_dt: datetime,
) -> DeviceConfigCommandRecord | None:
    if item.status != "pending":
        return None
    if _parse_isoformat(item.expires_at) > now_dt:
        return None
    return item.model_copy(
        update={
            "status": "timed_out",
            "updated_at": now,
            "leased_until": None,
            "next_retry_at": None,
            "result_detail": item.result_detail or "command expired before successful delivery",
        }
    )


def _normalize_segments(segments: list[WorkoutSessionSegment] | None) -> list[WorkoutSessionSegment]:
    normalized: list[WorkoutSessionSegment] = []
    for segment in segments or []:
        duration_s = segment.duration_s
        normalized_started_at = _normalize_iso(segment.started_at) or segment.started_at
        normalized_ended_at = _normalize_iso(segment.ended_at)
        if duration_s is None and normalized_ended_at is not None:
            duration_s = _session_duration_s(
                started_at=normalized_started_at,
                ended_at=normalized_ended_at,
            )
        normalized.append(
            segment.model_copy(
                update={
                    "started_at": normalized_started_at,
                    "ended_at": normalized_ended_at,
                    "duration_s": duration_s,
                }
            )
        )
    return normalized


def _normalize_equipment_ids(
    *,
    equipment_ids: list[str] | None,
    segments: list[WorkoutSessionSegment],
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in equipment_ids or []:
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    for segment in segments:
        if segment.equipment_id in seen:
            continue
        seen.add(segment.equipment_id)
        normalized.append(segment.equipment_id)
    return normalized


def _session_duration_s(*, started_at: str, ended_at: str | None) -> int | None:
    if ended_at is None:
        return None
    return max(int((_parse_isoformat(ended_at) - _parse_isoformat(started_at)).total_seconds()), 0)


def _normalize_iso(value: str | None) -> str | None:
    if value is None:
        return None
    return _parse_isoformat(value).isoformat()
