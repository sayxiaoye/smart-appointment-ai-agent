"""
消息构建器

负责构建桌游预约的响应消息
"""

from typing import Dict, Any, List
from config.constants import host_type_label, is_known


class MessageBuilder:
    """消息构建器"""

    def __init__(self):
        self.missing_info_prompts = {
            "start_time": "请问您想预约哪一天、几点开局？",
            "duration": "请问预计玩多久？",
            "game": "请问想玩哪款桌游？例如血染钟楼、卡卡颂、恐龙小镇。",
            "player_count": "请问一共几位玩家？",
            "host_type": "请问需要哪种主持？专业主持人、店员带玩、自助，或少儿向主持。",
            "preference": "对主持人的风格有偏好吗？没有的话可以直接说没有。",
        }

    def create_appointment_success_message(self, host: Dict[str, Any], appointment_history: Dict[str, Any]) -> str:
        summary = self._booking_summary(appointment_history)
        label = host_type_label(appointment_history.get("host_type"))
        if host.get("is_recommendation"):
            original = host.get("original_host") or {}
            return (
                f"\n机器人：{summary}主持人：{host['name']}（{label}）。预约成功！"
                f"（原指定的{original.get('name', '')}时间冲突，{host['name']}同样擅长这类局。）\n"
            )
        return f"\n机器人：{summary}主持人：{host['name']}（{label}）。预约成功！\n"

    def create_self_play_success_message(self, appointment_history: Dict[str, Any]) -> str:
        summary = self._booking_summary(appointment_history)
        return f"\n机器人：{summary}这场是自助，不安排主持人。预约成功！\n"

    def create_host_recommendation_message(self, original_host: Dict[str, Any],
                                           recommended_host: Dict[str, Any],
                                           appointment_history: Dict[str, Any],
                                           llm=None) -> str:
        game = appointment_history.get("game", "桌游")
        start_time = appointment_history.get("start_time", "")
        label = host_type_label(appointment_history.get("host_type"))

        if llm:
            try:
                prompt = f"""
你是桌游店预约助手。用户想约{original_host['name']}主持《{game}》，但{original_host['name']}在{start_time}没空。

可改约的主持人：
- 姓名：{recommended_host['name']}
- 主持类型：{label}
- 专长：{recommended_host.get('specialty', '')}

原主持人专长：{original_host.get('specialty', '')}

请生成一段80字以内的推荐，说明原主持人没空，推荐这位同类型主持人，并询问是否改约。只输出给用户看的话。
"""
                response = llm.invoke(prompt)
                generated = response.content.strip() if hasattr(response, "content") else ""
                if generated:
                    return f"\n机器人：{generated}\n"
            except Exception as exc:
                print(f"LLM生成推荐消息失败: {exc}")

        return (
            f"\n机器人：抱歉，{original_host['name']}在{start_time}没空。"
            f"{recommended_host['name']}也能做{label or '这类'}主持，这个时段有空。"
            f"要改约{recommended_host['name']}吗？\n"
        )

    def create_recommendation_declined_message(self, llm=None) -> str:
        if llm:
            try:
                prompt = "用户拒绝了推荐的桌游主持人。用60字以内表示理解，并建议换时间或重新选主持类型。只输出给用户看的话。"
                response = llm.invoke(prompt)
                generated = response.content.strip() if hasattr(response, "content") else ""
                if generated:
                    return f"\n机器人：{generated}\n"
            except Exception as exc:
                print(f"LLM生成拒绝消息失败: {exc}")
        return "\n机器人：好的。您可以换一个时间，或告诉我其他主持类型，我再帮您看档期。\n"

    def create_appointment_failure_message(self, host_name: str) -> str:
        if is_known(host_name):
            from services.appointment_service import AppointmentService
            host = AppointmentService().get_host_by_name(host_name)
            if host:
                return f"\n机器人：抱歉，{host_name}在这个时段没空，也没有同类型的主持人能顶上。请换个时间，或改主持类型。\n"
            return f"\n机器人：抱歉，没有找到名为「{host_name}」的主持人。请确认姓名，或改由我们按类型安排。\n"
        return "\n机器人：抱歉，这个时段没有合适的主持人空闲。请换个时间，或改成自助（如果这款游戏允许）。\n"

    def create_missing_info_questions(self, missing_info: List[str], appointment_history: Dict[str, Any] = None) -> str:
        questions = [self.missing_info_prompts.get(field, f"请补充{field}") for field in missing_info]
        prefix = ""
        history = appointment_history or {}
        if history.get("duration_defaulted") and "duration" not in missing_info and history.get("game"):
            prefix = f"时长先按《{history['game']}》的建议 {history.get('duration')} 安排。"
        return "\n" + prefix + " ".join(questions) + "\n"

    def create_clarify_message(self, question: str, appointment_history: Dict[str, Any] = None) -> str:
        history = appointment_history or {}
        prefix = ""
        if history.get("duration_defaulted") and history.get("game"):
            prefix = f"时长先按《{history['game']}》的建议 {history.get('duration')} 安排。"
        return "\n" + prefix + question + "\n"

    def create_unrelated_message(self) -> str:
        return "[REPLY][预约机器人]抱歉，我只能处理桌游预约。您可以告诉我想玩的游戏、人数、时间和主持方式。\n"

    def create_parse_error_message(self) -> str:
        return "[REPLY][预约机器人]\n机器人：解析失败，请重试。\n"

    def create_save_failure_message(self) -> str:
        return "\n机器人：抱歉，预约保存失败，请重试。\n"

    def _booking_summary(self, appointment_history: Dict[str, Any]) -> str:
        game = appointment_history.get("game") or "桌游"
        players = appointment_history.get("player_count")
        start_time = appointment_history.get("start_time") or ""
        duration = appointment_history.get("duration") or ""
        duration_note = "（已按建议时长安排）" if appointment_history.get("duration_defaulted") else ""
        player_text = f"{players}人，" if players else ""
        return f"已为您预约《{game}》，{player_text}{start_time}，时长{duration}{duration_note}。"
