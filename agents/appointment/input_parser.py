"""
用户输入解析器

负责解析用户输入并提取预约相关信息
"""

import json
from typing import Dict, Any, Generator
from langchain.prompts import PromptTemplate
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, AIMessage


class InputParser:
    """用户输入解析器"""
    
    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self.prompt = self._create_prompt_template()
        self.chain = self.prompt | self.llm
    
    def _create_prompt_template(self) -> PromptTemplate:
        """创建预约信息提取的Prompt模板"""
        from config.time_config import time_config
        current_date = time_config.current_date_str()
        current_datetime = time_config.current_datetime_str()
        
        return PromptTemplate(
            input_variables=["history", "user_input"],
            template=(
                "你是桌游店的预约机器人，负责帮用户预约桌游场次。\n"
                f"当前日期是{current_date}，当前北京时间是{current_datetime}。\n"
                "可约游戏包括：血染钟楼、卡卡颂、晴日岛、阿瓦隆、璀璨宝石、恐龙小镇。\n"
                "主持类型只能是：pro_host（专业主持人）、staff_guide（店员带玩）、self_play（自助）、kids_host（少儿向主持）。\n"
                "当前已知信息：{history}\n"
                "用户输入：{user_input}\n"
                "特别注意：如果用户是在回应主持人推荐（如\"是\"、\"好\"、\"可以\"、\"不\"、\"不要\"），请写入confirmation，不要标记为unrelated。\n"
                "重要：只输出纯JSON，不要markdown，不要额外说明：\n"
                "{{\n"
                '  "game": "桌游名称，没说则为未知",\n'
                '  "host_type": "pro_host/staff_guide/self_play/kids_host/未知",\n'
                '  "player_count": "玩家人数的整数，没说则为未知",\n'
                '  "start_time": "预约开始时间，必须是YYYY-MM-DD HH:MM。今天下午3点写成当天15:00；只说时间没说日期则默认今天。完全没有时间则为未知",\n'
                '  "duration": "时长，如90分钟。没说则为未知",\n'
                '  "host_name": "用户点名的主持人姓名，没有则为未知",\n'
                '  "preference": "对主持人风格的自然语言偏好，没有则为无",\n'
                '  "confirmation": "如果在回应推荐确认，提取是/不等回复，否则为未知",\n'
                '  "info_complete": "自助时需要game、player_count、start_time；其他情况还需要host_type或host_name。时长可以未知。",\n'
                '  "unrelated": "和桌游预约无关则为true，否则为false。确认推荐的回复不是unrelated",\n'
                '  "missing_info": "缺少的字段名列表，如[start_time, player_count]"\n'
                "}}\n"
                "再次强调：只输出纯JSON。"
            )
        )
    
    def parse_stream(self, user_input: str, chat_history: InMemoryChatMessageHistory) -> Generator[str, None, str]:
        """流式解析用户输入"""
        # 添加用户消息到历史
        chat_history.add_message(HumanMessage(content=user_input))
        
        # 构建历史字符串
        history_str = "\n".join(
            [f"用户：{m.content}" if m.type == "human" else f"机器人：{m.content}" 
             for m in chat_history.messages]
        )
        
        # 流式调用LLM
        response_stream = self.chain.stream({"history": history_str, "user_input": user_input})
        ai_content = ""
        
        for chunk in response_stream:
            token = chunk.content if hasattr(chunk, "content") else str(chunk)
            ai_content += token
            yield token
        
        # 添加AI回复到历史
        chat_history.add_message(AIMessage(content=ai_content))
        return ai_content
    
    def parse_data(self, ai_content: str) -> Dict[str, Any]:
        """解析AI返回的JSON数据"""
        try:
            return json.loads(ai_content)
        except json.JSONDecodeError:
            return {
                "game": "未知",
                "host_type": "未知",
                "player_count": "未知",
                "start_time": "未知",
                "duration": "未知",
                "host_name": "未知",
                "preference": "无",
                "confirmation": "未知",
                "info_complete": False,
                "unrelated": False,
                "missing_info": ["所有信息"]
            }
