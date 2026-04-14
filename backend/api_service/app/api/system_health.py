from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_event_store
from app.models.system_health import GatewayHealthDetail, GatewayHealthReportRequest, GatewayHealthSummary
from app.storage.store import Store


router = APIRouter(prefix="/api/v1/system/health", tags=["system-health"])


@router.post("/report", response_model=GatewayHealthDetail)
async def report_gateway_health(
    payload: GatewayHealthReportRequest,
    store: Store = Depends(get_event_store),
) -> GatewayHealthDetail:
    return await store.upsert_gateway_health_report(report=payload)


@router.get("", response_model=list[GatewayHealthSummary])
async def list_gateway_health(
    gym_id: str | None = Query(default=None),
    gateway_id: str | None = Query(default=None),
    component_type: str | None = Query(default=None),
    overall_status: str | None = Query(default=None),
    store: Store = Depends(get_event_store),
) -> list[GatewayHealthSummary]:
    return await store.list_gateway_health_summaries(
        gym_id=gym_id,
        gateway_id=gateway_id,
        component_type=component_type,
        overall_status=overall_status,
    )


@router.get("/{gateway_id}", response_model=GatewayHealthDetail)
async def get_gateway_health(
    gateway_id: str,
    store: Store = Depends(get_event_store),
) -> GatewayHealthDetail:
    detail = await store.get_gateway_health_detail(gateway_id=gateway_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="gateway health not found")
    return detail
