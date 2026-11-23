"""
预约数据库操作器

负责处理预约相关的数据库操作
注意：现在通过Services层访问数据库，符合分层架构
"""

from typing import Dict, Any
from datetime import datetime
from config.time_config import time_config
from config.constants import busy_periods_dict


class AppointmentDatabase:
    """预约数据库操作器"""
    
    def __init__(self):
        # 延迟导入Services避免循环依赖
        self._appointment_service = None
        self._user_behavior_service = None
    
    @property
    def appointment_service(self):
        """懒加载预约服务"""
        if self._appointment_service is None:
            from services.appointment_service import AppointmentService
            self._appointment_service = AppointmentService()
        return self._appointment_service
    
    @property 
    def user_behavior_service(self):
        """懒加载用户行为服务"""
        if self._user_behavior_service is None:
            from services.user_behavior_service import UserBehaviorService
            self._user_behavior_service = UserBehaviorService()
        return self._user_behavior_service
    
    def save_appointment(self, host_id, start_time: datetime,
                        end_time: datetime, appointment_history: Dict[str, Any],
                        session_id: str) -> bool:
        """保存预约信息到数据库"""
        try:
            success = self.appointment_service.save_appointment(
                host_id, start_time, end_time, appointment_history, session_id
            )
            if success:
                self._record_user_behavior(start_time, end_time, host_id, appointment_history, session_id)
            return success
        except Exception as exc:
            print(f"保存预约信息到数据库失败：{exc}")
            return False

    def update_memory_schedule(self, host_id, start_time: datetime, end_time: datetime):
        """更新内存中的主持人忙碌时间段。自助场次不写入。"""
        if host_id in (None, "", "None"):
            return
        busy_period = {
            "start": time_config.format_datetime(start_time, "%H:%M"),
            "end": time_config.format_datetime(end_time, "%H:%M")
        }
        busy_periods_dict.setdefault(host_id, []).append(busy_period)

    def _record_user_behavior(self, start_time: datetime, end_time: datetime,
                            host_id, appointment_history: Dict[str, Any],
                            session_id: str):
        """记录用户预约行为"""
        try:
            stored_host_id = None if host_id in (None, "", "None") else int(host_id)
            action_data = {
                "start_time": time_config.format_datetime(start_time, "%Y-%m-%d %H:%M:%S"),
                "end_time": time_config.format_datetime(end_time, "%Y-%m-%d %H:%M:%S"),
                "duration": int((end_time - start_time).total_seconds() / 60),
                "game": appointment_history.get("game"),
                "host_type": appointment_history.get("host_type"),
                "player_count": appointment_history.get("player_count"),
                "preference": appointment_history.get("preference", ""),
                "host_id": stored_host_id,
                "host_name": self._booked_host_name(stored_host_id, appointment_history),
            }
            self.user_behavior_service.record_behavior(
                user_id="default_user",
                action_type="appointment",
                action_data=action_data,
                host_id=stored_host_id,
                session_id=session_id,
            )
            
        except Exception as behavior_error:
            print(f"记录用户行为失败（但预约仍然成功）：{behavior_error}")

    def _booked_host_name(self, host_id, appointment_history: Dict[str, Any]):
        """记录实际订到的主持人，而不是用户随口说的称呼。"""
        if host_id not in (None, "", "None"):
            host = self.appointment_service.get_host_by_id(int(host_id))
            if host and host.get("name"):
                return host.get("name")
        name = appointment_history.get("host_name")
        if name in (None, "", "未知", "无"):
            return None
        return name
