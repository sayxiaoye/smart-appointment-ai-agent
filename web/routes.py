"""
Web界面路由

处理前端页面渲染和聊天功能
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from api.chat_handler import ProcessUserInput_stream
import logging

# 创建logger实例
logger = logging.getLogger(__name__)
# 模板配置
templates = Jinja2Templates(directory="web/templates")

# Web路由器
router = APIRouter(tags=["Web界面"])

class ChatRequest(BaseModel):
    message: str
    state: str | None = None

@router.get("/", response_class=HTMLResponse, summary="主页")
async def read_root(request: Request):
    """渲染主页聊天界面"""
    return templates.TemplateResponse("index.html", {"request": request})

@router.post("/chat/stream", summary="流式聊天")
async def chat_stream_endpoint(chat: ChatRequest):
    """处理流式聊天请求"""
    async def token_generator():
        async for token in ProcessUserInput_stream(chat.message):
            yield token
    return StreamingResponse(token_generator(), media_type="text/plain")

@router.post("/chat", summary="兼容性聊天接口")
async def chat_endpoint(chat: ChatRequest):
    """兼容性聊天接口，建议使用/chat/stream"""
    async def token_generator():
        async for token in ProcessUserInput_stream(chat.message):
            yield token
    return StreamingResponse(token_generator(), media_type="text/plain")

@router.get("/user_behavior", response_class=HTMLResponse, summary="用户行为分析页面")
async def user_behavior_page(request: Request):
    """用户行为分析页面"""
    return templates.TemplateResponse("user_behavior_analysis.html", {"request": request})

@router.get("/knowledge", response_class=HTMLResponse, summary="知识库管理页面")
async def knowledge_page(request: Request):
    """知识库管理页面"""
    # 通过API层获取知识库数据
    try:
        from api.knowledge import get_all_knowledge
        
        # 调用API层函数获取数据
        knowledge_data = await get_all_knowledge()
        documents = knowledge_data.get("documents", [])
        categories = knowledge_data.get("categories", [])
        
        return templates.TemplateResponse("knowledge_management.html", {
            "request": request,
            "documents": documents,
            "categories": categories
        })
    except Exception as e:
        return templates.TemplateResponse("knowledge_management.html", {
            "request": request,
            "documents": [],
            "categories": [],
            "error": str(e)
        })

@router.get("/host", response_class=HTMLResponse, summary="主持人状态页面")
async def host_page(request: Request):
    """主持人状态页面"""
    try:
        from api.host import get_all_hosts
        hosts = await get_all_hosts()
        return templates.TemplateResponse("host.html", {
            "request": request,
            "hosts": hosts
        })
    except Exception as e:
        return templates.TemplateResponse("host.html", {
            "request": request,
            "hosts": [],
            "error": str(e)
        })

@router.get("/host_schedule", response_class=HTMLResponse, summary="主持人排班页面")
async def host_schedule_page(request: Request):
    """主持人排班页面"""
    try:
        from api.host import get_all_hosts_schedule_today
        from config.time_config import time_config

        current_date = time_config.current_date_str()
        schedules_data = await get_all_hosts_schedule_today()
        schedule = [
            {
                "id": item["host_id"],
                "name": item["host_name"],
                "busy_periods": item["busy_periods"],
            }
            for item in schedules_data
        ]
        return templates.TemplateResponse("host_schedule.html", {
            "request": request,
            "schedule": schedule,
            "current_date": current_date
        })
    except Exception as e:
        logger.error(f"加载主持人排班数据失败: {str(e)}")
        return templates.TemplateResponse("host_schedule.html", {
            "request": request,
            "schedule": [],
            "error": str(e)
        })

@router.get("/user_behavior_analysis", response_class=HTMLResponse, summary="用户行为分析页面")
async def user_behavior_analysis_page(request: Request):
    """用户行为分析页面"""
    return templates.TemplateResponse("user_behavior_analysis.html", {"request": request})

@router.get("/admin", response_class=HTMLResponse, summary="系统管理页面")
async def admin_dashboard(request: Request):
    """系统管理仪表板"""
    try:
        # 通过API层获取系统状态信息
        from api.knowledge import get_all_knowledge
        from api.host import get_all_hosts

        knowledge_data = await get_all_knowledge()
        knowledge_count = knowledge_data.get("total_count", 0)
        categories = knowledge_data.get("categories", [])
        hosts = await get_all_hosts()

        db_info = {
            "knowledge_count": knowledge_count,
            "categories_count": len(categories),
            "hosts_count": len(hosts),
            "categories": categories
        }

        return templates.TemplateResponse("admin_dashboard.html", {
            "request": request,
            "db_info": db_info,
            "hosts": hosts[:5]
        })
    except Exception as e:
        return templates.TemplateResponse("admin_dashboard.html", {
            "request": request,
            "db_info": {},
            "hosts": [],
            "error": str(e)
        })

@router.get("/admin/database", response_class=HTMLResponse, summary="数据库管理页面")
async def database_admin_page(request: Request):
    """数据库管理页面"""
    try:
        # 通过API层获取数据库统计信息
        from api.knowledge import get_all_knowledge
        from api.host import get_all_hosts

        knowledge_data = await get_all_knowledge()
        hosts = await get_all_hosts()

        stats = {
            "knowledge_documents": knowledge_data.get("total_count", 0),
            "categories": len(knowledge_data.get("categories", [])),
            "hosts": len(hosts),
            "appointments": 0  # TODO: 通过API获取预约数量
        }
        
        return templates.TemplateResponse("database_admin.html", {
            "request": request,
            "stats": stats
        })
    except Exception as e:
        return templates.TemplateResponse("database_admin.html", {
            "request": request,
            "stats": {},
            "error": str(e)
        })
