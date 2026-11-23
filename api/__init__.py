"""API 路由注册。"""

from .auth import router as auth_router
from .appointment import router as appointment_router
from .consultation import router as consultation_router
from .task import router as task_router
from .knowledge import router as knowledge_router
from .host import router as host_router
from .user_behavior_analysis import router as user_behavior_analysis_router
from .user_behavior_analysis import router_underscore as user_behavior_analysis_underscore_router

api_routers = [
    auth_router,
    appointment_router,
    consultation_router,
    task_router,
    knowledge_router,
    host_router,
    user_behavior_analysis_router,
    user_behavior_analysis_underscore_router,
]
