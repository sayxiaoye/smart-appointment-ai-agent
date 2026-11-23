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
    
    def __init__(self, behavior_service = None):
        """
        初始化偏好管理器
        
        Args:
            behavior_service: 用户行为服务实例
        """
        self.behavior_service = behavior_service
        self.logger = logging.getLogger(__name__)
    
    @property
    def behavior_db(self):
        """为了向后兼容，提供behavior_db属性"""
        if hasattr(self, 'behavior_service') and self.behavior_service:
            # 返回一个适配器，将调用转发到behavior_service
            return self.behavior_service.user_behavior_repo
        else:
            # 如果没有service，返回None（应该在组件初始化时提供适当的处理）
            return None
    
    def update_preferences_from_appointment(self, action_data: Dict[str, Any], host_id: int = None):
        """从预约数据中更新主持人、游戏、主持类型和时间偏好。"""
        try:
            if host_id:
                self.update_host_preference(host_id)

            if action_data.get("start_time"):
                self.update_time_preference(action_data["start_time"])

            if action_data.get("duration"):
                self.update_duration_preference(action_data["duration"])

            game = action_data.get("game") or action_data.get("project")
            if game:
                self.update_game_preference(game)

            if action_data.get("host_type"):
                self.update_host_type_preference(action_data["host_type"])
        except Exception as e:
            self.logger.error(f"更新用户偏好失败: {str(e)}")

    def update_host_preference(self, host_id: int):
        """更新主持人偏好"""
        try:
            self.behavior_db.update_user_preference("host", str(host_id))
            self.logger.info(f"更新主持人偏好: {host_id}")
        except Exception as e:
            self.logger.error(f"更新主持人偏好失败: {str(e)}")
    
    def update_time_preference(self, start_time: str):
        """
        更新时间偏好
        
        Args:
            start_time: 开始时间字符串
        """
        try:
            start_datetime = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            hour = start_datetime.hour
            
            if 6 <= hour < 12:
                time_period = '上午'
            elif 12 <= hour < 18:
                time_period = '下午'
            else:
                time_period = '晚上'
            
            self.behavior_db.update_user_preference('time', time_period)
            self.logger.info(f"更新时间偏好: {time_period}")
        except Exception as e:
            self.logger.error(f"更新时间偏好失败: {str(e)}")
    
    def update_duration_preference(self, duration: Any):
        """
        更新服务时长偏好
        
        Args:
            duration: 服务时长
        """
        try:
            duration_str = str(duration)
            self.behavior_db.update_user_preference('duration', duration_str)
            self.logger.info(f"更新时长偏好: {duration_str}")
        except Exception as e:
            self.logger.error(f"更新时长偏好失败: {str(e)}")
    
    def update_game_preference(self, game: str):
        """更新游戏偏好"""
        try:
            self.behavior_db.update_user_preference("game", game)
            self.logger.info(f"更新游戏偏好: {game}")
        except Exception as e:
            self.logger.error(f"更新游戏偏好失败: {str(e)}")

    def update_host_type_preference(self, host_type: str):
        """更新主持类型偏好"""
        try:
            self.behavior_db.update_user_preference("host_type", host_type)
            self.logger.info(f"更新主持类型偏好: {host_type}")
        except Exception as e:
            self.logger.error(f"更新主持类型偏好失败: {str(e)}")
    
    def get_user_preferences(self) -> Dict[str, Any]:
        """
        获取用户所有偏好
        
        Returns:
            Dict: 用户偏好数据
        """
        try:
            return self.behavior_db.get_user_preferences()
        except Exception as e:
            self.logger.error(f"获取用户偏好失败: {str(e)}")
            return {}
    
    def get_preferred_host_id(self) -> Optional[int]:
        """获取偏好的主持人ID"""
        try:
            preferences = self.get_user_preferences()
            host_id = preferences.get("host")
            return int(host_id) if host_id else None
        except Exception as e:
            self.logger.error(f"获取偏好主持人ID失败: {str(e)}")
            return None
    
    def get_preferred_time_period(self) -> Optional[str]:
        """
        获取偏好的时间段
        
        Returns:
            str: 时间段偏好
        """
        try:
            preferences = self.get_user_preferences()
            return preferences.get('time')
        except Exception as e:
            self.logger.error(f"获取偏好时间段失败: {str(e)}")
            return None
    
    def get_preferred_service(self) -> Optional[str]:
        """
        获取偏好的服务项目
        
        Returns:
            str: 服务项目偏好
        """
        try:
            preferences = self.get_user_preferences()
            return preferences.get('game')
        except Exception as e:
            self.logger.error(f"获取偏好服务失败: {str(e)}")
            return None
    
    def get_preference_summary(self) -> Dict[str, Any]:
        """
        获取偏好摘要信息
        
        Returns:
            Dict: 偏好摘要
        """
        try:
            preferences = self.get_user_preferences()
            
            summary = {
                'has_host_preference': bool(preferences.get('host')),
                'has_time_preference': bool(preferences.get('time')),
                'has_game_preference': bool(preferences.get('game')),
                'has_duration_preference': bool(preferences.get('duration')),
                'preference_count': len([v for v in preferences.values() if v])
            }

            if preferences.get('host'):
                summary['preferred_host_id'] = int(preferences['host'])
            if preferences.get('time'):
                summary['preferred_time'] = preferences['time']
            if preferences.get('game'):
                summary['preferred_game'] = preferences['game']
            if preferences.get('duration'):
                summary['preferred_duration'] = preferences['duration']
            
            return summary
            
        except Exception as e:
            self.logger.error(f"获取偏好摘要失败: {str(e)}")
            return {}
    
    def clear_preference(self, preference_type: str):
        """
        清除特定类型的偏好
        
        Args:
            preference_type: 偏好类型
        """
        try:
            self.behavior_db.update_user_preference(preference_type, None)
            self.logger.info(f"清除偏好: {preference_type}")
        except Exception as e:
            self.logger.error(f"清除偏好失败: {str(e)}")
    
    def clear_all_preferences(self):
        """清除所有偏好"""
        try:
            preference_types = ['host', 'time', 'duration', 'game', 'host_type']
            for pref_type in preference_types:
                self.clear_preference(pref_type)
            self.logger.info("清除所有用户偏好")
        except Exception as e:
            self.logger.error(f"清除所有偏好失败: {str(e)}")
