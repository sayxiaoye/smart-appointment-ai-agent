"""咨询和预约互相拒绝时不能无限转交。"""

import asyncio

from agents.appointment.message_builder import MessageBuilder, is_status_question
from agents.task_classification.agent_router import AgentRouter
from agents.task_classification.classification_processor import ClassificationProcessor
from agents.task_classification.state_manager import StateManager
from agents.task_classification.unrelated_handler import UnrelatedHandler
from config.constants import SharedState, StateEnum


class FixedClassifier:
    def __init__(self, category):
        self.category = category
        self.calls = 0

    async def classify_task(self, task):
        self.calls += 1
        return self.category


class RejectingConsultant:
    def __init__(self, processor_holder):
        self.processor_holder = processor_holder
        self.shared_state = None
        self.calls = 0

    def set_shared_state(self, state):
        self.shared_state = state

    def set_unrelated_callback(self, callback):
        self.callback = callback

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def consult_stream(self, task):
        self.calls += 1
        if self.shared_state is not None:
            self.shared_state.value = StateEnum.CLASSIFY
        processor = self.processor_holder["processor"]
        async for token in processor.process_task_stream(task, rejected_by="consultant"):
            yield token


class StatusAppointment:
    def __init__(self):
        self.status_calls = 0

    def set_shared_state(self, state):
        self.state = state

    async def stream_status(self):
        self.status_calls += 1
        yield "[REPLY][预约机器人]当前没有进行中的预约"


class BouncingAppointment:
    def __init__(self, processor_holder):
        self.processor_holder = processor_holder
        self.calls = 0
        self.state = None

    def set_shared_state(self, state):
        self.state = state

    async def run_stream(self, user_input=None):
        self.calls += 1
        if self.state is not None:
            self.state.value = StateEnum.CLASSIFY
        processor = self.processor_holder["processor"]
        async for token in processor.process_task_stream(user_input, rejected_by="appointment"):
            yield token


def _collect(processor, task):
    async def run():
        return "".join([token async for token in processor.process_task_stream(task)])

    return asyncio.run(run())


def test_status_question_does_not_bounce_forever():
    holder = {}
    classifier = FixedClassifier("query")
    consultant = RejectingConsultant(holder)
    appointment = StatusAppointment()
    state = SharedState()
    processor = ClassificationProcessor(
        classifier,
        StateManager(state),
        AgentRouter(appointment, consultant, StateManager(state)),
        UnrelatedHandler(StateManager(state)),
    )
    holder["processor"] = processor

    reply = _collect(processor, "当前预约状态")

    assert classifier.calls == 0
    assert consultant.calls == 0
    assert appointment.status_calls == 1
    assert "当前没有进行中的预约" in reply
    assert state.value == StateEnum.CLASSIFY


def test_repeated_rejection_stops_at_unrelated_reply():
    holder = {}
    classifier = FixedClassifier("query")
    consultant = RejectingConsultant(holder)
    state = SharedState()
    processor = ClassificationProcessor(
        classifier,
        StateManager(state),
        AgentRouter(StatusAppointment(), consultant, StateManager(state)),
        UnrelatedHandler(StateManager(state)),
    )
    holder["processor"] = processor

    reply = _collect(processor, "今天股票怎么样")

    assert classifier.calls == 2
    assert consultant.calls == 1
    assert "只能帮您处理桌游" in reply


def test_appointment_rejecting_itself_does_not_recurse():
    holder = {}
    classifier = FixedClassifier("appointment")
    appointment = BouncingAppointment(holder)
    state = SharedState()
    processor = ClassificationProcessor(
        classifier,
        StateManager(state),
        AgentRouter(appointment, None, StateManager(state)),
        UnrelatedHandler(StateManager(state)),
    )
    holder["processor"] = processor

    reply = _collect(processor, "随便说点什么")

    assert classifier.calls == 2
    assert appointment.calls == 1
    assert "只能帮您处理桌游" in reply


def test_status_question_detection_ignores_new_booking():
    assert is_status_question("当前预约状态")
    assert is_status_question("我的预约状态")
    assert is_status_question("我要预约卡卡颂") is False
    reply = MessageBuilder().create_status_message(
        {"game": None, "start_time": None},
        {"game": "卡卡颂", "player_count": 4, "start_time": "2026-11-24 15:00", "host_type": "self_play"},
    )
    assert "卡卡颂" in reply
    assert "自助" in reply
    assert "主持人：" not in reply

    named = MessageBuilder().create_status_message(
        {},
        {
            "game": "血染钟楼",
            "player_count": 7,
            "start_time": "2026-11-24 13:00:00",
            "host_type": "pro_host",
            "host_name": "陈屿",
        },
    )
    assert "主持人：陈屿（专业主持人）" in named

    builder = MessageBuilder()
    builder._lookup_host_name = lambda host_id: "陈屿" if host_id == 1 else None
    looked_up = builder.create_status_message(
        {},
        {
            "game": "血染钟楼",
            "player_count": 7,
            "start_time": "2026-11-24 13:00:00",
            "host_type": "pro_host",
            "host_id": 1,
        },
    )
    assert "主持人：陈屿（专业主持人）" in looked_up
