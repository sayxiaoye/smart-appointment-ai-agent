"""事实问题的说法识别和时间追问。"""

from datetime import datetime
from pathlib import Path

from agents.factual.intent import classify_utterance
from agents.factual.responder import ASK_TIME, FactualResponder
from agents.factual.time_parse import build_time_prompt
from services.game_catalog_service import GameCatalogService


HOSTS = ["陈屿", "林可"]
GAME = {
    "name": "血染钟楼",
    "min_players": 5,
    "max_players": 12,
    "duration_min": 90,
    "needs_host": True,
    "allowed_host_types": ["pro_host"],
}


def _resolve(text):
    service = GameCatalogService.__new__(GameCatalogService)
    service.list_games = lambda: [GAME]
    return GameCatalogService.resolve_game(service, text)


def test_booking_phrase_is_not_an_availability_question():
    decision = classify_utterance("帮我预约陈屿明天 13:00 的血染钟楼", HOSTS, _resolve)
    assert decision["kind"] == "booking"


def test_address_rules_and_price_are_not_factual_questions():
    for text in ("门店地址", "血染钟楼怎么玩", "收费"):
        assert classify_utterance(text, HOSTS, _resolve)["kind"] == "none"


def test_zero_or_several_host_names_ask_which_host():
    assert classify_utterance("明天13点有空吗", HOSTS, _resolve)["kind"] == "ask_host"
    assert classify_utterance("陈屿和林可明天13点有空吗", HOSTS, _resolve)["kind"] == "ask_host"


def test_unknown_game_does_not_enter_catalog_fields():
    decision = classify_utterance("麻将几个人", HOSTS, _resolve)
    assert decision["kind"] == "game_missing"


def test_time_prompt_includes_beijing_now_and_skips_booking_parser():
    prompt = build_time_prompt("陈屿明天13点有空吗", datetime(2026, 11, 23, 22, 0))
    assert "2026-11-23 22:00" in prompt
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            Path("agents/factual/time_parse.py"),
            Path("agents/factual/responder.py"),
            Path("agents/factual/intent.py"),
        )
    )
    assert "parse_stream" not in source


def test_missing_time_asks_only_for_time_without_knowledge_text():
    calls = []

    def parse_time(text, now):
        calls.append(text)
        return None

    responder = FactualResponder(
        hosts=[{"id": 1, "name": "陈屿", "gender": "男", "host_types": ["pro_host"], "specialty": "推理"}],
        parse_time=parse_time,
    )

    async def run():
        return await responder.reply("陈屿有没有空", None)

    import asyncio

    reply = asyncio.run(run())
    assert reply == ASK_TIME
    assert calls == []
    assert "知识库" not in reply
