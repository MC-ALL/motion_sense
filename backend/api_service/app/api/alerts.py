from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import (
    ensure_alert_scope,
    filter_alerts_for_user,
    get_event_store,
    require_admin_or_teacher_user,
    require_rest_user,
)
from app.models.auth import AuthUser
from app.models.ingest import AlertBatchAckRequest, AlertBatchAckResult, AlertRecord
from app.storage.store import Store


router = APIRouter(
    prefix="/api/v1/alerts",
    tags=["alerts"],
    dependencies=[Depends(require_rest_user)],
)


@router.get("", response_model=list[AlertRecord])
async def list_alerts(
    level: str | None = Query(default=None),
    is_ack: bool | None = Query(default=None),
    device_id: str | None = Query(default=None),
    user: AuthUser = Depends(require_rest_user),
    store: Store = Depends(get_event_store),
) -> list[AlertRecord]:
    alerts = await store.list_alerts(level=level, is_ack=is_ack, device_id=device_id)
    return filter_alerts_for_user(user, alerts)


@router.get("/{alert_id}", response_model=AlertRecord)
async def get_alert(
    alert_id: int,
    user: AuthUser = Depends(require_rest_user),
    store: Store = Depends(get_event_store),
) -> AlertRecord:
    alert = await store.get_alert(alert_id=alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    ensure_alert_scope(user, alert)
    return alert


@router.patch("/{alert_id}/ack", response_model=AlertRecord)
async def ack_alert(
    alert_id: int,
    user: AuthUser = Depends(require_admin_or_teacher_user),
    store: Store = Depends(get_event_store),
) -> AlertRecord:
    alert = await store.get_alert(alert_id=alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    ensure_alert_scope(user, alert)
    updated = await store.ack_alert(alert_id=alert_id)
    assert updated is not None
    return updated


@router.post("/batch-ack", response_model=AlertBatchAckResult)
async def batch_ack_alerts(
    payload: AlertBatchAckRequest,
    user: AuthUser = Depends(require_admin_or_teacher_user),
    store: Store = Depends(get_event_store),
) -> AlertBatchAckResult:
    alerts = [alert for alert_id in payload.ids if (alert := await store.get_alert(alert_id=alert_id)) is not None]
    allowed_ids = [alert.id for alert in alerts if _can_ack_alert(user, alert)]
    items = await store.batch_ack_alerts(alert_ids=allowed_ids)
    return AlertBatchAckResult(updated=len(items), items=items)


def _can_ack_alert(user: AuthUser, alert: AlertRecord) -> bool:
    try:
        ensure_alert_scope(user, alert)
    except HTTPException:
        return False
    return True
