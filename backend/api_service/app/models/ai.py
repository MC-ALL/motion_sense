from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AiAnalyzeRequest(BaseModel):
    user_id: str
    start: str
    end: str


class AiAnalyzeReservedPayload(BaseModel):
    page: Literal["training_archive_ai_launcher"] = "training_archive_ai_launcher"
    accepted_request: AiAnalyzeRequest
    next_routes: list[str] = Field(default_factory=lambda: ["/training-archive", "/ai-reports"])
    state: Literal["reserved"] = "reserved"


class AiReportListFiltersPlaceholder(BaseModel):
    user_id_query_param: Literal["user_id"] = "user_id"
    status_query_param: Literal["status"] = "status"
    start_query_param: Literal["start"] = "start"
    end_query_param: Literal["end"] = "end"
    status_options: list[str] = Field(default_factory=lambda: ["queued", "generating", "completed", "failed"])
    window_options: list[str] = Field(default_factory=lambda: ["7d", "30d", "all"])


class AiReportsListReservedPayload(BaseModel):
    page: Literal["ai_reports_list"] = "ai_reports_list"
    state: Literal["reserved"] = "reserved"
    filters: AiReportListFiltersPlaceholder = Field(default_factory=AiReportListFiltersPlaceholder)
    items: list[dict[str, Any]] = Field(default_factory=list)
    suggested_entrypoint: Literal["/training-archive"] = "/training-archive"


class AiReportDetailReservedPayload(BaseModel):
    page: Literal["ai_report_detail"] = "ai_report_detail"
    state: Literal["reserved"] = "reserved"
    report_id: str
    sections: list[str] = Field(
        default_factory=lambda: ["overview", "summary", "insights", "recommendations", "evidence"]
    )


class ReservedApiResponse(BaseModel):
    status: str
    detail: str
    reserved_for: str
    docs_ref: str
    payload: dict[str, Any] | None = None
