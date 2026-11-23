"""按用户隔离预约、偏好、回访和分析。"""

import asyncio
import os
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["SKIP_SYSTEM_INIT"] = "1"

from agents.appointment.appointment_database import AppointmentDatabase
from agents.appointment_agent import AppointmentAgent
from agents.consultant.consultation_processor import ConsultationProcessor
from db.base.session_manager import SessionManager
from db.models import User, UserBehavior, UserPreference
from services.user_behavior_service import UserBehaviorService


@pytest.fixture
def client():
    import app as app_module

    with TestClient(app_module.app) as test_client:
        yield test_client


def _behavior_count() -> int:
    manager = SessionManager()
    with manager.session_scope() as session:
        return session.query(UserBehavior).count()


def _cleanup(usernames):
    manager = SessionManager()
    with manager.session_scope() as session:
        users = session.query(User).filter(User.username.in_(usernames)).all()
        user_ids = [str(user.id) for user in users]
        if user_ids:
            session.query(UserBehavior).filter(UserBehavior.user_id.in_(user_ids)).delete(synchronize_session=False)
            session.query(UserPreference).filter(UserPreference.user_id.in_(user_ids)).delete(synchronize_session=False)
            session.query(User).filter(User.id.in_([user.id for user in users])).delete(synchronize_session=False)


def test_saved_appointment_behavior_and_preferences_belong_to_that_user(tmp_path: Path):
    url = "sqlite:///" + (tmp_path / "booking.db").as_posix()
    database = AppointmentDatabase(user_id="15", db_path=url)
    saved = database.save_appointment(
        None,
        datetime(2026, 11, 24, 13, 0),
        datetime(2026, 11, 24, 14, 30),
        {"game": "血染钟楼", "host_type": "pro_host", "player_count": 4},
        "session-15",
    )
    assert saved is True

    service = UserBehaviorService(url)
    behaviors = service.get_user_behaviors("15", action_type="appointment")
    assert len(behaviors) == 1
    assert behaviors[0]["user_id"] == "15"
    assert behaviors[0]["user_id"] != "default_user"
    own_preferences = service.get_user_preferences("15")
    assert any(
        item["preference_type"] == "game" and item["preference_value"] == "血染钟楼"
        for item in own_preferences
    )
    assert service.get_user_preferences("16") == []

    agent = AppointmentAgent.__new__(AppointmentAgent)
    agent.user_id = "15"
    agent.appointment_database = database
    assert agent._latest_saved_appointment()["game"] == "血染钟楼"
    agent.user_id = "16"
    assert agent._latest_saved_appointment() is None


def test_consultation_record_uses_current_user(monkeypatch):
    captured = {}

    class StubAgent:
        def record_behavior(self, **kwargs):
            captured.update(kwargs)
            return True

    monkeypatch.setattr(
        "agents.user_behavior_agent.UserBehaviorAgent",
        lambda: StubAgent(),
    )
    processor = ConsultationProcessor(None, None, None, user_id="42")
    asyncio.run(processor._record_consultation_behavior("怎么玩", [], "session-42"))
    assert captured["user_id"] == "42"
    assert captured["action_type"] == "consultation"


def test_anonymous_chat_is_rejected_before_agent_and_writes_nothing(client, monkeypatch):
    import api.chat_handler as chat_handler

    def forbidden(user_id):
        raise AssertionError("未登录不应创建 Agent")

    monkeypatch.setattr(chat_handler, "build_task_agent", forbidden)
    before = _behavior_count()
    response = client.post("/chat/stream", json={"message": "我想预约"})
    assert response.status_code == 401
    assert _behavior_count() == before


def test_public_pages_do_not_require_login_or_write_behavior(client):
    before = _behavior_count()
    for path in ("/host", "/host_schedule", "/knowledge"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.text
    assert _behavior_count() == before


def test_two_users_keep_slots_bookings_analysis_and_logout(client, monkeypatch):
    import api.chat_handler as chat_handler

    names = ["path-user-a", "path-user-b"]
    try:
        chat_handler.reset_task_agents()

        def build(user_id):
            class Appointment:
                def __init__(self):
                    self.user_id = str(user_id)
                    self.appointment_history = {}
                    self.appointment_database = AppointmentDatabase(user_id=str(user_id))

            class Task:
                def __init__(self):
                    self.appointment_agent = Appointment()

                async def classify_task_stream(self, text):
                    self.appointment_agent.appointment_history["utterance"] = text
                    if text.startswith("完成预约:"):
                        game = text.split(":", 1)[1]
                        self.appointment_agent.appointment_database.save_appointment(
                            None,
                            datetime(2026, 11, 24, 13, 0),
                            datetime(2026, 11, 24, 14, 30),
                            {"game": game, "host_type": "pro_host", "player_count": 4},
                            f"session-{user_id}",
                        )
                    yield "ok"

            return Task()

        monkeypatch.setattr(chat_handler, "build_task_agent", build)
        other = TestClient(client.app)
        client.post(
            "/api/auth/register",
            json={"username": names[0], "password": "long-enough", "display_name": "甲用户"},
        )
        other.post(
            "/api/auth/register",
            json={"username": names[1], "password": "long-enough", "display_name": "乙用户"},
        )
        client.post("/chat/stream", json={"message": "未完成预约甲"})
        other.post("/chat/stream", json={"message": "未完成预约乙"})

        manager = SessionManager()
        with manager.session_scope() as session:
            id_by_name = {
                user.username: str(user.id)
                for user in session.query(User).filter(User.username.in_(names))
            }
        assert chat_handler._agents[id_by_name[names[0]]].appointment_agent.appointment_history["utterance"] == "未完成预约甲"
        assert chat_handler._agents[id_by_name[names[1]]].appointment_agent.appointment_history["utterance"] == "未完成预约乙"

        legacy = UserBehaviorService().record_behavior(
            user_id="default_user",
            action_type="appointment",
            action_data={"game": "旧的默认记录", "duration": 60},
        )
        assert legacy is True
        client.post("/chat/stream", json={"message": "完成预约:只属于甲"})
        other.post("/chat/stream", json={"message": "完成预约:只属于乙"})
        other.post("/chat/stream", json={"message": "完成预约:只属于乙"})

        analysis_a = client.get("/api/user-behavior/analysis")
        analysis_b = other.get("/api/user-behavior/analysis")
        assert analysis_a.status_code == 200
        assert analysis_a.json()["total_appointments"] == 1
        assert analysis_a.json()["favorite_service"] == "只属于甲"
        assert analysis_b.json()["total_appointments"] == 2
        assert analysis_b.json()["favorite_service"] == "只属于乙"

        page = client.get("/user_behavior")
        assert page.status_code == 200
        assert "default_user" not in page.text

        client.post("/api/auth/logout")
        assert client.get("/api/auth/me").json() == {"authenticated": False}
        assert client.get("/api/user-behavior/analysis").status_code == 401
    finally:
        chat_handler.reset_task_agents()
        _cleanup(names)
        manager = SessionManager()
        with manager.session_scope() as session:
            leftovers = session.query(UserBehavior).filter(UserBehavior.user_id == "default_user").all()
            for row in leftovers:
                if (row.action_data or {}).get("game") == "旧的默认记录":
                    session.delete(row)


def test_reminder_for_user_without_preferences_uses_display_name(client):
    username = "reminder-user"
    try:
        registered = client.post(
            "/api/auth/register",
            json={"username": username, "password": "long-enough", "display_name": "星河"},
        )
        assert registered.status_code == 200
        response = client.post("/api/user-behavior/send-reminder", json={})
        assert response.status_code == 200
        message = response.json()["message"]
        assert "星河" in message
        assert "Tom" not in message
        for path in (
            Path("agents/user_behavior_agent.py"),
            Path("api/user_behavior_analysis.py"),
        ):
            assert "尊敬的Tom" not in path.read_text(encoding="utf-8")
    finally:
        _cleanup([username])
