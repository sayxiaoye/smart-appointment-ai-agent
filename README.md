# Smart Appointment AI Agent

Smart Appointment AI Agent 是一个面向桌游门店场景的智能预约与咨询系统。项目基于 FastAPI、LangChain、FAISS、SQLite 和多 Agent 协作架构，实现了登录隔离、事实查询、意图识别、RAG 知识问答、主持人档期匹配、预约管理、用户行为分析和回访提醒。

这个项目把门店前台的高频工作拆开处理：先确认是谁在说话，再判断这句话是在查档期、查游戏、预约，还是问店内知识。预约按游戏、主持类型、人数和时长匹配主持人；自助场次不占档。预约成功后可以带上天气说明，回访提醒则使用该用户自己的称呼、常玩游戏和常约主持人。

## 项目背景

桌游门店前台需要同时处理游戏咨询、人数校验、主持类型选择、主持人排班、顾客预约和偏好记录。游戏越多、主持人类型越细，人工前台越容易漏信息、排错人或排重档。

因此，本项目用 AI Agent 重构这一流程：让系统像智能前台一样理解用户需求，并把咨询、预约和行为分析分给对应 Agent。预约槽位是游戏、主持类型、人数和时长；自助场次不占用主持人。

## 核心能力

- **账号与隔离**：注册时保存用户名、密码哈希和称呼。聊天、预约和行为分析都绑定当前登录用户，每个用户有独立的对话状态。
- **事实查询**：在调用分类模型之前，直接回答点名主持人是否有空、当天空档、主持人介绍、游戏人数时长，以及“我的预约”。查完回到待分类，不写入咨询或预约行为。
- **智能任务分类**：其余输入再区分预约、知识咨询，或不支持的支付、统计和其他问题。已经进入预约或咨询后，后续句子继续走当前流程。
- **多 Agent 协作**：归类、咨询、预约和用户行为各自处理一类工作。
- **RAG 知识咨询**：规则、地址、收费等叙述性问题走 FAISS 检索，再由大模型生成回答，支持流式输出。
- **智能预约管理**：按游戏目录、主持类型、人数、主持人专长和 `host_schedules` 档期匹配。指定主持人没空时推荐相似主持人并等待确认；自助场次直接保存，不占档。
- **用户行为分析**：预约和咨询记在当前用户名下。回访问候使用注册称呼、常玩游戏、常约主持人，以及 12:00–22:00 内的空闲时间。
- **预约结果里的天气**：预约写入成功后，用 LangChain 工具查询北京天气并写进成功提示。配置了 `OPENWEATHER_API_KEY` 时请求 OpenWeatherMap，否则使用固定的适宜天气说明。
- **Embedding 缓存优化**：通过数据库缓存和文件缓存减少重复向量计算，提高知识检索性能。
- **数据管理能力**：支持知识库、主持人和用户行为数据的管理，并在数据变化后自动维护索引。
- **日志与兜底机制**：保留关键处理过程日志，在信息不足或异常情况下提供更稳定的降级处理。

## 系统架构

项目采用严格的五层架构，核心原则是：**下层不能反向调用上层**。这样可以避免循环依赖，让业务逻辑、数据访问和接口编排保持清晰边界。

```text
Web & Application Layer
    ↓  app.py, web/：页面、路由入口、系统启动
API Layer
    ↓  api/：外部接口、请求编排、响应封装
Agents Layer
    ↓  agents/：AI Agent、任务路由、对话流程控制
Services Layer
    ↓  services/：业务逻辑、推荐算法、向量处理
DB Layer
    ↓  db/：数据模型、数据库连接、Repository
```

### 调用方向

- Web 层调用 API 层
- API 层调用 Agents 层或 Services 层
- Agents 层调用 Services 层
- Services 层调用 DB 层

回访提醒在生成问候时会直接读取主持人档期，这是当前代码里的一处例外。

## Agent 设计

### Task Classification Agent

任务分类 Agent 是系统的主调度器，负责分析用户输入、判断任务类型，并把请求分发给合适的专业 Agent。

```text
已登录用户输入 → 待分类时先做事实查询 → 未命中再分类 → 预约 / 咨询 / 暂不支持
```

主要职责：

- 只在待分类状态下拦截事实问题，查完回到待分类
- 判断预约、咨询，以及暂不支持的支付、统计和其他问题
- 为每个登录用户维护独立对话状态
- 预约或咨询进行中时，把后续输入留在当前 Agent

### Consultation Agent

咨询 Agent 负责知识问答场景，使用 RAG 流程从知识库中检索相关内容，再结合大模型生成回答。

```text
咨询任务 → 检索 knowledge_documents → FAISS 相似度搜索 → 流式回答 → 写入当前用户的咨询行为
```

主要职责：

- 回答规则、玩法、地址、收费等知识库问题
- 从知识库检索相关内容并构建提示词
- 生成自然语言回答
- 回答结束后回到待分类

### Appointment Agent

预约 Agent 负责预约相关流程，包括解析用户输入、校验游戏和主持类型、匹配主持人、生成确认消息等。

```text
预约任务 → 解析槽位 → 校验游戏与主持类型 → 查询主持人档期 → 写入预约 → 天气说明
```

主要职责：

- 提取游戏、主持类型、人数、时间和主持人偏好
- 校验人数区间和该游戏允许的主持类型
- 在 `host_schedules` 中检查 12:00–22:00 的忙碌档期；没有忙碌记录视为有空
- 指定主持人没空时推荐相似主持人，确认前留在预约流程
- 自助场次写入预约，不占用主持人
- 信息不全时追问，并保留已经收集的槽位
- 预约写入成功后附上天气说明，然后回到待分类

### User Behavior Agent

用户行为 Agent 更偏向后台智能分析，不完全依赖用户显式请求。它会根据交互记录、预约历史和偏好数据分析用户行为，为后续推荐提供依据。

```text
当前用户的行为记录 → 偏好分析 → 空闲档期 → 使用注册称呼生成回访问候
```

主要职责：

- 把咨询和预约记到当前用户
- 分析常玩游戏、常约主持人和常用时长
- 在营业时间内查找该主持人的空闲时段
- 生成回访问候。页面和接口都只看当前登录用户

### Factual Reply

事实回复不是第六个分类标签。归类机器人在调用分类模型之前，用规则判断这句话能不能直接查库回答。

```text
待分类 → 事实问题 → 读取档期 / 主持人 / 游戏 / 我的预约 → 直接回复 → 回到待分类
```

可以直接回答的包括：

- 某位主持人在某个时刻是否有空，以及当天还有哪些忙碌时段
- 某位主持人在 12:00–22:00 的空档，或这个时刻谁有空
- 主持人的性别、专长和主持类型
- 游戏目录里的人数、建议时长和是否需要主持
- 当前用户自己的预约进度

相对时间会单独做一次解析。有空或没空由档期数据决定，不交给知识库猜测。规则、收费、地址仍走咨询 Agent。带有“我要预约”“帮我预约”的句子仍走预约 Agent。缺了主持人、游戏或时间时，只追问一次，然后回到待分类。

## 核心设计思想

### 1. 用任务分类降低系统复杂度

系统并不让一个 Agent 处理所有事情。能查表的问题先直接回答，其余再分给咨询或预约。行为分析不占用聊天里的分类，只使用已经记下的当前用户数据。

### 2. 能查表的问题不走知识库

档期、主持人资料、游戏目录字段和本人的预约进度都有确定数据。这些句子在分类之前直接查库。规则、地址、收费等叙述性内容才进入 RAG，避免模型编造人数、时长或档期。

### 3. 用用户行为让推荐更个性化

系统会把咨询、预约和偏好记在当前用户名下。回访问候会用到常玩游戏和常约主持人，而不是每次都从零开始介绍。

### 4. 用分层架构保证可维护性

Agent 负责智能流程，Service 负责业务逻辑，Repository 负责数据访问。每层只关心自己的职责，减少后期修改时的连锁影响。

### 5. 为真实业务场景预留扩展空间

项目目前以本地 SQLite 和单体服务为主，但架构上预留了模型提供商切换、MCP 外部服务接入、后台任务、缓存优化和云端部署的扩展方向。

## 架构图

![System Architecture](./architecture%20.jpg)

## 技术栈

- **后端框架**：FastAPI、Uvicorn
- **AI 框架**：LangChain
- **大模型接入**：兼容 OpenAI 格式的模型提供商，例如 Qwen、DeepSeek、Zhipu、OpenAI、Azure OpenAI
- **向量检索**：FAISS
- **数据库**：SQLite、SQLAlchemy
- **RAG 能力**：Embedding、向量索引、知识库检索、提示词构建
- **流式响应**：Python AsyncGenerator
- **前端页面**：Jinja2 模板、静态 CSS
- **登录会话**：Starlette SessionMiddleware 签名 cookie
- **天气**：LangChain 工具调用 OpenWeatherMap
- **配置管理**：python-dotenv
- **后台任务**：schedule。启动时会挂上推荐调度，具体推荐生成仍待补全

## 项目结构

```text
Smart appointment AI agent/
├── agents/                         # 多 Agent 智能层
│   ├── task_classification_agent.py # 任务分类与主路由
│   ├── consultant_agent.py          # RAG 咨询 Agent
│   ├── appointment_agent.py         # 智能预约 Agent
│   ├── user_behavior_agent.py       # 用户行为分析 Agent
│   ├── factual/                     # 分类前的档期、主持人和游戏查询
│   ├── task_classification/         # 意图识别、状态管理、路由逻辑
│   ├── consultant/                  # 知识检索、提示词、回答生成
│   ├── appointment/                 # 预约解析、主持人匹配、消息构建
│   └── user_behavior/               # 行为记录、偏好管理、模式分析
├── api/                             # API 编排层
│   ├── auth.py                      # 注册、登录、退出、当前用户
│   ├── appointment.py               # 预约接口
│   ├── consultation.py              # 咨询接口
│   ├── task.py                      # 任务分类接口
│   ├── chat_handler.py              # 按用户隔离的流式聊天
│   ├── host.py                      # 主持人管理接口
│   ├── knowledge.py                 # 知识库管理接口
│   └── user_behavior_analysis.py    # 当前用户的行为分析接口
├── services/                        # 业务逻辑层
│   ├── appointment_service.py       # 预约业务逻辑
│   ├── knowledge_service.py         # 知识库管理
│   ├── recommendation_service.py    # 推荐逻辑
│   ├── host_service.py              # 主持人信息管理
│   ├── game_catalog_service.py      # 游戏目录与校验
│   ├── text_embedding.py            # Embedding 与向量处理
│   └── user_behavior_service.py     # 用户行为服务
├── db/                              # 数据持久化层
│   ├── models.py                    # SQLAlchemy 模型
│   ├── db_router.py                 # 数据库路由
│   ├── local_db.py                  # 本地数据库操作
│   ├── base/                        # 数据库基础接口
│   └── repositories/                # Repository 数据访问封装
├── config/                          # 配置模块
│   ├── constants.py                 # 常量与枚举
│   ├── database.py                  # 数据库配置
│   ├── model_provider.py            # 模型与 Embedding Provider 工厂
│   ├── session_secret.py            # 登录 cookie 密钥校验
│   ├── settings.py                  # 应用配置
│   └── time_config.py               # 北京时间
├── web/                             # Web 页面层
│   ├── routes.py                    # 页面路由
│   ├── templates/                   # HTML 模板
│   └── static/                      # 静态资源
├── mcp-server/                      # MCP 外部服务扩展，当前为空目录
├── data/                            # 数据库与缓存目录
├── tests/                           # 测试用例
├── app.py                           # 应用入口
├── requirements.txt                 # Python 依赖
├── .env.example                     # 环境变量模板
└── README.md                        # 项目说明
```

## 快速开始

### 1. 创建虚拟环境

```bash
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
```

Windows CMD：

```cmd
.venv\Scripts\activate.bat
```

macOS 或 Linux：

```bash
source .venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

复制环境变量模板：

```bash
cp .env.example .env
```

Windows PowerShell 可以使用：

```powershell
Copy-Item .env.example .env
```

然后在 `.env` 中填写模型配置。项目支持 OpenAI 兼容格式的大模型与 Embedding 服务。`SESSION_SECRET` 必须换成一段足够长的随机字符串；缺失或仍是示例占位符时，应用拒绝启动。

```env
MODEL_PROVIDER=qwen
LLM_API_KEY=your_llm_api_key_here
LLM_BASE_URL=your_openai_compatible_chat_base_url_here
LLM_MODEL=your_chat_model_name_here

EMBEDDING_PROVIDER=qwen
EMBEDDING_API_KEY=your_embedding_api_key_here
EMBEDDING_BASE_URL=your_openai_compatible_embedding_base_url_here
EMBEDDING_MODEL=your_embedding_model_name_here

OPENWEATHER_API_KEY=

SESSION_SECRET=replace_with_a_long_random_string
```

数据库默认使用 `sqlite:///data/smart_appointment.db`。需要换路径时设置 `DATABASE_URL`。

常见配置方向：

- Qwen：使用阿里云百炼或 DashScope 的模型、Base URL 和 API Key。
- DeepSeek：可用于聊天模型，Embedding 可搭配其他兼容服务。
- Zhipu：可配置智谱的聊天模型和向量模型。
- Azure OpenAI：将 `MODEL_PROVIDER` 设置为 `azure`，并补充对应的 Azure OpenAI 环境变量。

### 4. 启动服务

```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8001 --reload
```

直接运行 `python app.py` 也会监听 `127.0.0.1:8001`。端口被占用时，把命令里的端口改成其他值。

启动后可以访问：

- Web 页面：http://127.0.0.1:8001
- 登录：http://127.0.0.1:8001/login
- 注册：http://127.0.0.1:8001/register
- API 文档：http://127.0.0.1:8001/docs
- ReDoc 文档：http://127.0.0.1:8001/redoc

## 测试

运行全部测试：

```bash
pytest
```

运行单个测试文件：

```bash
pytest tests/test_factual_replies.py
```

## 主要页面

- 首页聊天与预约入口：`/`。发送消息前需要登录。
- 登录与注册：`/login`、`/register`
- 知识库管理：`/knowledge`，无需登录
- 主持人状态：`/host`，无需登录
- 主持人排班：`/host_schedule`，无需登录
- 用户行为分析：`/user_behavior`。页面可打开，读取分析和发送提醒时需要登录，并且只返回当前用户的数据。

## 后续规划

### 更强的 Agent 自主能力

- 增加 Agent 自我反思机制，让系统能够评估回答质量和预约成功率。
- 引入更完整的多轮推理链，提升复杂预约和冲突处理能力。
- 根据真实用户反馈优化推荐策略。

### 更完整的多 Agent 协作

- 增加 Agent 之间的直接通信，减少所有任务都经过归类机器人转发。
- 补上定时推荐任务里的实际生成逻辑，并让回访可以主动送到用户。
- 把预约、推荐、咨询之间的上下文记忆保存下来。当前每个用户的对话状态只放在进程内存中，重启后槽位会清空。

### 生产化能力

- 为知识库和主持人管理补上权限控制。聊天、预约和行为数据已经按登录用户隔离。
- 实现分类结果里的支付和统计，目前这两类会回复暂不支持。
- 增加更完整的异常处理和边界场景覆盖。
- 优化向量检索性能、缓存策略和响应速度。
- 支持 Docker 部署、云数据库和更标准的日志监控。

## 项目价值

这个项目把多 Agent、RAG、用户行为分析、预约调度和外部工具接入放在桌游门店场景中验证，也可以作为学习 AI Agent 工程化、分层架构、RAG 系统和业务自动化的综合实践项目。



