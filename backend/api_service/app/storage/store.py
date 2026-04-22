from __future__ import annotations

from typing import Protocol

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


class Store(Protocol):
    async def initialize(self) -> None: ...

    async def close(self) -> None: ...

    async def list_users(self) -> list[UserSummary]: ...

    async def get_user(
        self,
        *,
        username: str,
    ) -> StoredUser | None: ...

    async def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        role: UserRole,
        gym_ids: list[str],
        device_ids: list[str],
    ) -> UserSummary: ...

    async def update_user(
        self,
        *,
        username: str,
        password_hash: str | None = None,
        role: UserRole | None = None,
        gym_ids: list[str] | None = None,
        device_ids: list[str] | None = None,
    ) -> UserSummary | None: ...

    async def delete_user(
        self,
        *,
        username: str,
    ) -> bool: ...

    async def create_user_wristband_binding(
        self,
        *,
        username: str,
        wristband_id: str,
        gym_id: str,
        bound_at: str | None,
        source: BindingSource,
        note: str | None,
    ) -> UserWristbandBindingSummary: ...

    async def end_user_wristband_binding(
        self,
        *,
        binding_id: int,
        unbound_at: str | None,
        note: str | None,
    ) -> UserWristbandBindingSummary | None: ...

    async def list_user_wristband_bindings(
        self,
        *,
        username: str | None = None,
        wristband_id: str | None = None,
        gym_id: str | None = None,
        active_only: bool | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[UserWristbandBindingSummary]: ...

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
    ) -> WorkoutSessionSummary: ...

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
    ) -> WorkoutSessionSummary | None: ...

    async def get_workout_session(
        self,
        *,
        session_id: str,
    ) -> WorkoutSessionSummary | None: ...

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
    ) -> list[WorkoutSessionSummary]: ...

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
    ) -> AiReportDetail: ...

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
    ) -> AiReportDetail | None: ...

    async def claim_ai_report(
        self,
        *,
        report_id: str,
        from_status: AiReportStatus,
        to_status: AiReportStatus,
    ) -> AiReportDetail | None: ...

    async def get_ai_report(
        self,
        *,
        report_id: str,
    ) -> AiReportDetail | None: ...

    async def list_ai_reports(
        self,
        *,
        user_id: str | None = None,
        status: AiReportStatus | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[AiReportSummary]: ...

    async def create_refresh_session(
        self,
        *,
        session_id: str,
        username: str,
        refresh_jti: str,
        expires_at_s: int,
    ) -> StoredRefreshSession: ...

    async def get_refresh_session(
        self,
        *,
        session_id: str,
    ) -> StoredRefreshSession | None: ...

    async def update_refresh_session(
        self,
        *,
        session_id: str,
        refresh_jti: str,
        expires_at_s: int,
    ) -> StoredRefreshSession | None: ...

    async def delete_refresh_session(
        self,
        *,
        session_id: str,
    ) -> bool: ...

    async def delete_expired_refresh_sessions(
        self,
        *,
        now_s: int,
    ) -> int: ...

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
    ) -> DeviceSummary: ...

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
    ) -> DeviceSummary: ...

    async def update_device_registration(
        self,
        *,
        device_id: str,
        updates: dict,
    ) -> DeviceSummary | None: ...

    async def delete_device(
        self,
        *,
        device_id: str,
    ) -> bool: ...

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
    ) -> AlertRecord: ...

    async def record_binding_event(
        self,
        *,
        gym_id: str,
        wristband_id: str,
        equipment_id: str,
        action: str,
        reason: str | None,
        ts: int | None,
    ) -> None: ...

    async def record_telemetry(
        self,
        *,
        gym_id: str,
        device_type: str,
        device_id: str,
        payload: dict,
    ) -> None: ...

    async def list_devices(
        self,
        device_type: str | None = None,
        status: str | None = None,
    ) -> list[DeviceSummary]: ...

    async def get_device(
        self,
        *,
        device_id: str,
    ) -> DeviceSummary | None: ...

    async def list_alerts(
        self,
        level: str | None = None,
        is_ack: bool | None = None,
        device_id: str | None = None,
    ) -> list[AlertRecord]: ...

    async def get_alert(
        self,
        *,
        alert_id: int,
    ) -> AlertRecord | None: ...

    async def ack_alert(
        self,
        *,
        alert_id: int,
    ) -> AlertRecord | None: ...

    async def batch_ack_alerts(
        self,
        *,
        alert_ids: list[int],
    ) -> list[AlertRecord]: ...

    async def list_telemetry(
        self,
        *,
        device_type: str,
        device_id: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[TelemetryRecord]: ...

    async def list_binding_events(
        self,
        *,
        wristband_id: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[BindingEventRecord]: ...

    async def aggregate_env_telemetry(
        self,
        *,
        device_id: str,
        interval: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[EnvTelemetryAggregateRecord]: ...

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
    ) -> DeviceConfigCommandRecord: ...

    async def list_pending_device_config_commands(
        self,
        *,
        gateway_id: str,
        limit: int = 100,
        delivery_lease_s: int = 15,
    ) -> list[DeviceConfigCommandRecord]: ...

    async def get_device_config_command(
        self,
        *,
        command_id: str,
    ) -> DeviceConfigCommandRecord | None: ...

    async def update_device_config_command_result(
        self,
        *,
        gateway_id: str,
        command_id: str,
        result: GatewayCommandResultRequest,
    ) -> DeviceConfigCommandRecord | None: ...
