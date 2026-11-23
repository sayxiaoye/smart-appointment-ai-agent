"""主持人排班可以按日期查询。"""

import asyncio

import pytest
from fastapi import HTTPException

from api.host import get_all_hosts_schedule, resolve_schedule_date


def test_missing_date_means_today():
    day = resolve_schedule_date(None)
    assert day.hour == 0
    assert day.strftime("%Y-%m-%d")


def test_invalid_date_is_rejected():
    with pytest.raises(HTTPException) as caught:
        resolve_schedule_date("2026/11/24")
    assert caught.value.status_code == 400


def test_schedule_for_a_chosen_date_returns_hosts():
    data = asyncio.run(get_all_hosts_schedule("2026-11-24"))
    assert data
    assert data[0]["date"] == "2026-11-24"
    assert "host_name" in data[0]
    assert "busy_periods" in data[0]
