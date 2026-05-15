# 数字员工平台 · MVP

---

## 一、它是什么

一个**多角色数字员工平台**，涵盖 QA、研发、产品、运维和项目管理——每位员工专注于特定领域，遵守行为约束，使用工具，并支持量化评估。

**特点**
- 对模糊需求主动澄清，而非自行假设
- 明确拒绝未授权请求，不寻求变通手段
- L2 工具在执行前需 Mentor 审批（Human-in-the-loop）
- 每次工具调用和 L2 决策都自动写入审计记录
- 通过考题库进行可量化的评估，支持 Mentor 迭代训练

**已集成的工具能力**
- 🔍 **本地知识库**：对本地 `.txt`/`.md`/`.pdf` 文件进行语义搜索（RAG，支持增量更新）
- 📖 **Confluence**：实时搜索 + 懒加载本地缓存，质量不足时自动补充查询
- 🎫 **Jira**：JQL 搜索 + Issue 详情，设计测试用例前主动排查历史 Bug
- 🔀 **GitLab MR**：读取 PR diff，按模块分析变更，推荐回归测试范围
- 🧠 **跨会话记忆**：自动保存项目上下文、近期工作、QA 笔记，重启后可继续

---

## 二、快速开始

### 1. 安装依赖

```bash
cd app
pip install -r requirements.txt
```

### 2. 配置 API 密钥

```bash
cp .env.example .env
```

编辑 `.env` 并按需填写。**只需修改 `LLM_PROVIDER` 即可切换模型，无需改代码。**

```bash
# 使用 Claude（默认）
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx
EMBEDDING_API_KEY=sk-xxxxxxxxxxxxxxxx   # 知识库向量检索专用（OpenAI text-embedding-3-small）

# 使用 GPT-4
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx      # LLM 推理专用
# EMBEDDING_API_KEY=                    # 可省略，自动回退到 OPENAI_API_KEY
# MODEL_NAME=gpt-4o                     # 可选，默认已设置
# OPENAI_BASE_URL=https://...           # 可选：Azure OpenAI 端点或其他代理
```

> **注意**：知识库向量检索始终使用 OpenAI `text-embedding-3-small`，与 `LLM_PROVIDER` 无关。`EMBEDDING_API_KEY` 是其专用配置项——使用 Claude 时需单独设置；使用 GPT-4 时若不设置，则自动回退到 `OPENAI_API_KEY`，无需重复填写。

### 3. 初始化知识库

```bash
python knowledge/setup_kb.py          # 增量更新（默认）
python knowledge/setup_kb.py --full   # 强制全量重建
```

对 `knowledge/` 目录下的 `.txt`、`.md` 和 `.pdf` 文件进行分块，写入本地 ChromaDB 向量库（`knowledge/.chroma/`）。

**增量模式（默认）**：通过 MD5 哈希比对检测文件变更。
- 文件未变更 → 跳过，**不消耗 OpenAI API**
- 文件已修改 → 删除旧分块，重新 Embedding
- 新文件 → 直接 Embedding 并写入
- 已删除文件 → 从向量库中移除对应分块

**`--full` 模式**：清空整个向量库并完全重建。适用于更换 Embedding 模型或需要完全重置时使用。

> ⚠️ `setup_kb.py` **只管理本地文件**。通过 `save_confluence_page` 缓存的 Confluence 页面不受影响，每次运行时会单独列出（标注 `~`）以确认其存在。

### 4. 启动

```bash
# 第一步：安装依赖（已包含在 requirements.txt 中）
pip install -r requirements.txt

# 第二步：构建 React 前端（执行一次，或前端有变更时执行）
cd web/frontend
npm install
npm run build   # 输出到 web/frontend/dist/，由 FastAPI 直接托管
cd ..

# 第三步：启动 Web Server
python web/server.py
# 访问 http://localhost:8000
# API 文档在 http://localhost:8000/docs
```

**前端开发模式**（热重载，用于本地开发）：

```bash
# 终端 1：启动后端
python web/server.py

# 终端 2：启动前端开发服务器
cd web/frontend
npm run dev   # → http://localhost:5173，代理到 :8000
```

---

## 三、数字员工管理平台

**Web 平台**解决了多人协作和团队管理问题，支持 QA、研发、产品、运维和项目管理等多角色数字员工的统一管理。

### 核心功能

**多角色 Agent 管理**
- 支持五种角色的数字员工：QA、Dev、PM、SRE、PJ，每个 Agent 有独立的 Prompt、Jira 项目和 Confluence Space 配置
- 每种角色内置快速创建预设（如电商促销 QA、后端研发、产品经理等）
- 多角色同时存在时，侧边栏按角色分组展示，每种角色有专属颜色徽章

**角色 Prompt 模板管理**
- 系统级 CRUD 支持每个角色（QA / Dev / PM / SRE / PJ）的 base prompt 模板，可在侧边栏 **Role Prompts** 页面编辑
- 新员工入职时自动从对应角色模板初始化 base prompt（优先级：DB 自定义模板 → 内置默认 → QA 兜底）
- 支持保存 / 重置为默认，并有未保存状态提示；模板变更仅影响新入职员工

**Prompt 管理器（每 Agent 版本化 Prompt）**
- 每个 Agent 有两个独立版本化的 Prompt 层，可通过聊天头部的 **Prompt** 按钮访问：
  - **基础 Prompt**：核心身份、权限边界、行为规则和工具使用策略
  - **专项化**：该产品线的领域专属业务规则、已知风险点和约定
- 每次保存都会创建一个新的不可变版本；旧版本可随时激活（回滚）
- 版本历史侧边栏展示创建时间、变更说明，以及基础 Prompt 版本对应的测评通过率
- 测评运行时记录当时激活的 Prompt 版本，支持前后对比
- 首次打开时，基础 Prompt 从共享默认模板初始化；专项化从创建 Agent 时输入的值初始化

**实时聊天**
- **Token 级流式输出**：最终回复逐字符显示（Anthropic `messages.stream` / OpenAI `stream=True`）；工具调用阶段仍按节点流式输出；协议：`message_start → token* → done`
- **上下文窗口管理**：每次 LangGraph 运行前从数据库加载对话历史；若消息数量 ≥ `CONTEXT_COMPRESS_THRESHOLD`（默认 40），用单次 LLM 调用对最旧的消息进行摘要，并替换为一条 `[早期对话摘要]` 消息——完整历史保留在数据库中
- 思考过程、工具调用和工具结果实时流式显示；`asyncio.to_thread` + `asyncio.Queue` 将同步 LangGraph 桥接到异步事件循环
- L2 工具（如缓存 Confluence 页面）在聊天中显示内联审批卡片；点击批准或拒绝
- 每个 Agent 保持独立的对话历史；对话支持内联重命名（悬停时显示铅笔图标，按 Enter 确认）

**行为审计日志** *（完整详情见[专属章节](#十六行为审计日志)）*
- 每次工具调用自动写入 SQLite `audit_logs` 表：执行时长、成功/失败、完整输入参数、300 字符结果预览
- 每次 LLM 调用记录为 `event_type=llm_call`，含 `input_tokens`、`output_tokens` 和挂钟时长
- L2 审批决策（批准/拒绝）写入同一张表，形成完整操作轨迹
- 侧边栏**审计日志**看板：统计卡片（工具调用次数、成功率、平均时长、L2 决策次数、**输入 Token、输出 Token、预估费用**）；每日趋势图；Top 工具排行；分页事件表格，LLM 调用行有**费用列**，点击行展开显示每次调用的 Token 明细

**群聊（多 Agent 协作）**
- 创建含 2 个以上 QA Agent 的群聊，协作处理跨业务线的复杂工单（如结算 QA + 促销 QA 共同处理跨域 Jira 工单）
- Agent 在 **Supervisor LLM** 协调下依次响应，路由到最相关的领域专家；当 Supervisor 判断问题已解决或所有 Agent 均已发言时自动终止讨论
- 实时流式：每个 Agent 的思考指示器和回复通过 WebSocket 实时流式输出到浏览器；对该领域无补充内容的 Agent 只显示一个低调的"无需补充"指示器而非完整回复
- 从侧边栏删除群聊；对话历史跨会话持久化

**测评平台** *（完整详情见[专属章节](#七测评平台)）*
- 按角色分组浏览所有考题（带彩色分组标题）；一键对任意 Agent 运行单题或全套考题
- **选题面板**支持关键词搜索 + 角色筛选（QA / Dev / PM / SRE / PJ）
- 运行异步执行（后台线程）；浏览器轮询等待完成——无阻塞
- 自动评分（关键词命中）立即显示；有评判标准的考题在历史表格中内联显示 Mentor 评分表单
- 分数趋势图追踪历史通过/失败情况；Agent 对比标签页支持选择多个 Agent，查看分组柱状图 + 最新分数对比表格

**知识库管理（Main + Branch 架构）**
- **Main KB**：所有 Agent 共享的知识库（团队级标准、QA 规范）
- **Branch KB**：每个 Agent 私有的知识库（业务线文档、历史 Bug）
- 通过 Web UI 上传文档，实时查看每个来源的分块数量
- 从 Branch 中选取有价值的来源，一键 Promote 到 Main KB
```
文档上传
  ↓
用户选择：写入 Main KB 还是 Branch KB
  ↓
Agent 推理时同时搜索两个集合，按相关性合并结果
  ↓
Mentor 发现 Branch 内容对团队有价值 → 选择来源 → Promote 到 Main
```

**权限配置**
- 工具风险级别（L1/L2/L3）和各职级的权限上限可在侧边栏 **权限管理** 页面直接调整——无需修改代码或重启服务
- 首次启动时从 `config.py` 自动种入默认值；后续新增到 `TOOL_RISK_LEVEL` 的工具在下次打开页面时自动检测并补录

**对话 → 知识库（知识蒸馏）**
- 删除对话时，弹窗询问：*保存到知识库后删除 / 直接删除 / 取消*
- "保存到知识库"：用单次 LLM 调用将完整对话记录蒸馏为结构化知识库文章（标题 + 正文），分块、Embedding 并写入 Agent 的 Branch KB（`qa_knowledge_{agent_id}`）
- 保存的文章在后续对话中可立即通过 `search_knowledge_base` 搜索到——有价值的 QA 讨论永不丢失
- 端点：`POST /conversations/{id}/save-to-kb`

### 架构图

```
浏览器
  │  HTTP REST + WebSocket
  ▼
FastAPI (web/server.py :8000)
  │
  ├─ /api/agents/*                     → Agent CRUD (SQLite)
  ├─ /api/conversations/*              → 对话管理
  ├─ /api/conversations/{id}/ws        → WebSocket 实时推理（Token 级流式输出）
  ├─ /api/conversations/{id}/save-to-kb → 蒸馏对话记录 → Branch KB
  ├─ /api/audit/*                      → 审计日志查询、统计、追踪瀑布图
  ├─ /api/exams/*                      → 考题 CRUD + 异步运行管理 + LLM-as-Judge
  ├─ /api/role-prompts/*               → 系统级角色 Prompt 模板 CRUD
  ├─ /api/permissions/*                → 工具风险级别 + 职级权限上限配置
  ├─ /api/group-chats/*                → 群聊 CRUD + WebSocket 多 Agent 编排
  ├─ /api/agents/{id}/knowledge/*      → 知识库管理
  ├─ /api/test-suites/*                → 测试套件 + 用例 CRUD、Markdown/XMind 导出
  ├─ /api/test-runs/*                  → E2E 运行生命周期、终止、分析、截图
  ├─ /api/test-plans/*                 → 测试计划 CRUD + 并行执行
  └─ /api/browser-skills/*             → 环境型 + 额外型技能管理
         │
         ▼
   LangGraph Agent（每个 agent_id 有独立编译的 graph）
         │
    ┌────┴────┐
    │         │
  Main KB   Branch KB
  （共享）  （每 Agent）
  ChromaDB  ChromaDB
```

---

## 四、Agent 执行流程

```
用户输入
    ↓
[qa_agent] Claude 推理
    ↓ 有工具调用？
    ├─ 无 → 输出结论，结束
    │
    ├─ L1 工具（read_doc / search_kb）
    │    → [tools] 自动执行 → 返回结果 → 继续推理
    │
    └─ L2 工具（create_defect）
         → [human_review] 暂停，显示待审批
         → Mentor 输入 y/n
             ├─ y → 执行工具 → 继续推理
             └─ n → 取消，继续推理
```

### System Prompt 构建

System Prompt **不存储在任何地方**——在每次 LLM 调用时动态组装，调用后丢弃。持久化到数据库的只有原材料（Prompt 版本内容、Agent 元数据），不是组装后的字符串。

```
数据库（两张表）
  ┌─ prompt_versions（每 Agent 版本化，主要来源）
  │    ├─ type="base",           is_active=True  → base_prompt 内容
  │    └─ type="specialization", is_active=True  → specialization 内容
  │
  └─ qa_agents（元数据 + 兜底）
       ├─ ranking        = "Senior"   ← 格式化 {ranking_description} 占位符
       └─ specialization = "..."      ← 无激活版本时的 specialization 兜底

        │  WebSocket 连接时读取激活版本，构建 LangGraph config
        ▼

  lg_config = {
    "configurable": {
      "agent_id":       "<uuid>",
      "ranking":        "Senior",
      "base_prompt":    "<激活的 base 版本内容>",       ← prompt_versions 读取
      "specialization": "<激活的 spec 版本内容>",       ← prompt_versions 读取，兜底到 agent.specialization
    }
  }

        │  每次 LLM 调用时，在 qa_agent_node 内动态组装
        ▼

  # 1. 语义记忆检索（以最新用户消息为查询）
  memory_context = load_memory_context(agent_id, query=<最新用户消息>)

  # 2. 组装 System Prompt
  build_system_prompt(
    base_prompt    = "<激活版本>"   → 若空则回退到角色默认模板（ROLE_PROMPTS[agent.role]）
                                      再用 {agent_id} / {agent_version} / {ranking_description} 格式化
    specialization = "..."         → 追加为 【Domain Specialization】 区块（非空时）
    memory_context = "..."         → 追加跨会话记忆片段（非空时）
  )

        │
        ▼

  最终 System Prompt 结构：
  ┌──────────────────────────────────────────┐
  │  base prompt（格式化后）                  │  ← 身份 / 权限边界 / 行为规范 / 工具策略
  ├──────────────────────────────────────────┤
  │  ═══...═══                               │
  │  【Domain Specialization】（可选）        │  ← 业务线专属规则、已知风险、约定
  │  ═══...═══                               │
  │  {specialization 内容}                   │
  ├──────────────────────────────────────────┤
  │  {memory_context}（可选）                │  ← 语义检索出的跨会话记忆片段
  └──────────────────────────────────────────┘

  call_llm(system_prompt=<上述字符串>, ...)
  # 每次调用临时组装，用完即丢
```

**base_prompt 回退链（`agent/prompts.py`）：**

```
prompt_versions.type='base', is_active=True
  │ 若为空
  ▼
role_prompt_templates[agent.role]（DB 中可自定义的系统级模板）
  │ 若为空
  ▼
ROLE_PROMPTS[agent.role]（代码内置默认，按角色区分：QA / Dev / PM / SRE / PJ）
```

Ranking → 身份描述映射（`agent/prompts.py`）：

| Ranking | Prompt 中的身份 |
|---------|----------------|
| Intern  | 新入职的实习级 |
| Junior  | 初级 |
| Senior  | 高级 |
| Lead    | 领导级 |

**关键优势：** 在 Prompt 管理器中激活新版本，下一条消息立即生效——无需重启，无需数据迁移。`base_prompt` 和 `specialization` 独立版本化，可分别回滚。

**权限级别**（默认值在 `config.py` 的 `TOOL_RISK_LEVEL` 中定义；可在侧边栏 **权限管理** 页面实时调整）：

| 级别 | 含义 | 当前工具 |
|-------|---------|---------------|
| L1 | 自动执行，无需审批 | `read_requirement_doc`、`search_knowledge_base`、`search_confluence`、`search_jira`、`get_jira_issue`、`get_gitlab_mr_diff`、`write_output_file`、`save_to_memory` |
| L2 | 需要 Mentor 确认 | `create_defect_mock`、`save_confluence_page` |
| L3 | 仅输出计划，不执行（计划中） | 未来：触发 CI、变更配置 |

---

## 五、知识检索与记忆系统

跨会话记忆系统使用 ChromaDB 向量搜索，为每次对话只检索最相关的记忆片段，而非将完整的记忆 JSON 注入每个 Prompt。

### 工作流程

```
Agent 收到用户消息
  ↓
qa_agent_node 提取最后一条用户消息作为查询
  ↓
调用 load_memory_context(agent_id, query=<消息内容>)
  ↓
语义搜索：对所有已保存记忆条目进行 ChromaDB 余弦相似度检索
  ├─ 命中 → 返回 Top-5 片段（附相关度分数）
  ├─ 索引为空 → 从 JSON 重建索引，重试搜索
  └─ 任意异常 → 回退到完整 JSON 上下文（优雅降级）
  ↓
相关记忆片段注入到系统 Prompt
```

保存记忆时自动建立索引：`save_to_memory` 调用 `save_to_index`（尽力而为，不抛出异常）。索引存储在名为 `agent_memory_{agent_id}` 的 ChromaDB Collection 中，使用 OpenAI `text-embedding-3-small` 嵌入。

### 三层容错机制

1. **语义命中**：按余弦相似度返回 Top-5 片段
2. **索引为空**：从完整 JSON 记忆文件重建索引后重试——覆盖首次使用和已有 Agent 的场景
3. **任意异常**（ChromaDB 不可用、无 API Key 等）：原样返回完整 JSON 上下文——对现有部署零回归

### 相关文件

- `tools/semantic_memory.py` — `save_to_index`、`delete_from_index`、`search`、`rebuild_index`
- `tools/memory_manager.py` — 带 `query` 参数的 `load_memory_context`；带语义镜像的 `save_to_memory`
- `agent/agent.py` — 在调用 `load_memory_context` 前提取最后一条 `HumanMessage` 内容作为查询

### 持久化存储与记忆分类

```
每次启动
  ↓
读取 memory/agent_memory.json → 注入 System Prompt
  ↓
对话中 Agent 调用 save_to_memory 保存有价值的信息
  ↓
下次启动自动加载文件，从上次中断处继续
```

**欢迎面板**在启动时显示记忆状态：
- `🧠 已从历史会话加载记忆` — 找到历史记忆
- `🆕 无历史记忆（首次会话）` — 首次运行

### 记忆分类

| 分类 | 存储内容 | 保留策略 |
|----------|----------------|-----------|
| `user_preferences` | 默认项目、团队、输出风格 | 无限期 |
| `active_context` | 当前 Sprint、关注的功能模块 | 无限期 |
| `qa_notes` | 风险模式、团队约定、已知不稳定点 | 无限期 |
| `recent_work` | 已分析的工单、生成的测试用例、已审查的 MR | 滚动：最近 20 条 |
| `session_summary` | 每次会话的简要摘要 | 滚动：最近 5 条 |

### Agent 记忆行为

Agent 在以下时刻**主动**调用 `save_to_memory`——无需提示：
- 你提到默认项目或团队 → 保存到 `user_preferences`
- 完成一个 Jira 工单或 MR 的分析 → 关键发现保存到 `recent_work`
- 发现风险模式或团队约定 → 保存到 `qa_notes`
- 对话结束 → 简要摘要保存到 `session_summary`

### 记忆文件

记忆存储在 `memory/agent_memory.json`（已 gitignore——不提交到仓库）。可直接查看或编辑：

```json
{
  "user_preferences": {
    "default_jira_project": {"value": "SPPT", "updated": "2026-04-21"}
  },
  "active_context": {
    "current_sprint": {"value": "Sprint 42，聚焦：代金券核销", "updated": "2026-04-21"}
  },
  "qa_notes": {
    "voucher_risk_areas": {"value": "DB 迁移 + 幂等性历史高风险", "updated": "2026-04-21"}
  },
  "recent_work": [
    {"date": "2026-04-21", "label": "SPPT-97814 分析", "content": "代金券 MR，标记 DB 迁移风险"}
  ],
  "session_summaries": [
    {"date": "2026-04-21", "content": "分析了 SPPT-97814 MR，建议在 DB + API 层回归"}
  ]
}
```

### 知识库集成

以Confluence为例。本框架实现了**实时搜索 + 懒加载本地缓存**的混合 RAG 架构，使 Agent 在推理时能引用最新的内部文档。

### 架构

```
用户问题
   │
   ▼
Agent 判断需要检索信息
   │
   ├─► search_knowledge_base（本地 ChromaDB）
   │        │
   │        └─► Agent 评估结果质量——不是"有没有"，而是"够不够好"
   │                  ✅ 相关性高且内容完整 → 直接使用，跳过 Confluence
   │                  ⚠️ 满足任一条件时继续查询 Confluence：
   │                       - Top 相关性分数 < 75%
   │                       - 内容只覆盖了问题的一部分
   │                       - 内容看起来过时（提到旧版本/已废弃规则）
   │                       - 本地无结果
   │
   ├─► search_confluence（Confluence REST API，实时）
   │        返回：标题 / 摘要 / 链接 / page_id
   │        结合本地 + Confluence 内容作答
   │        │
   │        └─► Agent 判断：这个页面对未来任务有持续价值吗？
   │                  有 → 建议 Mentor 执行 save_confluence_page
   │                  无 → 在线使用摘要，不持久化
   │
   └─► save_confluence_page（L2，需 Mentor 确认）
            获取完整内容 → 去除 HTML → 分块 → Embedding → 写入本地 ChromaDB
            下次遇到类似问题直接走本地——无需再调 Confluence
```

> **设计原则**：检索的触发条件是**质量**，而非**是否存在**。即便本地有结果，相关性不足也会触发 Confluence 补充查询，而非接受低质量内容。`search_knowledge_base` 的结果带有质量提示（`✅ 相关性好` / `⚠️ 建议补充查询`），帮助 Agent 决策。

**工具角色：**

| 工具 | 级别 | 功能 | 何时使用 |
|------|-------|----------|-------------|
| `search_confluence` | L1（自主） | 实时 Confluence 搜索 | 本地知识库无答案，或内容可能过时 |
| `save_confluence_page` | L2（需确认） | 缓存页面到本地向量库 | 页面对当前及未来任务有持久价值 |

### 使用示例

```
你：为折扣优惠券和折扣码叠加使用的场景设计测试用例

Agent：（查询本地知识库——无匹配）
       调用 search_confluence("优惠券叠加规则 space=QA")
       找到 3 个相关页面："促销引擎设计规范"、"优惠券叠加规则 v2"……

       [基于 Confluence 文档生成的测试用例]
       TC-001 折扣优惠券 + 折扣码同时使用……
       ……

       💡 "优惠券叠加规则 v2"（page_id: 98765）有价值内容。
          建议 Mentor 确认缓存到本地知识库。
```

### 注意事项

- **L2 权限** — 执行前触发 Mentor 确认
- 保存同一页面多次自动**更新**（删除旧分块，写入新分块）——无需手动清理
- 已缓存页面在 `search_knowledge_base` 结果中以 `confluence:<页面标题>` 为来源显示
- 优先缓存**变更不频繁、引用频繁**的规范类文档；避免缓存高频变更文档（如每日测试汇总）

---


## 六、行为审计日志

每次工具调用、每次 LLM 调用和每次 Mentor 的 L2 批准/拒绝决策都自动写入持久化审计记录。无需额外配置——始终开启。QA Lead 可用此功能审查 Agent 活动、发现可靠性问题，并向管理层汇报 ROI 与费用支出。

### 记录内容

每条记录的 `event_type` 决定其含义，共三类：

| `event_type` | 触发时机 | 说明 |
|---|---|---|
| `tool_call` | 每次工具执行完成 | 记录工具名、入参、输出预览、耗时、是否成功 |
| `llm_call` | 每次 LLM 接口返回 | 记录模型名、input/output token 数、耗时 |
| `l2_decision` | Mentor 批准或拒绝 | 记录 `l2_approved` 布尔值 |

所有类型共享的基础字段：

| 字段 | 描述 |
|-------|-------------|
| `agent_id` / `agent_name` | 哪个 Agent 发起的调用 |
| `conversation_id` | Web 对话上下文 |
| `trace_id` | 同一用户请求内所有事件共享的 UUID，用于全链路追踪 |
| `tool_name` | 工具名称；`llm_call` 事件下此字段存储模型名（如 `claude-sonnet-4-6`） |
| `tool_args` | 完整输入参数（序列化 JSON） |
| `result_preview` | 输出的前 300 个字符 |
| `duration_ms` | 挂钟执行时间（毫秒） |
| `success` | 是否无错完成 |
| `error_msg` | `success = false` 时的错误详情 |
| `input_tokens` | LLM 输入 token 数（仅 `llm_call` 有效） |
| `output_tokens` | LLM 输出 token 数（仅 `llm_call` 有效） |
| `l2_approved` | `true` / `false`（仅 `l2_decision` 有效） |
| `created_at` | UTC 时间戳 |

### Token 计费

每次 LLM 调用完成后，`agent.py` 从响应对象读取 `input_tokens` / `output_tokens` 并调用 `log_llm_call()` 写入审计日志。汇总接口 `/api/audit/summary` 在指定时间窗口内聚合所有 `llm_call` 事件，按以下公式估算费用：

```
estimated_cost_usd = (total_input_tokens  / 1_000_000) × $3.00
                   + (total_output_tokens / 1_000_000) × $15.00
```

> 价格基于 Claude Sonnet 的 API 定价（每百万 token：输入 $3、输出 $15）。如切换模型，需在 `audit.py` 中同步更新系数。

汇总接口返回的 `tokens` 字段结构：

```json
{
  "tokens": {
    "input":  12400,
    "output": 3100,
    "estimated_cost_usd": 0.0838
  }
}
```

单条 `llm_call` 事件也可用 `/api/audit/trace/{trace_id}` 按对话轮次查看 token 明细，返回 `total_input_tokens` 和 `total_output_tokens`。

### Web 看板（AuditPanel）

在侧边栏点击**审计日志**打开看板。加载时以及过滤条件变化时调用 `/api/audit/summary` 和 `/api/audit`。

**统计卡片（第一行）：**
- **工具调用** — 所选周期内的总调用次数
- **成功率** — ≥ 95% 显示绿色，否则显示黄色
- **平均时长** — 每次工具调用的平均延迟
- **L2 决策** — 已批准 ✅ vs. 已拒绝 ❌ 计数并排

**Token 用量卡片（第二行，有 `llm_call` 数据时显示）：**
- **Input Tokens** — 周期内累计输入 token 数
- **Output Tokens** — 周期内累计输出 token 数
- **Est. Cost (USD)** — 按上述公式估算的美元费用（保留 4 位小数）

**趋势图** — 显示最近 N 天工具调用量的每日柱状图（recharts `BarChart`）。

**Top 工具** — 每个工具一条水平条，显示相对调用占比、绝对数量、平均延迟，以及非零时的错误数量。

**事件表格** — 每页 50 行分页：
- 列：时间、Agent、工具、类型（颜色编码徽章）、时长、状态/费用
- `llm_call` 行的"费用"列显示该次调用的单次估算成本（黄色字体）
- 点击任意行展开内联详情抽屉，显示完整参数、结果预览，以及 `llm_call` 行的 token 明细（输入 / 输出）
- 内联过滤器：工具名文本框、事件类型下拉框（含 `llm_call` 选项）；按 Enter 或失焦后生效

**过滤栏（头部）：** Agent 下拉框（所有 Agent 或单个）、时间窗口选择器（1d / 7d / 14d / 30d / 90d）、手动刷新按钮。

---

## 七、测评平台

测评平台将**训练 → 评估 → 调整**的完整闭环搬到 Web UI 中——不再需要手动复制粘贴。

### 工作原理

```
Mentor 在浏览器打开 /exams
  ↓
选择 Agent + 考题（或"全部考题"）→ 点击运行
  ↓
服务器创建状态为 "running" 的 ExamRun 行，立即返回 run ID
  ↓
后台线程：用 Agent 的专项化构建 LangGraph Agent，
  用考题 Prompt 调用，自动评分关键词命中，写入结果
  ↓
浏览器每 3 秒轮询，直到状态变为 "done"
  ↓
Mentor 查看自动评分 + 输出；填写 Mentor 评分滑块 → 提交
  ↓
服务器重新计算 total_score 和 passed，更新行
```

### Web UI 功能

**顶部工具栏**
- Agent 下拉框（选择一个运行，或选"所有 Agent"查看全部历史）
- 考题下拉框（指定文件或"所有考题"）
- **运行**按钮（未选择 Agent 时禁用）
- 刷新图标重新加载历史

**运行中指示条** — 对每个进行中的运行显示一个带 Agent 名称和考题 ID 的 spinner；全部完成后消失。

**历史标签页**
- 摘要统计卡片：总运行次数、通过率、平均分
- **分数趋势折线图**：x 轴为日期，每道考题一条线，y 轴为总分；追踪随时间的进步
- **运行历史表格**：时间 / Agent / 考题 / 自动分 / 总分 / 耗时 / 结果
  - 点击任意行展开详情抽屉，显示：
    - 评分明细（自动分 × 权重 + Mentor 分 × 权重）
    - 关键词检查（未命中关键词以红色高亮）
    - 完整 Agent 输出（可滚动，最多显示 12 行）
    - **Mentor 评分表单**：每个评判标准一个滑块（0.0–1.0）；提交按钮发送评分并刷新行显示最终结果

**对比标签页**
- Agent 选择面板（切换按钮，带颜色圆点）
- **分组柱状图**：x 轴为考题 ID，按 Agent 分组的柱子，y 轴为最新总分
- **对比表格**：每行为一道考题，每列为一个选中的 Agent，颜色编码分数

### 评分模型

评分分为两层，在 `eval/judge.py` 中实现：

**第一层：规则检查（`evaluate_rules`）**

纯字符串匹配，无需 LLM。对考题 YAML 中定义的每条 `rules` 逐一检验（当前支持 `contains_any` 类型），输出命中 / 未命中列表，汇总为 `auto_score`：

```
auto_score = (命中规则数 / 总规则数) × 100
```

**第二层：LLM-as-Judge（`evaluate_criteria`）**

若考题定义了 `criteria`（评判标准），系统自动调用 LLM 对每条标准打分，无需 Mentor 介入。

```
Judge 系统 Prompt：QA 考官角色，要求严格公正
用户 Prompt：考题场景 + Agent 原始输入 + Agent 完整输出 + 各评判标准（含 weight）
LLM 返回 JSON：
  {
    "<criterion_id>": {
      "score":     0–3,          # 0 完全不符合 / 3 完全符合
      "evidence":  "直接引用的原文片段（≤150 字符）",
      "reasoning": "打分理由（≤200 字符）"
    }
  }
```

`judge_to_score` 将各标准分数转换为加权 0–100 分：

```
judge_score = Σ (score_i / 3 × 100 × weight_i)   （权重归一化处理）
```

**最终合分**

```
total_score = auto_score × auto_weight + judge_score × mentor_weight
passed      = total_score ≥ pass_threshold
```

三种模式按考题 YAML 内容自动选择：

| 考题配置 | 行为 |
|----------|------|
| 有 `criteria` | LLM-as-Judge 自动运行，立即得出 `passed` 结论 |
| 无 `criteria`，有 `mentor_criteria` | Judge 不运行，`passed` 保持 `null`，等待 Mentor 手动提交评分 |
| 两者均无 | 纯规则自动评分，`mentor_weight` 折入 `auto_weight` |

Mentor 也可在 Judge 完成后通过滑块覆盖评分，服务器重新计算 `total_score`。权重和阈值来自 YAML 定义（`auto_score_weight` 默认 0.6，`mentor_score_weight` 默认 0.4，`pass_threshold` 默认 70）。

### Prompt 自动优化（反馈闭环）

当测评失败时，平台可以自动分析失败原因并提出针对性的 Prompt 改进建议——只需一键即可完成「训练 → 评估 → 调整」的闭环。

```
考题运行失败（关键词未命中、Judge 评分低）
  ↓
Mentor 在 ExamPanel 点击「建议改进」
  ↓
服务器调用 eval/suggester.py：
  - 加载当前激活的 Prompt 版本 + 考题 YAML
  - 将未命中关键词和 Judge 评分明细发送给第二个 LLM
  - 收到结果：{ diagnosis（根因诊断）, suggestions（建议列表）, patched_prompt（修订后完整 Prompt）}
  ↓
SuggestionPanel 展示诊断结论 + 可折叠的建议卡片（含 patch 文本）
  ↓
Mentor 点击「应用到新 Prompt 版本」
  ↓
服务器根据 patched_prompt 创建新 PromptVersion（旧版本自动停用）
  ↓
重新运行考题，对比新旧版本分数
```

---

## 八、GitLab MR 代码变更感知

QA 日常工作中最耗时的部分之一：**阅读需求和代码 diff，然后决定跑哪些回归测试**。Agent 现在可以自动化这一分析。

### 工作流程

```
你提供一个 Jira 工单（如 SPPT-12345）
  ↓
get_jira_issue 读取工单详情
  ↓
Agent 从描述/评论中提取 GitLab MR URL
  ↓
get_gitlab_mr_diff 获取完整 diff
  ↓
按模块分类变更文件（API / DB / 消息 / 前端 / ...）
  ↓
生成结构化的回归测试建议
```

### 输出示例

```
📁 API 层
  [MODIFIED] src/controller/CartController.java  (+45 -12)
  [MODIFIED] src/service/CartService.java         (+30 -8)

📁 数据库迁移
  [ADDED]    db/migration/V20240420__add_cart_column.sql  (+15 -0)

── 回归范围建议 ──
  • API 层：
      - API 集成测试
      - 契约测试
  • 数据库迁移：          ← 高风险，优先测试
      - DB 迁移测试
      - 数据完整性检查
```

### 使用示例

```
你：分析工单 SPPT-12345——我应该跑哪些回归测试？

Agent：（调用 get_jira_issue → 找到 MR URL → 调用 get_gitlab_mr_diff）

       本次 MR 修改了以下模块的 8 个文件：
       - API 层：CartController、CartService（接口逻辑变更）
       - 数据库迁移：新增购物车表列（高风险）
       - 消息：CartEventProducer（异步通知）

       建议回归范围：
       1. 完整的加购/修改/删除流程（API 集成测试）
       2. 迁移前后数据一致性验证
       3. 购物车成功事件投递验证（消息队列集成测试）
       4. 相关 E2E：结算上游链路
```

---

## 九、E2E 测试执行（Playwright + LLM 视觉）

平台内置了一套 UI 层自动化测试执行引擎，通过 Playwright 驱动真实浏览器，并利用 Claude 的视觉能力解读截图并决定操作——**无需 CSS 选择器或 XPath**。

### 工作原理

每个测试用例步骤在循环中执行：

```
截图 → decide_actions(截图, 步骤描述)
     → 执行操作（点击、输入、滚动……）
     → 截图 → verify_result(截图, 预期结果)
     → 通过 / 失败 + 保存证据截图
```

`decide_actions` 和 `verify_result` 均通过 Anthropic API 调用，将截图作为 base64 图片块传入。Claude 视觉识别页面元素后返回结构化 JSON（`{"type":"click","x":…,"y":…}`）。Agent 自行拆解多操作步骤——不要求每步仅对应一个操作。

执行在后端后台线程中运行；前端每 3 秒轮询进度。截图保存到 `output/test_runs/<run_id>/` 并通过专用 API 接口提供服务。

### Browser Skills（浏览器技能）

执行测试所需的上下文（环境 URL、凭证、测试数据、执行提示）以 **Browser Skills** 形式存储在 DB 中——不再硬编码在 UI 里。技能分为两类：

- **环境技能（Environment Skills）** — 每个目标环境一个；必须包含 `base_url:` 行；提供凭证、测试数据和环境注意事项。每次执行选择一个。
- **额外技能（Extra Skills）** — 可复用的执行提示（如"登录流程"、"弹窗处理"、"结算流程模式"）。每次执行可多选。

所有选中的技能拼接后作为上下文块注入到每次 `decide_actions` 和 `verify_result` 的调用提示中，确保 Claude 始终获得正确的凭证和环境上下文。

在 **Settings → Browser Skills**（`/browser-skills`）管理技能：两个 Tab（Environment / Extra）、左侧列表 + 右侧等宽字体编辑器、内联保存/删除。

环境技能示例：

```markdown
# Environment: Example SG Staging

base_url: https://staging.example.sg

credentials:
  username: testuser@example.com
  password: Test1234

test_data:
  product_id: '88001'
  voucher_code: 'TEST50'

notes:
  - CAPTCHA 在 Staging 环境已关闭
  - 支付网关已 Mock
```

### 启动测试执行

在 **Test Suites** 中选择套件，点击 **▶ Run**。弹窗要求填写：
- **运行名称**（如"Sprint 16 回归"）
- **环境技能**（必选，提供 base URL + 凭证）
- **额外技能**（可选多选）

执行立即在后台启动，自动跳转到 **TestRunView**。

### Android E2E 测试执行（ADB + LLM 视觉）

除 Web 浏览器之外，平台还支持通过 **ADB（Android Debug Bridge）** 对 Android 设备或模拟器执行 UI E2E 测试——同样基于 Claude 视觉，无需 Appium 或 XPath。

执行流程与 Web 端一致：

```
ADB 截图 → decide_actions(截图, 步骤描述, 分辨率)
         → 执行 ADB 操作（tap / swipe / type / keyevent / launch）
         → 截图 → verify_result()
         → 通过 / 失败 + 保存截图
```

因 Android 设备分辨率各异，屏幕尺寸在每条用例执行前通过 `adb shell wm size` 动态查询，并注入到 LLM 提示词中，以确保坐标计算准确。

**Android 环境技能示例**：

```markdown
# Environment: Example Android Staging

device_serial: emulator-5554
app_package: com.example.app
app_main_activity: com.example.app.MainActivity

credentials:
  username: testuser@example.com
  password: Test1234
```

在 Start Run 弹窗选择平台（`🌐 Web` / `🤖 Android`），其余流程（技能选择、TestRunView 查看进度）与 Web 端完全相同。

**前置条件**：需在 `PATH` 中有 `adb`（通过 Android Studio SDK 或 `brew install android-commandlinetools` 安装）并有已连接的设备或模拟器（`adb devices` 可以确认）。
