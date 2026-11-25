"""空档计算：某一分钟、全天空档、不点名。"""

from datetime import datetime

from agents.factual.schedule import assess_moment, free_windows, hosts_free_at


DAY = datetime(2026, 11, 24)


def _busy(start_hour, start_minute, end_hour, end_minute):
    return {
        "start": DAY.replace(hour=start_hour, minute=start_minute),
        "end": DAY.replace(hour=end_hour, minute=end_minute),
        "status": "busy",
    }


def test_moment_free_still_lists_later_busy_slot():
    result = assess_moment(DAY.replace(hour=13), [_busy(15, 0, 16, 0)])
    assert result["outside"] is False
    assert result["free"] is True
    assert result["overlap"] is None
    assert result["day_busy"] == [
        (DAY.replace(hour=15), DAY.replace(hour=16)),
    ]


def test_moment_overlapping_busy_slot():
    result = assess_moment(DAY.replace(hour=13), [_busy(12, 30, 14, 0)])
    assert result["free"] is False
    assert result["overlap"] == (DAY.replace(hour=12, minute=30), DAY.replace(hour=14))


def test_moment_outside_business_hours():
    result = assess_moment(DAY.replace(hour=10), [_busy(15, 0, 16, 0)])
    assert result["outside"] is True
    assert result["free"] is False
    assert result["overlap"] is None


def test_free_windows_split_by_one_busy_interval():
    windows = free_windows(DAY, [_busy(13, 0, 15, 0)])
    assert windows == [
        (DAY.replace(hour=12), DAY.replace(hour=13)),
        (DAY.replace(hour=15), DAY.replace(hour=22)),
    ]


def test_free_windows_empty_when_business_day_is_full():
    assert free_windows(DAY, [_busy(12, 0, 22, 0)]) == []


def test_unnamed_moment_skips_the_busy_host():
    hosts = [
        {"name": "陈屿", "schedules": []},
        {"name": "林可", "schedules": [_busy(12, 30, 14, 0)]},
        {"name": "周宁", "schedules": [_busy(18, 0, 19, 0)]},
    ]
    assert hosts_free_at(DAY.replace(hour=13), hosts) == ["陈屿", "周宁"]
