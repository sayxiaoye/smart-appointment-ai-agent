"""用忙碌排班判断某一分钟，以及营业时间内的空档。"""

from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


OPEN_HOUR = 12
CLOSE_HOUR = 22


def _naive(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value


def _bounds(item: Dict[str, Any]) -> Tuple[datetime, datetime, str]:
    start = item.get("start", item.get("start_time"))
    end = item.get("end", item.get("end_time"))
    return _naive(start), _naive(end), str(item.get("status") or "busy")


def _busy(schedules: Iterable[Dict[str, Any]]) -> List[Tuple[datetime, datetime]]:
    intervals = []
    for item in schedules or []:
        start, end, status = _bounds(item)
        if status == "busy" and start < end:
            intervals.append((start, end))
    intervals.sort()
    return intervals


def _same_day(left: datetime, right: datetime) -> bool:
    return left.date() == right.date()


def day_busy(moment: datetime, schedules: Iterable[Dict[str, Any]]) -> List[Tuple[datetime, datetime]]:
    moment = _naive(moment)
    return [(start, end) for start, end in _busy(schedules) if _same_day(start, moment)]


def outside_business_hours(moment: datetime) -> bool:
    moment = _naive(moment)
    return moment.hour < OPEN_HOUR or moment.hour >= CLOSE_HOUR


def assess_moment(moment: datetime, schedules: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """判断 [t, t+1 分钟) 是否与当天忙碌排班重叠。"""
    moment = _naive(moment)
    busy = day_busy(moment, schedules)
    if outside_business_hours(moment):
        return {"outside": True, "free": False, "overlap": None, "day_busy": busy}
    window_end = moment + timedelta(minutes=1)
    overlap = None
    for start, end in busy:
        if start < window_end and end > moment:
            overlap = (start, end)
            break
    return {"outside": False, "free": overlap is None, "overlap": overlap, "day_busy": busy}


def free_windows(day: datetime, schedules: Iterable[Dict[str, Any]]) -> List[Tuple[datetime, datetime]]:
    """从当天 12:00–22:00 中减去忙碌区间。"""
    day = _naive(day)
    open_at = datetime(day.year, day.month, day.day, OPEN_HOUR, 0)
    close_at = datetime(day.year, day.month, day.day, CLOSE_HOUR, 0)
    clipped = []
    for start, end in day_busy(day, schedules):
        left = max(start, open_at)
        right = min(end, close_at)
        if left < right:
            clipped.append((left, right))
    clipped.sort()
    merged: List[List[datetime]] = []
    for start, end in clipped:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    windows = []
    cursor = open_at
    for start, end in merged:
        if cursor < start:
            windows.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < close_at:
        windows.append((cursor, close_at))
    return windows


def hosts_free_at(moment: datetime, hosts: Sequence[Dict[str, Any]]) -> List[str]:
    """返回该分钟没有忙碌重叠的主持人姓名。营业时间外返回空列表。"""
    if outside_business_hours(moment):
        return []
    names = []
    for host in hosts:
        result = assess_moment(moment, host.get("schedules") or [])
        if result["free"]:
            names.append(host["name"])
    return names
