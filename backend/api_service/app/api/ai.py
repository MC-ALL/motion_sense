from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_event_store, is_unrestricted_user, require_rest_user
from app.models.ai import AiAnalyzeRequest, AiReportDetail, AiReportStatus, AiReportSummary
from app.models.auth import AuthUser
from app.models.user import StoredUser
from app.storage.store import Store


router = APIRouter(
    prefix="/api/v1/ai",
    tags=["ai"],
    dependencies=[Depends(require_rest_user)],
)


@router.post(
    "/analyze",
    response_model=AiReportDetail,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_ai_report(
    payload: AiAnalyzeRequest,
    user: AuthUser = Depends(require_rest_user),
    store: Store = Depends(get_event_store),
) -> AiReportDetail:
    target_user = await store.get_user(username=payload.user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="user not found")
    _ensure_ai_report_scope(current_user=user, target_user=target_user)
    if target_user.role != "student":
        raise HTTPException(status_code=409, detail="ai reports currently support student users only")

    evidence_sessions = await store.list_workout_sessions(
        username=target_user.username,
        start=payload.start,
        end=payload.end,
        limit=5000,
        offset=0,
    )
    return await store.create_ai_report(
        user_id=target_user.username,
        status="queued",
        start=payload.start,
        end=payload.end,
        summary_title=f"{target_user.username} 训练分析待生成",
        summary="报告已入队，等待后续 AI 生成流程写入正式内容。",
        insights=[],
        recommendations=[],
        evidence_session_ids=[item.session_id for item in evidence_sessions],
        raw_markdown=None,
        error_message=None,
    )


@router.get("/reports", response_model=list[AiReportSummary], response_model_exclude_none=True)
async def list_ai_reports(
    user_id: str | None = Query(default=None),
    status: AiReportStatus | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    user: AuthUser = Depends(require_rest_user),
    store: Store = Depends(get_event_store),
) -> list[AiReportSummary]:
    if user_id is not None:
        target_user = await store.get_user(username=user_id)
        if target_user is None:
            raise HTTPException(status_code=404, detail="user not found")
        _ensure_ai_report_scope(current_user=user, target_user=target_user)
        return await store.list_ai_reports(
            user_id=user_id,
            status=status,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
        )

    if is_unrestricted_user(user):
        return await store.list_ai_reports(
            user_id=None,
            status=status,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
        )

    if user.role == "student":
        return await store.list_ai_reports(
            user_id=user.username,
            status=status,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
        )

    items = await store.list_ai_reports(
        user_id=None,
        status=status,
        start=start,
        end=end,
        limit=5000,
        offset=0,
    )
    visible_items: list[AiReportSummary] = []
    for item in items:
        target_user = await store.get_user(username=item.user_id)
        if target_user is None:
            continue
        if _user_can_access_ai_report_target(current_user=user, target_user=target_user):
            visible_items.append(item)
    return visible_items[offset : offset + limit]


@router.get("/reports/{report_id}", response_model=AiReportDetail, response_model_exclude_none=True)
async def get_ai_report(
    report_id: str,
    user: AuthUser = Depends(require_rest_user),
    store: Store = Depends(get_event_store),
) -> AiReportDetail:
    report = await store.get_ai_report(report_id=report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="ai report not found")
    target_user = await store.get_user(username=report.user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="user not found")
    _ensure_ai_report_scope(current_user=user, target_user=target_user)
    return report


def _ensure_ai_report_scope(*, current_user: AuthUser, target_user: StoredUser) -> None:
    if _user_can_access_ai_report_target(current_user=current_user, target_user=target_user):
        return
    raise HTTPException(status_code=403, detail="ai report access forbidden")


def _user_can_access_ai_report_target(*, current_user: AuthUser, target_user: StoredUser) -> bool:
    if is_unrestricted_user(current_user):
        return True
    if current_user.username == target_user.username:
        return True
    if current_user.role != "teacher":
        return False

    teacher_gym_ids = set(current_user.gym_ids)
    teacher_device_ids = set(current_user.device_ids)
    target_gym_ids = set(target_user.gym_ids)
    target_device_ids = set(target_user.device_ids)
    if teacher_gym_ids.intersection(target_gym_ids):
        return True
    if teacher_device_ids.intersection(target_device_ids):
        return True
    return False
