"""
偏好管理器 - 专门负责管理用户的偏好数据

职责：
1. 从预约数据中提取和更新用户偏好
2. 管理主持人偏好、时间偏好、游戏偏好等
3. 提供偏好数据的查询和统计
4. 处理偏好的变化和趋势分析
"""

from typing import Dict, Any, Optional
from datetime import datetime
import logging


class PreferenceManager:
    """偏好管理器 - 负责用户偏好的管理和分析"""

    def __init__(self, behavior_service=None):
        self.behavior_service = behavior_service
        self.logger = logging.getLogger(__name__)

    @property
    def behavior_db(self):
        """为了向后兼容，提供behavior_db属性"""
        if hasattr(self, "behavior_service") and self.behavior_service:
            return self.behavior_service.user_behavior_repo
        return None

    def update_preferences_from_appointment(self, user_id: str, action_data: Dict[str, Any], host_id: int = None):
        """从预约数据中更新当前用户的主持人、游戏、主持类型和时间偏好。"""
        try:
            if host_id:
                self.update_host_preference(user_id, host_id)

            if action_data.get("start_time"):
                self.update_time_preference(user_id, action_data["start_time"])

            if action_data.get("duration"):
                self.update_duration_preference(user_id, action_data["duration"])

            game = action_data.get("game") or action_data.get("project")
            if game:
                self.update_game_preference(user_id, game)

            if action_data.get("host_type"):
                self.update_host_type_preference(user_id, action_data["host_type"])
        except Exception as e:
            self.logger.error(f"更新用户偏好失败: {str(e)}")

    def update_host_preference(self, user_id: str, host_id: int):
        try:
            self.behavior_db.update_user_preference(user_id, "host", str(host_id))
            self.logger.info(f"更新主持人偏好: {host_id}")
        except Exception as e:
            self.logger.error(f"更新主持人偏好失败: {str(e)}")

    def update_time_preference(self, user_id: str, start_time: str):
        try:
            start_datetime = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            hour = start_datetime.hour

            if 6 <= hour < 12:
                time_period = "上午"
            elif 12 <= hour < 18:
                time_period = "下午"
            else:
                time_period = "晚上"

            self.behavior_db.update_user_preference(user_id, "time", time_period)
            self.logger.info(f"更新时间偏好: {time_period}")
        except Exception as e:
            self.logger.error(f"更新时间偏好失败: {str(e)}")

    def update_duration_preference(self, user_id: str, duration: Any):
        try:
            duration_str = str(duration)
            self.behavior_db.update_user_preference(user_id, "duration", duration_str)
            self.logger.info(f"更新时长偏好: {duration_str}")
        except Exception as e:
            self.logger.error(f"更新时长偏好失败: {str(e)}")

    def update_game_preference(self, user_id: str, game: str):
        try:
            self.behavior_db.update_user_preference(user_id, "game", game)
            self.logger.info(f"更新游戏偏好: {game}")
        except Exception as e:
            self.logger.error(f"更新游戏偏好失败: {str(e)}")

    def update_host_type_preference(self, user_id: str, host_type: str):
        try:
            self.behavior_db.update_user_preference(user_id, "host_type", host_type)
            self.logger.info(f"更新主持类型偏好: {host_type}")
        except Exception as e:
            self.logger.error(f"更新主持类型偏好失败: {str(e)}")

    def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        try:
            rows = self.behavior_db.get_user_preferences(user_id)
            if isinstance(rows, dict):
                return rows
            mapped: Dict[str, Any] = {}
            for row in rows or []:
                key = row.get("preference_type")
                if key and key not in mapped:
                    mapped[key] = row.get("preference_value")
            return mapped
        except Exception as e:
            self.logger.error(f"获取用户偏好失败: {str(e)}")
            return {}

    def get_preferred_host_id(self, user_id: str) -> Optional[int]:
        try:
            host_id = self.get_user_preferences(user_id).get("host")
            return int(host_id) if host_id else None
        except Exception as e:
            self.logger.error(f"获取偏好主持人ID失败: {str(e)}")
            return None

    def get_preferred_time_period(self, user_id: str) -> Optional[str]:
        try:
            return self.get_user_preferences(user_id).get("time")
        except Exception as e:
            self.logger.error(f"获取偏好时间段失败: {str(e)}")
            return None

    def get_preferred_service(self, user_id: str) -> Optional[str]:
        try:
            return self.get_user_preferences(user_id).get("game")
        except Exception as e:
            self.logger.error(f"获取偏好服务失败: {str(e)}")
            return None

    def get_preference_summary(self, user_id: str) -> Dict[str, Any]:
        try:
            preferences = self.get_user_preferences(user_id)
            summary = {
                "has_host_preference": bool(preferences.get("host")),
                "has_time_preference": bool(preferences.get("time")),
                "has_game_preference": bool(preferences.get("game")),
                "has_duration_preference": bool(preferences.get("duration")),
                "preference_count": len([value for value in preferences.values() if value]),
            }
            if preferences.get("host"):
                summary["preferred_host_id"] = int(preferences["host"])
            if preferences.get("time"):
                summary["preferred_time"] = preferences["time"]
            if preferences.get("game"):
                summary["preferred_game"] = preferences["game"]
            if preferences.get("duration"):
                summary["preferred_duration"] = preferences["duration"]
            return summary
        except Exception as e:
            self.logger.error(f"获取偏好摘要失败: {str(e)}")
            return {}

    def clear_preference(self, user_id: str, preference_type: str):
        try:
            self.behavior_db.update_user_preference(user_id, preference_type, None)
            self.logger.info(f"清除偏好: {preference_type}")
        except Exception as e:
            self.logger.error(f"清除偏好失败: {str(e)}")

    def clear_all_preferences(self, user_id: str):
        try:
            for pref_type in ("host", "time", "duration", "game", "host_type"):
                self.clear_preference(user_id, pref_type)
            self.logger.info("清除所有用户偏好")
        except Exception as e:
            self.logger.error(f"清除所有偏好失败: {str(e)}")
