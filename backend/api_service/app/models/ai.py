from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.user import _USERNAME_PATTERN

AiReportStatus = Literal["queued", "generating", "completed", "failed"]

class AiAnalyzeRequest(BaseModel):
    user_id: str = Field(min_length=3, max_length=64, pattern=_USERNAME_PATTERN)
    start: str
    end: str


class AiReportSummary(BaseModel):
    report_id: str
    user_id: str
    status: AiReportStatus
    start: str
    end: str
    created_at: str | None = None
    updated_at: str | None = None
    finished_at: str | None = None
    summary_title: str | None = None


class AiReportDetail(AiReportSummary):
    summary: str | None = None
    insights: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    evidence_session_ids: list[str] = Field(default_factory=list)
    raw_markdown: str | None = None
    error_message: str | None = None


class ReservedApiResponse(BaseModel):
    status: str
    detail: str
    reserved_for: str
    docs_ref: str
    payload: dict[str, Any] | None = None
