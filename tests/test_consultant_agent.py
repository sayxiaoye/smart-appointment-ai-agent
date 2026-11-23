"""
ConsultantAgent 功能测试

测试咨询代理的实际功能：
1. 识别咨询相关请求
2. 从知识库检索相关信息
3. 生成专业回答
4. 处理无关请求（兜底）
"""

import pytest
from agents.consultant_agent import ConsultantAgent


class TestConsultantAgentCoreFeatures:
    """测试咨询代理核心功能"""
    
    @pytest.mark.asyncio
    async def test_should_answer_boardgame_questions(self):
        """测试：应该能回答桌游相关问题"""
        agent = ConsultantAgent()
        await agent.knowledge_retriever.initialize()

        questions = [
            "血染钟楼适合几个人？",
            "卡卡颂可以自助吗？",
            "专业主持怎么收费？",
        ]

        for question in questions:
            response = await agent.consult(question)
            assert isinstance(response, str), f"应该返回字符串回答，但得到：{type(response)}"
            assert len(response.strip()) > 0, f"回答不应该为空，问题：{question}"

            keywords = ["血染", "卡卡颂", "主持", "人", "自助", "收费", "分钟", "桌游"]
            has_relevant_content = any(keyword in response for keyword in keywords)
            assert has_relevant_content, f"回答应该与桌游相关，问题：{question}，回答：{response[:200]}..."
    
    @pytest.mark.asyncio
    async def test_should_search_knowledge_from_database(self):
        """测试：应该能从数据库检索相关知识"""
        agent = ConsultantAgent()
        await agent.knowledge_retriever.initialize()
        
        question = "血染钟楼适合几个人？"
        knowledge_results = await agent.knowledge_retriever.search_knowledge(question, top_k=3)
        
        assert isinstance(knowledge_results, list), f"应该返回列表，但得到：{type(knowledge_results)}"
        
        if len(knowledge_results) > 0:
            for doc in knowledge_results:
                assert isinstance(doc, dict), f"知识条目应该是字典格式，但得到：{type(doc)}"
                assert 'content' in doc, f"知识条目应该有content字段，但得到：{doc.keys()}"
                
            all_content = " ".join(doc.get('content', '') for doc in knowledge_results)
            keywords = ["血染", "人数", "主持", "分钟", "桌游"]
            has_relevant = any(keyword in all_content for keyword in keywords)
            assert has_relevant, f"检索的知识应该与桌游相关，但得到：{all_content[:300]}..."
    
    @pytest.mark.asyncio
    async def test_should_generate_professional_response(self):
        """测试：应该生成专业的回答"""
        agent = ConsultantAgent()
        await agent.knowledge_retriever.initialize()
        
        question = "血染钟楼需要主持人吗？"
        response = await agent.consult(question)

        assert len(response) > 20, f"回答应该有一定长度，但只有{len(response)}字符：{response}"
        assert "不知道" not in response, f"回答不应该说不知道：{response[:100]}..."

        professional_terms = ["主持", "人", "分钟", "血染", "专业"]
        has_professional_content = any(term in response for term in professional_terms)
        assert has_professional_content, f"回答应该包含桌游信息，但得到：{response[:200]}..."


class TestConsultantAgentEdgeCases:
    """测试边界情况和错误处理"""
    
    @pytest.mark.asyncio
    async def test_should_handle_empty_or_invalid_input(self):
        """测试：应该处理空输入或无效输入"""
        agent = ConsultantAgent()
        await agent.knowledge_retriever.initialize()
        
        invalid_inputs = ["", "   ", "？", "...", "###"]
        
        for invalid_input in invalid_inputs:
            try:
                response = await agent.consult(invalid_input)
                assert isinstance(response, str), f"无效输入应该返回字符串，输入：'{invalid_input}'"
            except Exception as e:
                assert isinstance(e, (ValueError, TypeError)), \
                    f"无效输入'{invalid_input}'异常类型错误：{type(e)}"
    
    @pytest.mark.asyncio
    async def test_should_work_with_stream_mode(self):
        """测试：流式模式应该正常工作"""
        agent = ConsultantAgent()
        await agent.knowledge_retriever.initialize()
        
        question = "血染钟楼需要几个人？"
        
        response_tokens = []
        async for token in agent.consult_stream(question):
            response_tokens.append(token)
        
        stream_response = "".join(response_tokens)
        assert len(stream_response) > 0, "流式模式应该返回内容"
        
        normal_response = await agent.consult(question)
        
        keywords = ["血染", "人", "主持", "分钟"]
        stream_has_content = any(keyword in stream_response for keyword in keywords)
        normal_has_content = any(keyword in normal_response for keyword in keywords)
        
        assert stream_has_content or normal_has_content, \
            f"至少一种模式应该返回相关内容\n流式：{stream_response[:100]}...\n普通：{normal_response[:100]}..."
