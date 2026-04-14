from __future__ import annotations

from pydantic import BaseModel


class DeviceOtaRequest(BaseModel):
    firmware_url: str
    version: str
    sha256: str
    force: bool = False
