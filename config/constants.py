from enum import Enum

busy_periods_dict = {}  # { host_id: [ {"start": "...", "end": "..."} ] }


class HostType(str, Enum):
    PRO_HOST = "pro_host"
    STAFF_GUIDE = "staff_guide"
    SELF_PLAY = "self_play"
    KIDS_HOST = "kids_host"


HOST_TYPE_LABELS = {
    HostType.PRO_HOST.value: "专业主持人",
    HostType.STAFF_GUIDE.value: "店员带玩",
    HostType.SELF_PLAY.value: "自助",
    HostType.KIDS_HOST.value: "少儿向主持",
}

_HOST_TYPE_ALIASES = {
    "pro_host": HostType.PRO_HOST.value,
    "专业主持人": HostType.PRO_HOST.value,
    "专业主持": HostType.PRO_HOST.value,
    "staff_guide": HostType.STAFF_GUIDE.value,
    "店员带玩": HostType.STAFF_GUIDE.value,
    "店员": HostType.STAFF_GUIDE.value,
    "带玩": HostType.STAFF_GUIDE.value,
    "self_play": HostType.SELF_PLAY.value,
    "自助": HostType.SELF_PLAY.value,
    "自己玩": HostType.SELF_PLAY.value,
    "自己看规则": HostType.SELF_PLAY.value,
    "kids_host": HostType.KIDS_HOST.value,
    "少儿向主持": HostType.KIDS_HOST.value,
    "少儿主持": HostType.KIDS_HOST.value,
    "儿童主持": HostType.KIDS_HOST.value,
    "少儿": HostType.KIDS_HOST.value,
}


def host_type_label(host_type: str | None) -> str:
    if not host_type:
        return ""
    return HOST_TYPE_LABELS.get(host_type, host_type)


def normalize_host_type(value) -> str | None:
    """Map a user phrase or enum value onto a host type code."""
    if value is None:
        return None
    text = str(value).strip()
    if text in ("", "未知", "无", "None", "null"):
        return None
    if text in _HOST_TYPE_ALIASES:
        return _HOST_TYPE_ALIASES[text]
    lowered = text.lower()
    if lowered in _HOST_TYPE_ALIASES:
        return _HOST_TYPE_ALIASES[lowered]
    for alias, code in sorted(_HOST_TYPE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if alias in text or alias in lowered:
            return code
    return None


def parse_player_count(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value).strip()
    if text in ("", "未知", "无"):
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else None


def is_known(value) -> bool:
    return value not in (None, "", "未知", "无")

class StateEnum(Enum):
    CLASSIFY = "classify"
    APPOINTMENT = "appointment"
    CONSULT = "consult"
    OTHER = "other"
    
class SharedState:
    def __init__(self):
        self.value = StateEnum.CLASSIFY
