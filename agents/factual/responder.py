"""根据说法和数据库事实生成一次性回复。"""

from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional

from agents.appointment.message_builder import is_status_question
from agents.factual.intent import classify_utterance
from agents.factual.schedule import assess_moment, free_windows, hosts_free_at, outside_business_hours
from agents.factual.time_parse import parse_moment
from config.constants import host_type_label
from config.time_config import time_config


ASK_TIME = "[REPLY][归类机器人]请问要查哪一天、几点？"
ASK_HOST = "[REPLY][归类机器人]请问要查哪一位主持人？"
UNKNOWN_HOST = "[REPLY][归类机器人]没有找到这位主持人。"
UNKNOWN_GAME = "[REPLY][归类机器人]目录里没有这款游戏，我不能确定人数或时长。"


def _reply(text: str) -> str:
    return f"[REPLY][归类机器人]{text}"


def _clock(value: datetime) -> str:
    return value.strftime("%H:%M")


def _ranges(intervals: Iterable[tuple]) -> str:
    return "、".join(f"{_clock(start)}–{_clock(end)}" for start, end in intervals)


def _type_labels(host_types: Optional[List[str]]) -> str:
    labels = [host_type_label(item) for item in host_types or []]
    return "、".join(label for label in labels if label)


class FactualResponder:
    def __init__(
        self,
        hosts: Optional[List[Dict[str, Any]]] = None,
        schedules_of: Optional[Callable[[int, datetime], List[Dict[str, Any]]]] = None,
        catalog: Any = None,
        parse_time: Optional[Callable[[str, datetime], Optional[datetime]]] = None,
        now: Optional[Callable[[], datetime]] = None,
    ):
        self._hosts = hosts
        self._schedules_of = schedules_of
        self._catalog = catalog
        self._parse_time = parse_time
        self._now = now or time_config.now

    async def reply(self, text: str, appointment_agent: Any = None) -> Optional[str]:
        if is_status_question(text):
            return await self._own_status(appointment_agent)
        hosts = self._load_hosts()
        decision = classify_utterance(text, [host["name"] for host in hosts], self._resolve_game)
        kind = decision["kind"]
        if kind in ("booking", "none"):
            return None
        if kind == "ask_host":
            return ASK_HOST
        if kind == "unknown_host":
            return UNKNOWN_HOST
        if kind == "host_list":
            return _reply(self._host_list(hosts))
        if kind == "host_profile":
            host = self._by_name(hosts, decision["host"])
            return UNKNOWN_HOST if host is None else _reply(self._profile(text, host))
        if kind == "game_missing":
            return UNKNOWN_GAME
        if kind == "game_fields":
            return _reply(self._game_fields(decision["game"]))
        if decision.get("needs_time"):
            return ASK_TIME
        moment = self._read_time(text)
        if moment is None:
            return ASK_TIME
        if kind == "who":
            return _reply(self._who(moment, hosts))
        host = self._by_name(hosts, decision["host"])
        if host is None:
            return UNKNOWN_HOST
        schedules = self._schedules(host, moment)
        if kind == "windows":
            return _reply(self._windows(host["name"], moment, schedules))
        return _reply(self._moment(host["name"], moment, schedules))

    async def _own_status(self, appointment_agent: Any) -> str:
        if appointment_agent is not None and hasattr(appointment_agent, "stream_status"):
            chunks = []
            async for token in appointment_agent.stream_status():
                chunks.append(token)
            return "".join(chunks)
        from agents.appointment.message_builder import MessageBuilder

        history = {}
        if appointment_agent is not None:
            history = getattr(appointment_agent, "appointment_history", None) or {}
        return f"[REPLY][预约机器人]{MessageBuilder().create_status_message(history, None)}"

    def _read_time(self, text: str) -> Optional[datetime]:
        current = self._now()
        if self._parse_time is not None:
            return self._parse_time(text, current)
        from config.model_provider import create_chat_model

        return parse_moment(text, create_chat_model(temperature=0), current)

    def _load_hosts(self) -> List[Dict[str, Any]]:
        if self._hosts is not None:
            return self._hosts
        from services.host_service import HostService

        return HostService().get_all_hosts()

    def _resolve_game(self, text: str):
        if self._catalog is not None:
            return self._catalog.resolve_game(text)
        from services.game_catalog_service import GameCatalogService

        return GameCatalogService().resolve_game(text)

    def _schedules(self, host: Dict[str, Any], moment: datetime) -> List[Dict[str, Any]]:
        if self._schedules_of is not None:
            return self._schedules_of(host["id"], moment)
        if host.get("schedules") is not None:
            return host["schedules"]
        from services.appointment_service import AppointmentService

        return AppointmentService().get_host_schedules(host["id"], moment)

    def _by_name(self, hosts: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
        for host in hosts:
            if host["name"] == name:
                return host
        return None

    def _moment(self, name: str, moment: datetime, schedules: List[Dict[str, Any]]) -> str:
        result = assess_moment(moment, schedules)
        when = moment.strftime("%Y-%m-%d %H:%M")
        if result["outside"]:
            return f"{name}在{when}不在营业时间 12:00–22:00 内，这个时刻没有空。"
        busy = _ranges(result["day_busy"]) or "没有"
        if result["free"]:
            return f"{name}在{when}有空。当天忙碌时段：{busy}。"
        start, end = result["overlap"]
        return f"{name}在{when}没空，重叠排班是 {_clock(start)}–{_clock(end)}。当天忙碌时段：{busy}。"

    def _windows(self, name: str, moment: datetime, schedules: List[Dict[str, Any]]) -> str:
        windows = free_windows(moment, schedules)
        date_text = moment.strftime("%Y-%m-%d")
        if not windows:
            return f"{name}在{date_text}的营业时间内没有空档。"
        return f"{name}在{date_text}的空档是 {_ranges(windows)}。"

    def _who(self, moment: datetime, hosts: List[Dict[str, Any]]) -> str:
        when = moment.strftime("%Y-%m-%d %H:%M")
        if outside_business_hours(moment):
            return f"{when}不在营业时间 12:00–22:00 内，这个时刻没有空。"
        enriched = []
        for host in hosts:
            item = dict(host)
            item["schedules"] = self._schedules(host, moment)
            enriched.append(item)
        names = hosts_free_at(moment, enriched)
        if not names:
            return f"{when}没有主持人有空。"
        return f"{when}有空的主持人：{'、'.join(names)}。"

    def _profile(self, text: str, host: Dict[str, Any]) -> str:
        name = host["name"]
        specialty = host.get("specialty") or "没有填写专长"
        gender = host.get("gender") or "未填写"
        types = _type_labels(host.get("host_types")) or "未填写"
        if "擅长" in text or "专长" in text:
            return f"{name}的专长是{specialty}。"
        if "性别" in text:
            return f"{name}的性别是{gender}。"
        if "主持" in text:
            return f"{name}的主持类型是{types}。"
        return f"{name}，{gender}，主持类型：{types}。专长：{specialty}。"

    def _host_list(self, hosts: List[Dict[str, Any]]) -> str:
        if not hosts:
            return "现在没有主持人档案。"
        body = "、".join(f"{host['name']}（{_type_labels(host.get('host_types')) or '未填写'}）" for host in hosts)
        return f"店里有{len(hosts)}位主持人：{body}。"

    def _game_fields(self, game: Dict[str, Any]) -> str:
        allowed = _type_labels(game.get("allowed_host_types")) or "未填写"
        hosting = "需要主持" if game.get("needs_host") else "可以不安排主持"
        return (
            f"《{game['name']}》适合 {game['min_players']}–{game['max_players']} 人，"
            f"建议时长 {game['duration_min']} 分钟，{hosting}。可选主持：{allowed}。"
        )
