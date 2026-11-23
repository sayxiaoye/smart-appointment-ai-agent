"""
预约处理器

负责协调整个桌游预约流程
"""

import os
import asyncio
import aiohttp
from typing import Dict, Any, AsyncGenerator, Optional
from .input_parser import InputParser
from .host_finder import HostFinder
from .message_builder import MessageBuilder
from .appointment_database import AppointmentDatabase
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate
from config.constants import HostType, host_type_label, is_known, normalize_host_type, parse_player_count


class WeatherMCPTool(BaseTool):
    """Weather API 工具"""
    name: str = "get_current_weather"
    description: str = "获取指定城市的当前天气信息"

    def __init__(self):
        super().__init__()
        self._api_key = os.getenv("OPENWEATHER_API_KEY")
        self._base_url = "https://api.openweathermap.org/data/2.5/weather"

    async def _get_weather_data(self, city: str = "Beijing") -> str:
        if not self._api_key:
            return "北京今天天气晴朗，温度适宜，建议您注意防晒"

        try:
            params = {
                "q": city,
                "appid": self._api_key,
                "units": "metric",
                "lang": "zh_cn",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(self._base_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        temp = data["main"]["temp"]
                        feels_like = data["main"]["feels_like"]
                        description = data["weather"][0]["description"]
                        humidity = data["main"]["humidity"]
                        wind_speed = data.get("wind", {}).get("speed", 0)
                        return f"北京当前天气：{description}，气温{temp}°C（体感{feels_like}°C），湿度{humidity}%，风速{wind_speed}m/s"
                    return "北京今天天气晴朗，温度适宜，建议您出行注意防晒"
        except Exception:
            return "北京今天天气宜人，温度适中，适合出行"

    def _run(self, city: str = "Beijing") -> str:
        return asyncio.run(self._get_weather_data(city))

    async def _arun(self, city: str = "Beijing") -> str:
        return await self._get_weather_data(city)


class AppointmentProcessor:
    """预约处理器"""

    def __init__(self, input_parser: InputParser, host_finder: HostFinder,
                 message_builder: MessageBuilder, appointment_database: AppointmentDatabase,
                 llm=None, catalog=None, host_service=None):
        self.input_parser = input_parser
        self.host_finder = host_finder
        self.message_builder = message_builder
        self.appointment_database = appointment_database
        self.llm = llm
        self.catalog = catalog
        self.host_service = host_service

        if self.llm:
            self.weather_tool = WeatherMCPTool()
            self.tools = [self.weather_tool]
            self.agent_prompt = ChatPromptTemplate.from_messages([
                ("system", "你是一个智能助手，可以获取天气信息并生成个性化的预约成功提示。"),
                ("human", "{input}"),
                ("placeholder", "{agent_scratchpad}"),
            ])
            self.weather_agent = create_openai_tools_agent(self.llm, self.tools, self.agent_prompt)
            self.agent_executor = AgentExecutor(agent=self.weather_agent, tools=self.tools, verbose=True)

    def requires_host(self, appointment_history: Dict[str, Any]) -> bool:
        return appointment_history.get("host_type") != HostType.SELF_PLAY.value

    def update_history_from_data(self, appointment_history: Dict[str, Any], data: Dict[str, Any]) -> bool:
        if appointment_history.get("awaiting_confirmation"):
            return self._handle_recommendation_response(appointment_history, data)

        appointment_history.pop("clarify_question", None)
        appointment_history.pop("invalid_fields", None)

        for key in ("game", "player_count", "start_time", "duration", "host_name", "preference"):
            if is_known(data.get(key)):
                appointment_history[key] = data[key]
                if key == "duration":
                    appointment_history["duration_defaulted"] = False

        player_count = parse_player_count(appointment_history.get("player_count"))
        if player_count is not None:
            appointment_history["player_count"] = player_count
        elif is_known(appointment_history.get("player_count")):
            appointment_history["clarify_question"] = "人数我没识别出来，请直接告诉我几位玩家。"
            appointment_history["player_count"] = None

        game = self._resolve_game(appointment_history)

        if is_known(data.get("host_type")):
            normalized = normalize_host_type(data.get("host_type"))
            if not normalized:
                appointment_history["host_type"] = None
                appointment_history["clarify_question"] = "主持类型请从专业主持人、店员带玩、自助、少儿向主持里选择。"
            else:
                appointment_history["host_type"] = normalized

        if appointment_history.get("clarify_question"):
            return False

        self._infer_host_type(appointment_history)
        if appointment_history.get("clarify_question"):
            return False

        if game and player_count is not None and appointment_history.get("host_type"):
            validation = self._catalog().validate_selection(game, player_count, appointment_history["host_type"])
            if not validation["valid"]:
                appointment_history["invalid_fields"] = validation["invalid_fields"]
                appointment_history["clarify_question"] = validation["clarify_question"]
                return False
            if not self._named_host_supports_type(appointment_history):
                return False

        return self._has_required_fields(appointment_history)

    def _catalog(self):
        if self.catalog is None:
            from services.game_catalog_service import GameCatalogService
            self.catalog = GameCatalogService()
        return self.catalog

    def _hosts(self):
        if self.host_service is None:
            from services.host_service import HostService
            self.host_service = HostService()
        return self.host_service

    def _resolve_game(self, appointment_history: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not is_known(appointment_history.get("game")):
            appointment_history["game_id"] = None
            return None
        game = self._catalog().resolve_game(appointment_history["game"])
        if not game:
            names = "、".join(self._catalog().list_game_names())
            appointment_history["clarify_question"] = f"没有找到「{appointment_history['game']}」。目前可约：{names}。"
            appointment_history["game"] = None
            appointment_history["game_id"] = None
            return None
        appointment_history["game"] = game["name"]
        appointment_history["game_id"] = game["id"]
        if not is_known(appointment_history.get("duration")) or appointment_history.get("duration_defaulted"):
            appointment_history["duration"] = f"{game['duration_min']}分钟"
            appointment_history["duration_defaulted"] = True
        return game

    def _infer_host_type(self, appointment_history: Dict[str, Any]) -> None:
        if appointment_history.get("host_type") or not is_known(appointment_history.get("host_name")):
            return
        host = self._hosts().get_host_by_name(appointment_history["host_name"])
        if not host:
            return
        types = [item for item in (host.get("host_types") or []) if item != HostType.SELF_PLAY.value]
        if len(types) == 1:
            appointment_history["host_type"] = types[0]
        else:
            labels = "、".join(host_type_label(item) for item in types)
            appointment_history["clarify_question"] = f"{host['name']}可以做这些主持：{labels}。请选一种。"

    def _named_host_supports_type(self, appointment_history: Dict[str, Any]) -> bool:
        host_name = appointment_history.get("host_name")
        host_type = appointment_history.get("host_type")
        if not is_known(host_name) or host_type == HostType.SELF_PLAY.value:
            return True
        host = self._hosts().get_host_by_name(host_name)
        if not host:
            return True
        if host_type not in (host.get("host_types") or []):
            labels = "、".join(host_type_label(item) for item in (host.get("host_types") or []))
            appointment_history["clarify_question"] = (
                f"{host['name']}不能做{host_type_label(host_type)}，可以做：{labels}。"
            )
            return False
        return True

    def _has_required_fields(self, appointment_history: Dict[str, Any]) -> bool:
        required = ["start_time", "game", "player_count", "duration"]
        if self.requires_host(appointment_history):
            if not is_known(appointment_history.get("host_name")) or not appointment_history.get("host_type"):
                required.append("host_type")
        return all(is_known(appointment_history.get(field)) for field in required)

    def _handle_recommendation_response(self, appointment_history: Dict[str, Any], data: Dict[str, Any]) -> bool:
        user_response = str(data.get("confirmation") or "").lower()
        positive_responses = ["是", "好", "可以", "同意", "确定", "yes", "ok", "行"]
        negative_responses = ["不", "不要", "不行", "不同意", "换", "no"]
        is_positive = any(item in user_response for item in positive_responses)
        is_negative = any(item in user_response for item in negative_responses)

        if is_positive and not is_negative:
            recommended = appointment_history.get("recommended_host")
            if recommended:
                appointment_history["confirmed_host"] = recommended
                appointment_history["awaiting_confirmation"] = False
                return True
        elif is_negative:
            appointment_history["recommendation_declined"] = True
            appointment_history["awaiting_confirmation"] = False
            return True
        return False

    async def handle_unrelated_request(self, user_input: str, unrelated_callback, state) -> AsyncGenerator[str, None]:
        if unrelated_callback:
            try:
                yield "[REPLY][预约机器人]和预约信息无关，已交给归类机器人处理\n"
                result = await unrelated_callback(user_input)
                if hasattr(result, "__aiter__"):
                    async for token in result:
                        yield token
                else:
                    yield result
            except Exception as exc:
                yield f"[ERROR]处理请求时发生错误: {str(exc)}\n"
                yield self.message_builder.create_unrelated_message()
        else:
            yield self.message_builder.create_unrelated_message()

    async def handle_complete_appointment(self, appointment_history: Dict[str, Any],
                                        session_id: str) -> AsyncGenerator[str, None]:
        if appointment_history.get("recommendation_declined"):
            reply = self.message_builder.create_recommendation_declined_message(self.llm)
            yield f"[REPLY][预约机器人]{reply}"
            appointment_history.pop("recommendation_declined", None)
            appointment_history.pop("recommended_host", None)
            appointment_history.pop("original_host", None)
            return

        if appointment_history.get("confirmed_host"):
            host = appointment_history["confirmed_host"]
            host["is_recommendation"] = True
            host["original_host"] = appointment_history.get("original_host")
            reply = await self._process_successful_appointment(host, appointment_history, session_id)
            yield f"[REPLY][预约机器人]{reply}"
            appointment_history.pop("confirmed_host", None)
            appointment_history.pop("recommended_host", None)
            appointment_history.pop("original_host", None)
            return

        if appointment_history.get("awaiting_confirmation"):
            yield "[REPLY][预约机器人]\n机器人：请明确回复「是」或「不」，我再为您安排。\n"
            return

        if not self.requires_host(appointment_history):
            reply = await self._process_self_play(appointment_history, session_id)
            yield f"[REPLY][预约机器人]{reply}"
            return

        thought_msgs = []

        def collect_thoughts(msg):
            thought_msgs.append(msg)

        host = self.host_finder.find_host_with_thought(appointment_history, collect_thoughts)
        for msg in thought_msgs:
            yield msg

        host_name = appointment_history.get("host_name")
        if host and host.get("requires_confirmation"):
            recommendation_msg = self.message_builder.create_host_recommendation_message(
                host.get("original_host"), host.get("recommended_host"), appointment_history, self.llm
            )
            yield f"[REPLY][预约机器人]{recommendation_msg}"
            appointment_history["recommended_host"] = host.get("recommended_host")
            appointment_history["original_host"] = host.get("original_host")
            appointment_history["awaiting_confirmation"] = True
            yield "[SIGNAL]recommendation_pending"
            return

        if host:
            reply = await self._process_successful_appointment(host, appointment_history, session_id)
            yield f"[REPLY][预约机器人]{reply}"
            return

        reply = self.message_builder.create_appointment_failure_message(host_name)
        yield f"[REPLY][预约机器人]{reply}"

    async def _process_self_play(self, appointment_history: Dict[str, Any], session_id: str) -> str:
        start_time, end_time, _ = self.host_finder.parse_time_and_duration(
            appointment_history["start_time"], appointment_history["duration"]
        )
        if not start_time or not end_time:
            return self.message_builder.create_appointment_failure_message(None)
        success = self.appointment_database.save_appointment(
            None, start_time, end_time, appointment_history, session_id
        )
        if success:
            return self.message_builder.create_self_play_success_message(appointment_history)
        return self.message_builder.create_save_failure_message()

    async def _process_successful_appointment(self, host: Dict[str, Any],
                                           appointment_history: Dict[str, Any], session_id: str) -> str:
        start_time, end_time, _ = self.host_finder.parse_time_and_duration(
            appointment_history["start_time"], appointment_history["duration"]
        )
        success = self.appointment_database.save_appointment(
            host["id"], start_time, end_time, appointment_history, session_id
        )
        if not success:
            return self.message_builder.create_save_failure_message()

        self.appointment_database.update_memory_schedule(host["id"], start_time, end_time)
        if self.llm and hasattr(self, "agent_executor"):
            label = host_type_label(appointment_history.get("host_type"))
            prompt = (
                "请获取北京今天的天气信息，然后结合天气为用户生成一段温馨的桌游预约成功提示。"
                f"游戏：{appointment_history.get('game')}，人数：{appointment_history.get('player_count')}，"
                f"主持人：{host['name']}，主持类型：{label}，专长：{host.get('specialty', '')}。"
            )
            try:
                result = await self.agent_executor.ainvoke({"input": prompt})
                agent_output = result.get("output", "")
                summary = self.message_builder.create_appointment_success_message(host, appointment_history).strip()
                return f"\n{summary}\n{agent_output}\n"
            except Exception as exc:
                print(f"Agent调用失败: {exc}")
        return self.message_builder.create_appointment_success_message(host, appointment_history)

    async def handle_incomplete_info(self, data: Dict[str, Any], appointment_history: Dict[str, Any]) -> AsyncGenerator[str, None]:
        if appointment_history.get("clarify_question"):
            reply = self.message_builder.create_clarify_message(
                appointment_history["clarify_question"], appointment_history
            )
            yield "[THOUGHT][预约机器人]预约信息需要澄清，先告诉用户哪里不合适"
            yield f"[REPLY][预约机器人]{reply}"
            return

        missing = []
        if not is_known(appointment_history.get("game")):
            missing.append("game")
        if not is_known(appointment_history.get("player_count")):
            missing.append("player_count")
        if not is_known(appointment_history.get("start_time")):
            missing.append("start_time")
        if not is_known(appointment_history.get("duration")):
            missing.append("duration")
        if self.requires_host(appointment_history) and not appointment_history.get("host_type"):
            if not is_known(appointment_history.get("host_name")) or not appointment_history.get("host_type"):
                missing.append("host_type")

        reply = self.message_builder.create_missing_info_questions(missing, appointment_history)
        yield f"[THOUGHT][预约机器人]预约信息不完整，缺少：{', '.join(missing)}"
        yield f"[REPLY][预约机器人]{reply}"
