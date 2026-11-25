"""档案、游戏目录、本人预约，以及答完回到待分类。"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from langchain_core.chat_history import InMemoryChatMessageHistory

from agents.appointment.appointment_database import AppointmentDatabase
from agents.appointment.appointment_processor import AppointmentProcessor
from agents.appointment.host_finder import HostFinder
from agents.appointment.message_builder import MessageBuilder
from agents.appointment_agent import AppointmentAgent
from agents.factual.responder import FactualResponder
from agents.task_classification.agent_router import AgentRouter
from agents.task_classification.classification_processor import ClassificationProcessor
from agents.task_classification.state_manager import StateManager
from agents.task_classification.unrelated_handler import UnrelatedHandler
from config.constants import SharedState, StateEnum
from services.game_catalog_service import GameCatalogService


GAME = {
    "name": "血染钟楼",
    "min_players": 5,
    "max_players": 12,
    "duration_min": 90,
    "needs_host": True,
    "allowed_host_types": ["pro_host"],
}
HOSTS = [
    {"id": 1, "name": "陈屿", "gender": "男", "host_types": ["pro_host"], "specialty": "社交推理控场"},
    {"id": 2, "name": "林可", "gender": "女", "host_types": ["staff_guide"], "specialty": "轻策略"},
]


class Catalog:
    def resolve_game(self, text):
        service = GameCatalogService.__new__(GameCatalogService)
        service.list_games = lambda: [GAME]
        return GameCatalogService.resolve_game(service, text)


def _responder():
    return FactualResponder(hosts=HOSTS, catalog=Catalog())


def _run(responder, text, agent=None):
    return asyncio.run(responder.reply(text, agent))


def test_unknown_host_and_overlapping_slot_are_stated():
    responder = FactualResponder(
        hosts=HOSTS,
        schedules_of=lambda host_id, moment: [{
            "start": datetime(2026, 11, 24, 12, 30),
            "end": datetime(2026, 11, 24, 14, 0),
            "status": "busy",
        }],
        parse_time=lambda text, now: datetime(2026, 11, 24, 10, 0) if "10" in text else datetime(2026, 11, 24, 13, 0),
    )
    unknown = _run(responder, "王五明天13点有空吗")
    assert "没有找到这位主持人" in unknown
    busy = _run(responder, "陈屿明天13点有空吗")
    assert "没空" in busy
    assert "12:30–14:00" in busy
    closed = _run(responder, "陈屿明天10点有空吗")
    assert "12:00–22:00" in closed
    assert "没有空" in closed


def test_profile_list_and_game_fields_use_records():
    responder = _responder()
    specialty = _run(responder, "陈屿擅长什么")
    assert "社交推理控场" in specialty
    general = _run(responder, "陈屿什么样")
    assert "男" in general
    assert "专业主持人" in general
    assert "社交推理控场" in general
    listing = _run(responder, "店里有哪些主持人")
    assert "2位主持人" in listing
    assert "陈屿（专业主持人）" in listing
    assert "林可（店员带玩）" in listing
    game = _run(responder, "血染钟楼几个人，要不要主持")
    assert "5–12" in game
    assert "90" in game
    assert "需要主持" in game
    assert "专业主持人" in game
    missing = _run(responder, "麻将几个人")
    assert "没有这款游戏" in missing
    assert "5–12" not in missing


def test_own_status_hides_another_users_booking(tmp_path: Path):
    url = "sqlite:///" + (tmp_path / "status.db").as_posix()
    own = AppointmentDatabase(user_id="15", db_path=url)
    other = AppointmentDatabase(user_id="16", db_path=url)
    assert own.save_appointment(None, datetime(2026, 11, 24, 13, 0), datetime(2026, 11, 24, 14, 0), {"game": "自己的已确认"}, "s15")
    assert other.save_appointment(None, datetime(2026, 11, 24, 15, 0), datetime(2026, 11, 24, 16, 0), {"game": "别人的局"}, "s16")

    agent = AppointmentAgent.__new__(AppointmentAgent)
    agent.user_id = "15"
    agent.appointment_database = own
    agent.message_builder = MessageBuilder()
    agent.appointment_history = {
        "game": "进行中的局",
        "player_count": 6,
        "start_time": "2026-11-24 19:00",
        "host_type": "pro_host",
        "host_name": "陈屿",
    }
    reply = _run(_responder(), "我的预约", agent)
    assert "进行中的局" in reply
    assert "自己的已确认" in reply
    assert "别人的局" not in reply
    assert "请问想玩哪款" not in reply


class QueryClassifier:
    def __init__(self):
        self.calls = 0

    async def classify_task(self, task):
        self.calls += 1
        return "query"


class QuietConsultant:
    def __init__(self):
        self.calls = []

    def set_shared_state(self, state):
        self.state = state

    def set_unrelated_callback(self, callback):
        self.callback = callback

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def consult_stream(self, task):
        self.calls.append(task)
        yield "[REPLY][咨询机器人]知识库里的地址"


class SlotAgent:
    def __init__(self):
        self.appointment_history = {"game": "血染钟楼", "start_time": "2026-11-24 19:00"}
        self.reset_called = False
        self.run_calls = []
        self.user_id = None

    def reset(self):
        self.reset_called = True
        self.appointment_history = {}

    async def stream_status(self):
        yield "[REPLY][预约机器人]进行中的预约：《血染钟楼》。"

    async def run_stream(self, user_input=None):
        self.run_calls.append(user_input)
        yield "补槽"


def test_availability_answer_returns_to_classify_without_clearing_slots():
    agent = SlotAgent()
    consultant = QuietConsultant()
    classifier = QueryClassifier()
    state = SharedState()
    manager = StateManager(state)
    processor = ClassificationProcessor(
        classifier,
        manager,
        AgentRouter(agent, consultant, manager),
        UnrelatedHandler(manager),
    )
    processor.factual_responder = FactualResponder(
        hosts=[{"id": 1, "name": "陈屿", "gender": "男", "host_types": ["pro_host"], "specialty": "推理"}],
        schedules_of=lambda host_id, moment: [{
            "start": datetime(2026, 11, 24, 15, 0),
            "end": datetime(2026, 11, 24, 16, 0),
            "status": "busy",
        }],
        parse_time=lambda text, now: datetime(2026, 11, 24, 13, 0),
    )

    first = asyncio.run(_collect(processor, "陈屿明天13点有空吗"))
    assert "有空" in first
    assert "15:00–16:00" in first
    assert state.value == StateEnum.CLASSIFY
    assert agent.appointment_history["game"] == "血染钟楼"
    assert agent.reset_called is False
    assert classifier.calls == 0
    assert consultant.calls == []

    second = asyncio.run(_collect(processor, "门店地址"))
    assert classifier.calls == 1
    assert consultant.calls == ["门店地址"]
    assert agent.run_calls == []
    assert "补槽" not in second


def test_status_inside_booking_returns_to_classify_and_keeps_game():
    agent = AppointmentAgent.__new__(AppointmentAgent)
    agent.user_id = None
    agent.message_builder = MessageBuilder()
    agent.appointment_history = {
        "game": "血染钟楼",
        "player_count": 6,
        "start_time": "2026-11-24 19:00",
        "host_type": "pro_host",
        "host_name": "陈屿",
    }
    agent.state = SharedState()
    agent.state.value = StateEnum.APPOINTMENT
    reply = asyncio.run(_collect_agent(agent, "我的预约"))
    assert "血染钟楼" in reply
    assert agent.state.value == StateEnum.CLASSIFY
    assert agent.appointment_history["game"] == "血染钟楼"


def test_confirmation_stays_with_booking():
    shared = SharedState()
    shared.value = StateEnum.APPOINTMENT
    seen = []

    class Parser:
        def parse_stream(self, user_input, history):
            yield json.dumps({
                "confirmation": "可以",
                "unrelated": False,
                "game": "未知",
                "host_type": "未知",
                "player_count": "未知",
                "start_time": "未知",
                "duration": "未知",
                "host_name": "未知",
                "preference": "无",
                "info_complete": False,
                "missing_info": [],
            }, ensure_ascii=False)

        def parse_data(self, content):
            return json.loads(content)

    agent = AppointmentAgent.__new__(AppointmentAgent)
    agent.session_id = "confirm"
    agent.chat_history = InMemoryChatMessageHistory()
    agent.user_id = None
    agent.appointment_history = {
        "awaiting_confirmation": True,
        "recommended_host": {"id": 2, "name": "林可"},
        "game": "血染钟楼",
    }
    agent.input_parser = Parser()
    agent.message_builder = MessageBuilder()
    agent.host_finder = HostFinder()
    agent.appointment_processor = AppointmentProcessor(
        agent.input_parser, agent.host_finder, agent.message_builder, None, llm=None
    )

    async def handle_complete(history, session_id):
        seen.append(dict(history))
        yield "[REPLY][预约机器人]已按推荐确认"

    agent.appointment_processor.handle_complete_appointment = handle_complete
    agent.state = shared

    class Spy:
        def __init__(self):
            self.calls = 0

        async def reply(self, text, appointment_agent):
            self.calls += 1
            return "[REPLY][归类机器人]不应该查档"

    spy = Spy()
    manager = StateManager(shared)
    processor = ClassificationProcessor(
        QueryClassifier(),
        manager,
        AgentRouter(agent, QuietConsultant(), manager),
        UnrelatedHandler(manager),
    )
    processor.factual_responder = spy
    reply = asyncio.run(_collect(processor, "可以"))
    assert spy.calls == 0
    assert seen and seen[0]["confirmed_host"]["name"] == "林可"
    assert "已按推荐确认" in reply


async def _collect(processor, task):
    return "".join([token async for token in processor.process_task_stream(task)])


async def _collect_agent(agent, task):
    return "".join([token async for token in agent.run_stream(task)])
