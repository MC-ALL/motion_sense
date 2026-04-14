from __future__ import annotations

from pydantic import BaseModel


class AiAnalyzeRequest(BaseModel):
    user_id: str
    start: str
    end: str


class ReservedApiResponse(BaseModel):
    status: str
    detail: str
    reserved_for: str
    docs_ref: str
