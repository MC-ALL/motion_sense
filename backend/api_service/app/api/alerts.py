from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_event_store
from app.models.ingest import AlertBatchAckRequest, AlertBatchAckResult, AlertRecord
from app.storage.store import Store


router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertRecord])
async def list_alerts(
    level: str | None = Query(default=None),
    is_ack: bool | None = Query(default=None),
    store: Store = Depends(get_event_store),
) -> list[AlertRecord]:
    return await store.list_alerts(level=level, is_ack=is_ack)


@router.get("/{alert_id}", response_model=AlertRecord)
async def get_alert(
    alert_id: int,
    store: Store = Depends(get_event_store),
) -> AlertRecord:
    alert = await store.get_alert(alert_id=alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    return alert


@router.patch("/{alert_id}/ack", response_model=AlertRecord)
async def ack_alert(
    alert_id: int,
    store: Store = Depends(get_event_store),
) -> AlertRecord:
    alert = await store.ack_alert(alert_id=alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    return alert


@router.post("/batch-ack", response_model=AlertBatchAckResult)
async def batch_ack_alerts(
    payload: AlertBatchAckRequest,
    store: Store = Depends(get_event_store),
) -> AlertBatchAckResult:
    items = await store.batch_ack_alerts(alert_ids=payload.ids)
    return AlertBatchAckResult(updated=len(items), items=items)
