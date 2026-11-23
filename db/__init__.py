"""
Database Module

数据库模块，包含：
- 数据模型定义
- 数据访问对象 (Repository)
- 数据库路由器
- 会话管理
"""

from .db_router import DatabaseRouter, HostDBRouter, KnowledgeDBRouter
from .repositories import HostRepository, GameRepository, KnowledgeRepository, UserBehaviorRepository
from .base import SessionManager
from .models import (
    Base, Host, HostSchedule, Game,
    KnowledgeDocument, User, UserBehavior, UserPreference, UserRecommendation
)

__all__ = [
    'DatabaseRouter',
    'HostDBRouter',
    'KnowledgeDBRouter',
    'HostRepository',
    'GameRepository',
    'KnowledgeRepository',
    'UserBehaviorRepository',
    'SessionManager',
    'Base',
    'Host',
    'HostSchedule',
    'Game',
    'KnowledgeDocument',
    'User',
    'UserBehavior',
    'UserPreference',
    'UserRecommendation'
]
