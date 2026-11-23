"""
Repositories Module

数据访问对象模块，包含：
- 主持人数据仓库
- 游戏目录数据仓库
- 知识库数据仓库
- 用户行为数据仓库
"""

from .host_repository import HostRepository
from .game_repository import GameRepository
from .knowledge_repository import KnowledgeRepository
from .user_behavior_repository import UserBehaviorRepository

__all__ = [
    "HostRepository",
    "GameRepository",
    "KnowledgeRepository",
    "UserBehaviorRepository",
]
