# 劳法智枢 Legal AI Agent

面向中国劳动争议场景的多智能体法律辅助系统。项目将法条/案例 RAG、劳动赔偿计算、案件预判、风险评估、仲裁文书生成和会话级上下文协同整合到一个 FastAPI + Web 单页应用中，适合用于演示劳动法 AI Agent 的端到端产品能力。

> 说明：系统输出仅用于法律信息检索、计算辅助和材料草拟，不构成正式法律意见。

## 核心能力

- 多 Agent 协同：`RouterAgent` 根据用户意图分发到问答、文书、风险、预判等子 Agent。
- 会话级上下文：同一 `session_id` 保存案件事实、上次赔偿计算、路由轨迹和对话摘要，支持多轮追问。
- 赔偿计算引擎：支持 N、N+1、2N、未签劳动合同双倍工资、加班费、年休假、竞业限制、社保补缴、工伤待遇等场景。
- RAG 检索增强：基于劳动法条和案例数据构建 Chroma 向量库，并结合关键词重排处理法条编号查询。
- 路由仲裁层：UI 模式作为偏好而非硬强制，明确计算或文书需求可自动覆盖当前模式。
- 结构化输出：后端返回计算结果、风险等级、证据完整度、时间线、下一步行动和会话可观测字段。
- 回归测试：覆盖单轮计算、混合多轮会话、上下文隔离、文书/预判复用计算结果等关键路径。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 后端 | FastAPI, Uvicorn |
| Agent / LLM | LangChain, LangGraph, Qwen DashScope compatible API |
| RAG | ChromaDB, LangChain Chroma, DashScope Embedding |
| 前端 | HTML, CSS, JavaScript, SSE streaming |
| 测试 | Python `unittest` |
| 持久化 | Local JSON conversation state, local Chroma vector store |

## 项目结构

```text
legal_ai_agent/
├── app.py                         # ASGI app 兼容入口
├── start_server.py                # 本地启动入口
├── build_db.py                    # 知识库构建入口
├── requirements.txt               # Python 依赖
├── .env.example                   # 环境变量模板
├── frontend/
│   └── index.html                 # Web 单页应用
├── legal_ai_agent/
│   ├── api/
│   │   └── server.py              # FastAPI 主链路、路由仲裁、结构化输出
│   ├── agents/
│   │   ├── router_agent.py        # 意图路由
│   │   ├── qa_agent.py            # 法律问答
│   │   ├── doc_agent.py           # 文书生成
│   │   ├── risk_agent.py          # 风险评估
│   │   └── judge_agent.py         # 案件预判
│   ├── memory/
│   │   ├── memory_manager.py      # 会话状态 JSON 持久化
│   │   └── case_profile.py        # 轻量案件事实状态
│   ├── rag/
│   │   ├── build_db.py            # 向量库构建
│   │   ├── vector_store.py        # 混合检索与法条重排
│   │   └── retriever.py
│   ├── tools/
│   │   ├── calculator.py          # 劳动争议赔偿计算引擎
│   │   ├── labor_tools.py         # LangChain 工具封装
│   │   └── legal_reasoning.py     # 案件结构化分析
│   ├── llm/
│   │   └── qwen_llm.py            # DashScope LLM/Embedding 封装
│   └── config/
│       └── settings.py            # 路径与模型配置
├── data/
│   ├── law/                       # 法条文本数据
│   ├── case/                      # 案例文本数据
│   └── raw/                       # 原始 docx 数据源
├── docs/
│   ├── ARCHITECTURE.md            # 架构说明
│   ├── API.md                     # API 契约
│   ├── GITHUB_CHECKLIST.md        # 上传前检查清单
│   ├── project/                   # 项目技术文档
│   └── evaluation/                # 测试报告与评估材料
├── tests/
│   ├── test_smoke.py
│   ├── test_calculation_docx_cases.py
│   ├── test_conversation_state.py
│   └── test_multiturn_workflow.py
└── db/
    └── .gitkeep                   # 本地 conversation_state.json 不入库
```

## 快速开始

### 1. 创建环境

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. 配置密钥

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，填入：

```text
DASHSCOPE_API_KEY=your_dashscope_api_key
```

也可以直接在当前 PowerShell 会话中设置：

```powershell
$env:DASHSCOPE_API_KEY="your_dashscope_api_key"
```

### 3. 构建知识库

```powershell
.\venv\Scripts\python.exe build_db.py --init
```

如需强制重建：

```powershell
.\venv\Scripts\python.exe build_db.py --force
```

### 4. 启动服务

```powershell
.\venv\Scripts\python.exe start_server.py
```

访问：<http://localhost:8000>

## 测试

```powershell
.\venv\Scripts\python.exe -m unittest discover
```

重点测试覆盖：

- 赔偿计算公式与边界场景。
- 同一会话内计算、法条问答、案件追问、预判、文书、风险混合调用。
- 普通法条问答不被前文赔偿计算污染。
- 新 `session_id` 不继承旧会话事实。
- UI 偏好模式不会阻断明确的计算/文书意图。
- `force_mode=true` 时才严格锁定指定 Agent。

## API 简览

主要接口：

- `POST /api/chat`
- `POST /api/chat/stream`

请求体兼容：

```json
{
  "query": "月薪10000，工作3年，被公司突然辞退且无补偿，能拿多少？",
  "session_id": "demo-session",
  "preferred_mode": "qa",
  "force_mode": false
}
```

响应会返回 `route`、`answer/reply` 和 `structured`，其中 `structured.conversation` 可观察本轮路由原因、已知案件事实和是否复用了上次计算结果。

详见 [docs/API.md](docs/API.md)。

## 设计亮点

### 会话级协同

`ConversationStateStore` 以 `session_id` 为边界保存案件事实、计算结果和路由轨迹。用户先问“赔偿多少”，再问“胜诉率怎么样”或“帮我写仲裁申请书”，后端会把上一轮金额、工资、年限、解除性质注入给预判/文书 Agent。

### 上下文污染控制

系统区分普通法条问答和案件连续追问。比如在计算后继续问“劳动法第68条是什么”，只走普通问答，不注入前文案件状态，也不让结构化面板抽取旧计算片段。

### 可解释路由

后端将 UI 选择视为 `preferred_mode`，再由 `_resolve_effective_route` 进行仲裁。明确文书、明确计算、风险、预判等意图优先，响应中通过 `route_reason` 解释调度原因。

## 上传 GitHub 前

请先阅读 [docs/GITHUB_CHECKLIST.md](docs/GITHUB_CHECKLIST.md)。核心原则：

- 不提交 `.env`、`db/conversation_state.json`、`chroma_db/`、`venv/`、`.idea/`。
- 保留 `data/`、`docs/`、`tests/`、`frontend/` 和 `legal_ai_agent/`。
- 提交前运行完整测试。

