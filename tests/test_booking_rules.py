"""桌游预约规则：不调用大模型。"""

import asyncio
import sqlite3
from pathlib import Path

from agents.appointment.appointment_processor import AppointmentProcessor
from agents.appointment.host_finder import HostFinder
from agents.appointment.message_builder import MessageBuilder
from db.base.legacy_reset import reset_legacy_sqlite_if_needed
from services.game_catalog_service import GameCatalogService
from services.host_service import HostService


def _db_url(tmp_path: Path) -> str:
    return "sqlite:///" + (tmp_path / "booking.db").as_posix()


def _processor(tmp_path: Path) -> AppointmentProcessor:
    db_url = _db_url(tmp_path)
    catalog = GameCatalogService(db_url)
    hosts = HostService(db_url)
    catalog.initialize_default_games()
    hosts.initialize_default_hosts()
    return AppointmentProcessor(
        input_parser=None,
        host_finder=HostFinder(),
        message_builder=MessageBuilder(),
        appointment_database=None,
        llm=None,
        catalog=catalog,
        host_service=hosts,
    )


def _history() -> dict:
    return {
        "game": None,
        "game_id": None,
        "host_type": None,
        "player_count": None,
        "start_time": None,
        "duration": None,
        "duration_defaulted": False,
        "host_name": None,
        "preference": None,
    }


def test_player_count_out_of_range(tmp_path):
    processor = _processor(tmp_path)
    history = _history()
    finished = processor.update_history_from_data(history, {
        "game": "血染钟楼",
        "host_type": "专业主持人",
        "player_count": 2,
        "start_time": "2026-11-24 15:00",
    })
    assert finished is False
    assert "player_count" in history["invalid_fields"]
    assert "不在范围内" in history["clarify_question"]


def test_host_type_not_allowed(tmp_path):
    processor = _processor(tmp_path)
    history = _history()
    finished = processor.update_history_from_data(history, {
        "game": "卡卡颂",
        "host_type": "pro_host",
        "player_count": 3,
        "start_time": "2026-11-24 15:00",
    })
    assert finished is False
    assert "host_type" in history["invalid_fields"]


def test_kids_game_rejects_pro_host(tmp_path):
    processor = _processor(tmp_path)
    history = _history()
    finished = processor.update_history_from_data(history, {
        "game": "恐龙小镇",
        "host_type": "专业主持人",
        "player_count": 3,
        "start_time": "2026-11-24 15:00",
    })
    assert finished is False
    assert "host_type" in history["invalid_fields"]


def test_needs_host_rejects_self_play(tmp_path):
    processor = _processor(tmp_path)
    history = _history()
    finished = processor.update_history_from_data(history, {
        "game": "血染钟楼",
        "host_type": "自助",
        "player_count": 8,
        "start_time": "2026-11-24 15:00",
    })
    assert finished is False
    assert "不能自助" in history["clarify_question"]


def test_self_play_completes_without_host_and_uses_catalog_duration(tmp_path):
    processor = _processor(tmp_path)
    history = _history()
    finished = processor.update_history_from_data(history, {
        "game": "卡卡颂",
        "host_type": "自己玩",
        "player_count": "3人",
        "start_time": "2026-11-24 15:00",
    })
    assert finished is True
    assert history["host_type"] == "self_play"
    assert history["duration"] == "45分钟"
    assert history["duration_defaulted"] is True
    assert processor.requires_host(history) is False


def test_named_host_infers_single_host_type(tmp_path):
    processor = _processor(tmp_path)
    history = _history()
    finished = processor.update_history_from_data(history, {
        "game": "血染钟楼",
        "host_name": "陈屿",
        "player_count": 8,
        "start_time": "2026-11-24 15:00",
    })
    assert finished is True
    assert history["host_type"] == "pro_host"
    assert history["duration"] == "90分钟"


def test_self_play_confirmation_does_not_occupy_host(tmp_path):
    processor = _processor(tmp_path)
    history = _history()
    processor.update_history_from_data(history, {
        "game": "卡卡颂",
        "host_type": "self_play",
        "player_count": 4,
        "start_time": "2026-11-24 15:00",
    })

    class FakeDatabase:
        def __init__(self):
            self.saved_host_id = "unset"

        def save_appointment(self, host_id, start_time, end_time, appointment_history, session_id):
            self.saved_host_id = host_id
            return True

        def update_memory_schedule(self, *args):
            raise AssertionError("自助场次不应写入主持人档期")

    processor.appointment_database = FakeDatabase()

    async def run():
        chunks = []
        async for token in processor.handle_complete_appointment(history, "session"):
            chunks.append(token)
        return "".join(chunks)

    reply = asyncio.run(run())
    assert processor.appointment_database.saved_host_id is None
    assert "自助" in reply
    assert "卡卡颂" in reply


def test_host_type_filter_stays_inside_same_type():
    finder = HostFinder()
    hosts = [
        {"id": 1, "name": "陈屿", "host_types": ["pro_host"]},
        {"id": 2, "name": "苏晚", "host_types": ["staff_guide"]},
    ]
    matched = finder.filter_hosts_by_type(hosts, "pro_host")
    assert [host["name"] for host in matched] == ["陈屿"]


def test_legacy_massage_database_is_backed_up_and_removed(tmp_path):
    db_file = tmp_path / "smart_appointment.db"
    connection = sqlite3.connect(db_file)
    connection.execute("CREATE TABLE technicians (id INTEGER PRIMARY KEY)")
    connection.commit()
    connection.close()

    reset_legacy_sqlite_if_needed("sqlite:///" + db_file.as_posix())

    assert not db_file.exists()
    backups = list(tmp_path.glob("smart_appointment.legacy.*.db"))
    assert len(backups) == 1
