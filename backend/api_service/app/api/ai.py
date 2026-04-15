from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_rest_user
from app.models.ai import AiAnalyzeRequest, ReservedApiResponse


router = APIRouter(
    prefix="/api/v1/ai",
    tags=["ai"],
    dependencies=[Depends(require_rest_user)],
)


def _reserved_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=501,
        detail=ReservedApiResponse(
            status="reserved",
            detail=detail,
            reserved_for="phase_2_ai_integration",
            docs_ref="docs/05-后台端.md#4-ai-运动分析",
        ).model_dump(),
    )


@router.post("/analyze", response_model=ReservedApiResponse)
async def analyze_ai_report(_: AiAnalyzeRequest) -> ReservedApiResponse:
    raise _reserved_error("AI 分析接口已预留，当前版本未接入模型调用与流式输出")


@router.get("/reports", response_model=ReservedApiResponse)
async def list_ai_reports() -> ReservedApiResponse:
    raise _reserved_error("AI 报告列表接口已预留，当前版本未实现存储与查询")


@router.get("/reports/{report_id}", response_model=ReservedApiResponse)
async def get_ai_report(report_id: str) -> ReservedApiResponse:
    raise _reserved_error(f"AI 报告详情接口已预留，当前版本未实现报告读取: {report_id}")
