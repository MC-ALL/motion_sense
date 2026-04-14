from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_ingest_service
from app.models.ingest import IngestBatch, IngestBatchAccepted
from app.services.ingest_service import IngestService


router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


@router.post("/batch", response_model=IngestBatchAccepted)
async def ingest_batch(
    payload: IngestBatch,
    ingest_service: IngestService = Depends(get_ingest_service),
) -> IngestBatchAccepted:
    accepted = await ingest_service.ingest_batch(payload)
    return IngestBatchAccepted(accepted=accepted)
