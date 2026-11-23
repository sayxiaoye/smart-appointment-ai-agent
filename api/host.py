"""
主持人 API

提供主持人信息和排班查询接口
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel

router = APIRouter(prefix="/api/hosts", tags=["主持人管理"])


class HostResponse(BaseModel):
    """主持人信息响应"""
    id: int
    name: str
    host_types: List[str]
    host_type_labels: List[str]
    specialty: str


class ScheduleResponse(BaseModel):
    """排班信息响应"""
    id: int
    host_id: int
    start_time: str
    end_time: str
    status: str
    appointment_id: int | None = None


def _to_host_response(host: dict) -> HostResponse:
    from config.constants import host_type_label
    host_types = host.get("host_types") or []
    return HostResponse(
        id=host["id"],
        name=host["name"],
        host_types=host_types,
        host_type_labels=[host_type_label(item) for item in host_types],
        specialty=host.get("specialty") or "",
    )


@router.get("/", response_model=List[HostResponse], summary="获取所有主持人")
async def get_all_hosts():
    try:
        from services.host_service import HostService
        host_service = HostService()
        return [_to_host_response(host) for host in host_service.get_all_hosts()]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取主持人信息失败: {str(exc)}")


def resolve_schedule_date(date: Optional[str]):
    """把 YYYY-MM-DD 转成北京时间当天零点。空值表示今天。"""
    from config.time_config import time_config

    if not date:
        return time_config.today()
    parsed = time_config.parse_datetime(date, "%Y-%m-%d")
    if parsed is None:
        raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD")
    return parsed


async def get_all_hosts_schedule(date: Optional[str] = None):
    try:
        from services.host_service import HostService

        host_service = HostService()
        day = resolve_schedule_date(date)
        schedules_data = []
        for host in host_service.get_all_hosts():
            busy_periods = []
            for sched in host_service.get_host_schedules(host["id"], day):
                if sched.get("status") == "busy":
                    busy_periods.append({
                        "start": sched["start_time"].strftime("%H:%M") if hasattr(sched["start_time"], "strftime") else str(sched["start_time"]),
                        "end": sched["end_time"].strftime("%H:%M") if hasattr(sched["end_time"], "strftime") else str(sched["end_time"]),
                        "appointment_id": sched.get("appointment_id"),
                    })
            schedules_data.append({
                "host_id": host["id"],
                "host_name": host["name"],
                "date": day.strftime("%Y-%m-%d"),
                "busy_periods": busy_periods,
            })
        return schedules_data
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取排班信息失败: {str(exc)}")


@router.get("/schedules", summary="按日期获取所有主持人排班")
async def get_hosts_schedule_by_date(date: Optional[str] = Query(None, description="YYYY-MM-DD，缺省为今天")):
    return await get_all_hosts_schedule(date)


@router.get("/schedules/today", summary="获取所有主持人今日排班")
async def get_all_hosts_schedule_today():
    return await get_all_hosts_schedule(None)


@router.get("/{host_id}/schedule", response_model=List[ScheduleResponse], summary="获取主持人排班")
async def get_host_schedule(host_id: int):
    try:
        from services.host_service import HostService
        from config.time_config import time_config

        host_service = HostService()
        host = host_service.get_host_by_id(host_id)
        if not host:
            raise HTTPException(status_code=404, detail="主持人不存在")

        schedules = host_service.get_host_schedules(host_id, time_config.today())
        return [
            ScheduleResponse(
                id=sched["id"],
                host_id=sched["host_id"],
                start_time=sched["start_time"].strftime("%H:%M"),
                end_time=sched["end_time"].strftime("%H:%M"),
                status=sched["status"],
                appointment_id=sched.get("appointment_id"),
            )
            for sched in schedules
        ]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取排班信息失败: {str(exc)}")


@router.get("/{host_id}", response_model=HostResponse, summary="获取单个主持人信息")
async def get_host(host_id: int):
    try:
        from services.host_service import HostService
        host = HostService().get_host_by_id(host_id)
        if not host:
            raise HTTPException(status_code=404, detail="主持人不存在")
        return _to_host_response(host)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取主持人信息失败: {str(exc)}")
