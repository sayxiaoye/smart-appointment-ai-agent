"""
AppointmentAgent 功能测试

测试预约代理的核心功能：
1. 解析用户预约请求 
2. 管理预约状态和信息收集
3. 处理无关请求
4. 完成预约流程
"""

import pytest
import asyncio
from agents.appointment_agent import AppointmentAgent


class TestAppointmentAgentCoreFeatures:
    """测试预约代理核心功能"""
    
    def test_should_extract_user_info_from_natural_language(self):
        """
        测试：预约代理应该能从自然语言中提取预约信息
        
        用户说："我想预约明天下午2点玩卡卡颂，4个人，自助"
        应该提取到：
        - 时间: 明天下午2点
        - 游戏: 卡卡颂
        - 主持类型: 自助
        
        这个测试验证整个自然语言处理流程：
        用户输入 -> LLM处理 -> JSON解析 -> 结果验证
        """
        agent = AppointmentAgent()
        
        user_input = "我想预约明天下午2点玩卡卡颂，4个人，自助"
        
        # 使用真实的解析流程：通过LLM处理用户输入
        from langchain_core.chat_history import InMemoryChatMessageHistory
        chat_history = InMemoryChatMessageHistory()
        
        # 模拟流式解析过程，获取LLM的完整响应
        ai_content = ""
        for token in agent.input_parser.parse_stream(user_input, chat_history):
            ai_content += token
        
        # 解析LLM返回的JSON
        result = agent.input_parser.parse_data(ai_content)
        
        # 验证解析结果包含预期信息
        from config.constants import normalize_host_type
        assert "卡卡颂" in str(result.get("game")), f"应该提取到卡卡颂，但得到：{result.get('game')}"
        assert normalize_host_type(result.get("host_type")) == "self_play", f"应该提取到自助，但得到：{result.get('host_type')}"
        
        # 验证时间信息（明天下午2点应该被转换为标准格式）
        start_time = result["start_time"]
        assert start_time != "未知", f"应该提取到时间信息，但得到：{start_time}"
        assert "14:00" in start_time, f"时间应该转换为14:00格式，但得到：{start_time}"
        
        # 验证这不是无关请求
        assert result["unrelated"] == False, "预约请求不应该被标记为无关"
    
    def test_should_track_appointment_state_correctly(self):
        """
        测试：预约代理应该正确跟踪预约状态
        
        用户分步骤提供信息：
        1. "我要预约卡卡颂" -> 应该记录游戏=卡卡颂
        2. "明天下午2点" -> 应该记录时间，并保持游戏
        """
        agent = AppointmentAgent()

        assert agent.appointment_history["game"] is None
        assert agent.appointment_history["start_time"] is None
        assert agent.appointment_history["host_type"] is None

        data1 = {"game": "卡卡颂"}
        agent.appointment_processor.update_history_from_data(agent.appointment_history, data1)

        assert agent.appointment_history["game"] == "卡卡颂"
        assert agent.appointment_history["start_time"] is None

        data2 = {"start_time": "2026-11-24 14:00"}
        agent.appointment_processor.update_history_from_data(agent.appointment_history, data2)

        assert agent.appointment_history["game"] == "卡卡颂"
        assert agent.appointment_history["start_time"] == "2026-11-24 14:00"
    
    def test_should_identify_unrelated_requests(self):
        """
        测试：预约代理应该能识别与预约无关的请求
        
        用户说："今天天气怎么样？"
        应该识别为无关请求，而不是尝试解析预约信息
        """
        agent = AppointmentAgent()
        
        unrelated_input = "今天天气怎么样？"
        
        # 使用真实的解析流程：通过LLM处理用户输入
        from langchain_core.chat_history import InMemoryChatMessageHistory
        chat_history = InMemoryChatMessageHistory()
        
        # 模拟流式解析过程，获取LLM的完整响应
        ai_content = ""
        for token in agent.input_parser.parse_stream(unrelated_input, chat_history):
            ai_content += token
        
        # 解析LLM返回的JSON
        result = agent.input_parser.parse_data(ai_content)
        
        # 应该被标记为无关请求
        assert result.get("unrelated", False) == True, f"应该识别为无关请求，但得到：{result}"
    
    def test_should_complete_appointment_when_all_info_collected(self):
        """
        测试：当收集到所有必需信息时，应该完成预约
        
        提供游戏、人数、自助和开始时间后应该完成，时长用目录建议值补上。
        """
        agent = AppointmentAgent()

        complete_data = {
            "start_time": "2026-11-24 14:00",
            "game": "卡卡颂",
            "host_type": "自助",
            "player_count": 4,
        }

        finished = agent.appointment_processor.update_history_from_data(
            agent.appointment_history,
            complete_data
        )

        assert finished is True, f"提供完整信息后应该完成预约，但finished={finished}"
        assert agent.appointment_history["game"] == "卡卡颂"
        assert agent.appointment_history["host_type"] == "self_play"
        assert agent.appointment_history["player_count"] == 4
        assert agent.appointment_history["duration"] == "45分钟"
        assert agent.appointment_processor.requires_host(agent.appointment_history) is False
    
    @pytest.mark.asyncio
    async def test_should_handle_incomplete_info_gracefully(self):
        """
        测试：当信息不完整时，应该引导用户补充
        
        只提供部分信息时，应该询问缺失的信息
        """
        agent = AppointmentAgent()
        
        incomplete_data = {"game": "卡卡颂"}

        finished = agent.appointment_processor.update_history_from_data(
            agent.appointment_history,
            incomplete_data
        )

        assert finished is False, "信息不完整时不应该完成预约"

        try:
            response_tokens = []
            async for token in agent.appointment_processor.handle_incomplete_info(
                incomplete_data, agent.appointment_history
            ):
                response_tokens.append(token)

            response = "".join(response_tokens)
            assert len(response) > 0, "应该返回引导信息"
            assert "几点" in response or "玩家" in response or "主持" in response, f"应该追问缺失信息，但得到：{response}"
            
        except Exception as e:
            pytest.fail(f"处理不完整信息时出错：{e}")


class TestAppointmentAgentEdgeCases:
    """测试边界情况和错误处理"""
    
    def test_should_handle_invalid_input(self):
        """
        测试：应该处理无效输入而不崩溃
        """
        agent = AppointmentAgent()
        
        # 测试空输入
        try:
            result = agent.input_parser.parse_data("")
            # 不应该崩溃，应该有某种处理方式
        except Exception as e:
            # 如果抛出异常，至少应该是可预期的异常类型
            assert isinstance(e, (ValueError, TypeError)), f"应该是可预期的异常类型，但得到：{type(e)}"
    
    def test_should_reset_state_properly(self):
        """
        测试：应该正确重置预约状态
        """
        agent = AppointmentAgent()
        
        # 设置一些状态
        agent.appointment_history["game"] = "卡卡颂"
        agent.appointment_history["start_time"] = "明天"
        agent.finished = True

        agent.reset()

        assert agent.appointment_history["game"] is None
        assert agent.appointment_history["start_time"] is None
        assert agent.finished is False
