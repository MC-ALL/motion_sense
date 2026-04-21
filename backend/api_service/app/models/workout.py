from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.user import UserSummary


BindingSource = Literal["manual", "imported", "aggregated"]
WorkoutSessionStatus = Literal["open", "completed", "cancelled"]
WorkoutSessionSource = Literal["manual", "imported", "aggregated"]


class UserWristbandBindingSummary(BaseModel):
    id: int
    username: str
    wristband_id: str
    gym_id: str
    is_active: bool
    bound_at: str
    unbound_at: str | None = None
    source: BindingSource = "manual"
    note: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class UserWristbandBindingOverviewResponse(BaseModel):
    active_bindings: list[UserWristbandBindingSummary] = Field(default_factory=list)
    binding_history: list[UserWristbandBindingSummary] = Field(default_factory=list)


class UserWristbandBindingCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    wristband_id: str = Field(min_length=1, max_length=128)
    gym_id: str = Field(min_length=1, max_length=128)
    bound_at: str | None = None
    source: BindingSource = "manual"
    note: str | None = Field(default=None, max_length=500)


class UserWristbandBindingUnbindRequest(BaseModel):
    unbound_at: str | None = None
    note: str | None = Field(default=None, max_length=500)


class WorkoutSessionMetrics(BaseModel):
    avg_heart_rate: float | None = None
    max_heart_rate: int | None = None
    total_steps: int | None = None
    total_rep_count: int | None = None
    total_energy_wh: float | None = None
    alert_count: int | None = None


class WorkoutSessionSegment(BaseModel):
    equipment_id: str = Field(min_length=1, max_length=128)
    started_at: str
    ended_at: str | None = None
    duration_s: int | None = Field(default=None, ge=0)
    rep_count: int | None = Field(default=None, ge=0)
    energy_wh: float | None = Field(default=None, ge=0)


class WorkoutSessionSummary(BaseModel):
    session_id: str
    username: str
    wristband_id: str
    gym_id: str
    status: WorkoutSessionStatus
    source: WorkoutSessionSource = "manual"
    started_at: str
    ended_at: str | None = None
    duration_s: int | None = None
    equipment_ids: list[str] = Field(default_factory=list)
    segments: list[WorkoutSessionSegment] = Field(default_factory=list)
    metrics: WorkoutSessionMetrics = Field(default_factory=WorkoutSessionMetrics)
    notes: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class WorkoutSessionCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    wristband_id: str = Field(min_length=1, max_length=128)
    gym_id: str = Field(min_length=1, max_length=128)
    status: WorkoutSessionStatus = "completed"
    source: WorkoutSessionSource = "manual"
    started_at: str
    ended_at: str | None = None
    equipment_ids: list[str] = Field(default_factory=list)
    segments: list[WorkoutSessionSegment] = Field(default_factory=list)
    metrics: WorkoutSessionMetrics = Field(default_factory=WorkoutSessionMetrics)
    notes: str | None = Field(default=None, max_length=1000)


class WorkoutSessionUpdateRequest(BaseModel):
    status: WorkoutSessionStatus | None = None
    ended_at: str | None = None
    equipment_ids: list[str] | None = None
    segments: list[WorkoutSessionSegment] | None = None
    metrics: WorkoutSessionMetrics | None = None
    notes: str | None = Field(default=None, max_length=1000)


class WorkoutSessionAggregateRequest(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=64)
    wristband_id: str | None = Field(default=None, min_length=1, max_length=128)
    gym_id: str | None = Field(default=None, min_length=1, max_length=128)
    start: str | None = None
    end: str | None = None


class WorkoutSessionAggregateResult(BaseModel):
    processed_bindings: int = 0
    created_sessions: int = 0
    updated_sessions: int = 0
    skipped_segments: int = 0
    sessions: list[WorkoutSessionSummary] = Field(default_factory=list)


class UserTrainingProfileSummary(BaseModel):
    total_sessions: int = 0
    completed_sessions: int = 0
    open_sessions: int = 0
    cancelled_sessions: int = 0
    total_duration_s: int = 0
    total_rep_count: int = 0
    total_energy_wh: float = 0
    avg_heart_rate: float | None = None
    max_heart_rate: int | None = None
    equipment_ids: list[str] = Field(default_factory=list)
    last_session_at: str | None = None


class UserTrainingProfileResponse(BaseModel):
    user: UserSummary
    query_start: str | None = None
    query_end: str | None = None
    active_binding: UserWristbandBindingSummary | None = None
    recent_bindings: list[UserWristbandBindingSummary] = Field(default_factory=list)
    recent_sessions: list[WorkoutSessionSummary] = Field(default_factory=list)
    summary: UserTrainingProfileSummary = Field(default_factory=UserTrainingProfileSummary)
