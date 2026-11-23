"""
预约服务层

职责：
1. 封装预约相关的数据库操作
2. 处理预约业务逻辑
3. 提供预约相关的数据服务
"""

import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from db.db_router import DatabaseRouter
import logging

logger = logging.getLogger(__name__)


class AppointmentService:
    """预约服务类"""

    def __init__(self, db_path: str = "sqlite:///data/smart_appointment.db"):
        self.db_router = DatabaseRouter(db_path)
        self.host_repo = self.db_router.hosts

    def save_appointment(self, host_id, start_time: datetime,
                        end_time: datetime, appointment_history: Dict[str, Any],
                        session_id: str) -> bool:
        """保存预约。自助场次不占用主持人档期。"""
        try:
            if host_id in (None, "", "None"):
                logger.info(
                    "自助场次已确认：游戏=%s，时间=%s 到 %s",
                    appointment_history.get("game"), start_time, end_time,
                )
                return True

            appointment_id = int(time.time() * 1000)
            self.host_repo.add_schedule(
                host_id=int(host_id),
                start_time=start_time,
                end_time=end_time,
                status="busy",
                appointment_id=appointment_id,
            )
            logger.info("预约已保存：主持人ID=%s, 时间=%s 到 %s", host_id, start_time, end_time)
            return True
        except Exception as exc:
            logger.error("保存预约失败：%s", exc)
            return False

    def get_host_by_id(self, host_id: int) -> Optional[Dict[str, Any]]:
        try:
            return self.host_repo.get_host_by_id(host_id)
        except Exception as exc:
            logger.error("获取主持人信息失败：%s", exc)
            return None

    def get_host_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        try:
            return self.host_repo.get_host_by_name(name)
        except Exception as exc:
            logger.error("获取主持人信息失败：%s", exc)
            return None

    def get_all_hosts(self) -> List[Dict[str, Any]]:
        try:
            return self.host_repo.get_all_hosts()
        except Exception as exc:
            logger.error("获取主持人列表失败：%s", exc)
            return []

    def get_hosts_by_type(self, host_type: str) -> List[Dict[str, Any]]:
        try:
            return self.host_repo.get_hosts_by_type(host_type)
        except Exception as exc:
            logger.error("按主持类型获取主持人失败：%s", exc)
            return []

    def get_host_schedules(self, host_id: int, date) -> List[Dict[str, Any]]:
        try:
            return self.host_repo.get_host_schedules(host_id, date)
        except Exception as exc:
            logger.error("获取主持人排班失败：%s", exc)
            return []

    def is_host_available(self, host_id: int, start_time: datetime, end_time: datetime) -> bool:
        try:
            return self.host_repo.is_host_available(host_id, start_time, end_time)
        except Exception as exc:
            logger.error("检查主持人可用性失败：%s", exc)
            return False

    def get_all_specialties(self) -> List[str]:
        try:
            return self.host_repo.get_all_specialties()
        except Exception as exc:
            logger.error("获取主持人专长失败：%s", exc)
            return []
