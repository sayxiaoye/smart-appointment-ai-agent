"""把「明天13点」解析成确定时刻。不走预约槽位解析。"""

import re
from datetime import datetime
from typing import Optional

from config.time_config import time_config


_CLOCK = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")


def build_time_prompt(text: str, now: datetime) -> str:
    current = time_config.format_datetime(now) if now.tzinfo else now.strftime("%Y-%m-%d %H:%M")
    return (
        f"当前北京时间是{current}。\n"
        "从用户的话里提取一个开始时刻。\n"
        "只输出 YYYY-MM-DD HH:MM。无法确定时只输出 UNKNOWN。\n"
        "不要输出其他文字。\n"
        f"用户：{text}"
    )


def parse_moment(text: str, llm, now: Optional[datetime] = None) -> Optional[datetime]:
    current = now or time_config.now()
    message = llm.invoke(build_time_prompt(text, current))
    content = message.content if hasattr(message, "content") else str(message)
    if "UNKNOWN" in content.upper():
        return None
    matched = _CLOCK.search(content)
    if not matched:
        return None
    return datetime.strptime(matched.group(), "%Y-%m-%d %H:%M")
