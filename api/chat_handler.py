from agents.task_classification_agent import TaskClassificationAgent
from agents.appointment_agent import AppointmentAgent
from agents.consultant_agent import ConsultantAgent

_agents = {}


def build_task_agent(user_id: str) -> TaskClassificationAgent:
    """为该登录用户创建独立的分类、预约和咨询状态。"""
    session_id = f"user-{user_id}"
    return TaskClassificationAgent(
        AppointmentAgent(session_id=session_id, user_id=str(user_id)),
        ConsultantAgent(session_id=session_id, user_id=str(user_id)),
    )


def get_task_agent(user_id: str) -> TaskClassificationAgent:
    key = str(user_id)
    agent = _agents.get(key)
    if agent is None:
        agent = build_task_agent(key)
        _agents[key] = agent
    return agent


def reset_task_agents() -> None:
    _agents.clear()


async def ProcessUserInput_stream(user_input, user_id: str, state=None, context=None):
    """按登录用户处理聊天。未登录的请求不得进入这里。"""
    agent = get_task_agent(str(user_id))
    async for token in agent.classify_task_stream(user_input):
        yield token
