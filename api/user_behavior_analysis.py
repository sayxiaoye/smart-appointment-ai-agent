"""
用户行为分析API - 只返回当前登录用户的数据
"""

from fastapi import APIRouter, Request
from typing import Optional
from pydantic import BaseModel

from api.auth import require_login

router = APIRouter(prefix="/api/user-behavior", tags=["用户行为分析"])
router_underscore = APIRouter(prefix="/api/user_behavior", tags=["用户行为分析"])


class UserAnalysisResponse(BaseModel):
    """用户分析响应"""
    favorite_host_id: Optional[int] = None
    favorite_host_name: Optional[str] = None
    favorite_service: Optional[str] = None
    favorite_duration: Optional[int] = None
    total_appointments: int = 0
    days_since_last_appointment: Optional[int] = None
    should_send_reminder: bool = False


async def get_user_analysis(user_id: str) -> UserAnalysisResponse:
    """获取指定用户的行为分析数据"""
    try:
        from agents.user_behavior_agent import UserBehaviorAgent

        agent = UserBehaviorAgent()
        analysis = agent.get_user_analysis(user_id)

        if not analysis:
            return UserAnalysisResponse()

        host_name = None
        if analysis.get("favorite_host_id"):
            from db import HostDBRouter
            db = HostDBRouter()
            host_info = db.get_host_by_id(analysis["favorite_host_id"])
            if host_info:
                host_name = host_info.get("name")

        return UserAnalysisResponse(
            favorite_host_id=analysis.get("favorite_host_id"),
            favorite_host_name=host_name,
            favorite_service=analysis.get("favorite_service"),
            favorite_duration=analysis.get("favorite_duration"),
            total_appointments=analysis.get("total_appointments", 0),
            days_since_last_appointment=analysis.get("days_since_last_appointment"),
            should_send_reminder=analysis.get("should_send_reminder", False),
        )
    except Exception as e:
        import logging
        logging.error(f"获取用户分析数据失败: {e}")
        return UserAnalysisResponse()


def _failure_message(display_name: str) -> str:
    name = (display_name or "").strip() or "您"
    return f"尊敬的{name}，您好！系统暂时无法查询主持人时间，请稍后再试或直接联系我们预约。"


@router.get("/analysis", response_model=UserAnalysisResponse)
async def get_current_user_analysis(request: Request):
    user = require_login(request)
    return await get_user_analysis(str(user["id"]))


@router.get("/dashboard_data", response_model=UserAnalysisResponse)
async def get_dashboard_data(request: Request):
    user = require_login(request)
    return await get_user_analysis(str(user["id"]))


@router_underscore.get("/dashboard_data", response_model=UserAnalysisResponse)
async def get_dashboard_data_underscore(request: Request):
    user = require_login(request)
    return await get_user_analysis(str(user["id"]))


class ReminderRequest(BaseModel):
    """旧客户端可能仍提交 user_id，服务端忽略该字段。"""
    user_id: Optional[str] = None


class ReminderResponse(BaseModel):
    message: str
    host_available_times: Optional[list] = None


@router.post("/send-reminder", response_model=ReminderResponse, summary="发送回访提醒")
async def send_reminder(request: Request, body: Optional[ReminderRequest] = None):
    user = require_login(request)
    try:
        from agents.user_behavior_agent import UserBehaviorAgent

        agent = UserBehaviorAgent()
        result = await agent.get_reminder_with_schedule(
            str(user["id"]), display_name=user["display_name"]
        )
        return ReminderResponse(
            message=result["message"],
            host_available_times=result["host_available_times"],
        )
    except Exception as e:
        import logging
        logging.error(f"生成回访提醒失败: {e}")
        return ReminderResponse(message=_failure_message(user["display_name"]), host_available_times=[])
