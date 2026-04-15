from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_rest_user
from app.models.ai import ReservedApiResponse
from app.models.ota import DeviceOtaRequest


router = APIRouter(
    prefix="/api/v1",
    tags=["ota"],
    dependencies=[Depends(require_rest_user)],
)


def _reserved_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=501,
        detail=ReservedApiResponse(
            status="reserved",
            detail=detail,
            reserved_for="phase_2_ota_integration",
            docs_ref="docs/07-通讯接口定义.md#28-ota-触发ota",
        ).model_dump(),
    )


@router.post("/devices/{device_id}/ota", response_model=ReservedApiResponse)
async def create_device_ota_task(
    device_id: str,
    _: DeviceOtaRequest,
) -> ReservedApiResponse:
    raise _reserved_error(
        f"OTA 接口已预留，当前版本未实现任务下发、网关转发与设备升级确认: {device_id}"
    )


@router.get("/ota/tasks", response_model=ReservedApiResponse)
async def list_ota_tasks() -> ReservedApiResponse:
    raise _reserved_error("OTA 任务列表接口已预留，当前版本未实现任务存储与查询")


@router.get("/ota/tasks/{task_id}", response_model=ReservedApiResponse)
async def get_ota_task(task_id: str) -> ReservedApiResponse:
    raise _reserved_error(f"OTA 任务详情接口已预留，当前版本未实现任务读取: {task_id}")
