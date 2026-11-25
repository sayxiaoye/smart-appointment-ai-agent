"""把一句话分成预约、事实查询，或留给原来的归类。"""

import re
from typing import Any, Callable, Dict, List, Optional, Sequence

from agents.appointment.message_builder import is_status_question


BOOKING_MARKERS = ("我要预约", "帮我预约", "帮我约", "预约一场")
AVAILABILITY_MARKERS = ("有没有空", "谁有空", "哪些时段", "有空", "没空", "空档", "档期")
PROFILE_MARKERS = ("擅长", "专长", "哪些主持人", "有哪些主持人", "性别", "什么样")
GAME_MARKERS = ("几个人", "多少人", "玩多久", "多久", "要不要主持", "哪种主持")
NARRATIVE_MARKERS = ("怎么玩", "规则")
PRICE_MARKERS = ("收费", "多少钱")

_TIME_WORDS = (
    "今天", "明天", "后天", "上午", "下午", "晚上", "点", "时", "分",
    "周", "月", "号", "日", "有没有", "有空", "没空", "空档", "档期",
    "哪些", "时段", "谁", "主持人", "擅长", "专长", "性别", "什么样",
    "什么", "怎么", "吗", "呢", "的", "在", "问", "一下", "帮我", "看看",
    "是否", "能不能", "可以", "几个人", "多少人", "玩多久", "多久",
    "要不要主持", "哪种主持", "店里", "有哪些", "介绍",
)
_CJK_NAME = re.compile(r"[\u4e00-\u9fff]{2,}")


def matched_host_names(text: str, host_names: Sequence[str]) -> List[str]:
    """按姓名全称出现的次数收集，长名字优先，去掉被更长名字包含的短名字。"""
    found = [name for name in sorted(host_names, key=len, reverse=True) if name and name in text]
    return [name for name in found if not any(name != other and name in other for other in found)]


def _unmatched_names(text: str, known_names: Sequence[str]) -> List[str]:
    cleaned = text
    for token in list(known_names) + list(_TIME_WORDS):
        cleaned = cleaned.replace(token, " ")
    cleaned = re.sub(r"[0-9０-９:：点分时/\-]", " ", cleaned)
    return [item for item in _CJK_NAME.findall(cleaned) if item not in _TIME_WORDS]


def _has_time_hint(text: str) -> bool:
    hints = ("今天", "明天", "后天", "上午", "下午", "晚上", "点", "时", "周", "月", "号", ":")
    return any(hint in text for hint in hints) or any(ch.isdigit() for ch in text)


def classify_utterance(
    text: str,
    host_names: Sequence[str],
    resolve_game: Callable[[str], Optional[Dict[str, Any]]],
) -> Dict[str, Any]:
    normalized = (text or "").replace(" ", "")
    if any(marker in normalized for marker in BOOKING_MARKERS):
        return {"kind": "booking"}
    if is_status_question(normalized):
        return {"kind": "own_status"}
    if any(marker in normalized for marker in AVAILABILITY_MARKERS):
        return _availability(normalized, host_names)
    if any(marker in normalized for marker in PRICE_MARKERS):
        return {"kind": "none"}
    if any(marker in normalized for marker in PROFILE_MARKERS):
        return _profile(normalized, host_names)
    if any(marker in normalized for marker in NARRATIVE_MARKERS):
        return {"kind": "none"}
    if any(marker in normalized for marker in GAME_MARKERS):
        return _game(normalized, resolve_game)
    return {"kind": "none"}


def _availability(text: str, host_names: Sequence[str]) -> Dict[str, Any]:
    names = matched_host_names(text, host_names)
    if "哪些时段" in text:
        return _named_or_ask(text, names, "windows")
    if "谁有空" in text or ("谁" in text and "有空" in text):
        return {"kind": "who", "needs_time": not _has_time_hint(text)}
    if len(names) == 1:
        return {"kind": "moment", "host": names[0], "needs_time": not _has_time_hint(text)}
    if len(names) > 1:
        return {"kind": "ask_host", "hosts": names}
    if _unmatched_names(text, names):
        return {"kind": "unknown_host"}
    return {"kind": "ask_host", "hosts": []}


def _named_or_ask(text: str, names: List[str], kind: str) -> Dict[str, Any]:
    if len(names) == 1:
        return {"kind": kind, "host": names[0], "needs_time": not _has_time_hint(text)}
    if len(names) > 1:
        return {"kind": "ask_host", "hosts": names}
    if _unmatched_names(text, names):
        return {"kind": "unknown_host"}
    return {"kind": "ask_host", "hosts": []}


def _profile(text: str, host_names: Sequence[str]) -> Dict[str, Any]:
    if "哪些主持人" in text or "有哪些主持人" in text:
        return {"kind": "host_list"}
    names = matched_host_names(text, host_names)
    if len(names) == 1:
        return {"kind": "host_profile", "host": names[0]}
    if len(names) > 1:
        return {"kind": "ask_host", "hosts": names}
    if _unmatched_names(text, names):
        return {"kind": "unknown_host"}
    return {"kind": "ask_host", "hosts": []}


def _game(text: str, resolve_game: Callable[[str], Optional[Dict[str, Any]]]) -> Dict[str, Any]:
    game = resolve_game(text)
    if game:
        return {"kind": "game_fields", "game": game}
    if _unmatched_names(text, []) or "《" in text:
        return {"kind": "game_missing"}
    return {"kind": "none"}
