# 数字员工平台 — 路线图

---

## V1 · 已完成

### 业务功能

| 功能 | 说明 |
|------|------|
| 多 Agent 管理 | 按业务线创建、编辑、Offboard Agent；内置快速创建预设（促销、支付、平台、数据质量） |
| 实时 Chat | WebSocket 流式推送，思考过程、工具调用、工具结果逐步可见 |
| L1/L2 权限体系 | L1 工具自动执行；L2 工具暂停等待 Mentor 审批（Human-in-the-Loop） |
| Agent 职级系统 | Intern / Junior / Senior / Lead 映射不同权限上限；system prompt 身份描述运行时动态注入 |
| 工具集成 | 本地 KB RAG、Confluence 混合检索、Jira JQL + Issue 详情、GitLab MR diff 分析 |
| 跨会话记忆 | `save_to_memory` 写入本地 JSON，下次对话自动注入 system prompt |
| 知识库 Main + Branch | Main KB 全 Agent 共享；Branch KB 按 Agent 隔离；文档上传；Branch → Main 一键 Promote |
| 对话 → KB 蒸馏 | 删除对话时可选保存摘要到 Agent Branch KB；LLM 提炼对话精华，写入 ChromaDB |
| Group Chat | 2+ Agent 多轮协作；Supervisor Pattern 路由；PASS 机制；双重终止守卫；实时流式 |
| Exam 测评平台 | YAML 驱动考题；关键词自动评分 + Mentor 人工打分；异步执行；成绩趋势图；多 Agent 对比 |
| 行为审计日志 | 所有工具调用 + L2 决策写入 SQLite；Web 可视化（统计卡、趋势图、事件详情表） |

### 技术架构

| 技术点 | 实现 |
|--------|------|
| Agent 编排 | LangGraph StateGraph（可含环）+ interrupt_before HITL 中断/恢复 |
| 多轮对话状态 | MemorySaver checkpointer，按 thread_id 隔离 |
| RAG | ChromaDB + OpenAI embedding；Main + Branch 双集合；两阶段检索策略 |
| 异步桥接 | `asyncio.to_thread` + `asyncio.Queue` 桥接同步 LangGraph 到异步 WebSocket |
| Multi-Agent | Supervisor Pattern；`operator.add` reducer；GroupChatState；fresh thread_id |
| System Prompt | 静态模板 + ranking/specialization/memory 三层运行时注入；prompt 不落库 |
| 权限路由 | TOOL_RISK_LEVEL × Agent Ranking ceiling 双维度路由 |
| 存储 | SQLite + SQLAlchemy ORM（Agents / Conversations / Messages / ExamRuns / AuditLogs） |
| 前端 | React + Vite + Tailwind CSS；recharts 图表；WebSocket 实时通信 |
| LLM 适配 | 统一 `call_llm` 接口，支持 Anthropic / OpenAI，`.env` 一行切换 |

---

## V2 · 规划中

### P0 — 技术债 & 核心体验

- [x] **Token 级流式输出**
  `llm_client` 支持 streaming 模式；`token_callback` 通过 LangGraph config 注入 `qa_agent_node`；
  WebSocket handler 的 `_astream` 用同一 queue 多路复用 node 事件和 token delta；
  前端 `message_start → token* → done` 协议实现逐字打字效果

- [x] **Context window 管理**
  每次对话前从 DB 加载历史，超过 `CONTEXT_COMPRESS_THRESHOLD`（默认 40 条）时用 LLM 将旧消息压缩为摘要；
  DB 保留完整历史，只压缩传给 LangGraph 的 in-flight state

- [x] **Token 用量追踪**
  `LLMResponse` 携带 `input_tokens / output_tokens`；`qa_agent_node` 每次 LLM 调用后写入 `audit_logs`
  （`event_type=llm_call`）；Audit Log summary API 汇总 token 数和 Claude Sonnet 估算成本；
  AuditPanel 新增 Input Tokens / Output Tokens / Est. Cost 三张统计卡；
  事件表格新增 Cost 列，仅对 `llm_call` 行显示黄色美元金额（$3/M input + $15/M output）

- [x] **LLM 应用可观测性（三大支柱）**
  **P0 链路追踪**：每轮对话生成 `trace_id`，随 LangGraph config 传播，所有 audit 事件共享同一 trace；
  `audit_logs` 新增 `trace_id`、`node_name`、`extra_data_json` 字段；
  `/api/audit/trace/{id}` 接口返回完整事件瀑布图；AuditPanel 展开行可点击查看 trace；
  **P1 健康评分**：summary API 新增 `health` 字段（综合评分 0–1、P95 延迟、误差率趋势）；AuditPanel 展示 Health Score 卡片；
  **P2 对话质量实时评分**：每轮对话结束后异步 LLM-as-Judge 评分（helpfulness/boundaries/clarity），
  结果以 `event_type=quality_score` 写入 audit_logs，AuditPanel 展示质量趋势折线图；
  **P3 知识库使用分析**：`execute_tool` 从 search_knowledge_base 结果解析 top_score 和 result_count，
  写入 extra_data_json；summary API 新增 `kb_stats`（low_relevance_rate、avg_top_score）

### P1 — 评测体系升级

- [x] **LLM-as-Judge**
  测评完成后，用独立 LLM 对 Agent 输出打分，减少对人工 Mentor 的依赖；结合现有 Mentor Score 形成三层评分

- [x] **Prompt 版本管理**
  Agent system prompt 变更时记录版本快照，可对比不同 prompt 版本下的测评成绩变化

### P2 — 产品与用户体验

- [x] **多角色数字员工平台**
  从仅支持 QA 扩展为通用数字员工平台，支持 QA / Dev / PM / SRE / PJ 五种角色；
  每个角色拥有独立的 system prompt（`agent/prompts.py`）和入职预设；
  侧边栏展示角色徽章；多角色同时存在时按角色分组展示

- [x] **角色 Prompt 模板管理**
  系统级 CRUD 支持每个角色的 base prompt 模板；侧边栏新增 `/role-prompts` 页面；
  新员工入职时自动从对应角色模板初始化 base prompt
  （优先级：DB 中的自定义模板 → 内置 dict → QA 兜底）；
  编辑器支持保存 / 重置为默认 / 未保存状态提示

- [x] **i18n（中英文切换）**
  所有界面文本提取到 `i18n.jsx` 的 `TRANSLATIONS` 字典中；顶栏提供 EN/ZH 切换按钮；
  语言偏好持久化到 `localStorage`；`useLang()` hook 在所有组件中可用

- [x] **深色 / 浅色主题**
  首次加载时自动适配系统偏好；顶栏提供手动切换按钮；
  全局使用 Tailwind `dark:` 变体；偏好持久化到 `localStorage`

- [x] **Exam 平台 — 角色支持**
  考题 YAML、`ExamPayload` 及 REST API 响应均新增 `role` 字段；
  "Select Exams" → "Select Questions"，选择面板新增搜索框 + 角色筛选 Pill；
  Manage 页面考题按角色分组（QA / Dev / PM / SRE / PJ），带彩色分组标题和角色圆点徽章；
  "New Exam" 弹窗 → "New Question"，并新增 Role 下拉字段；
  旧考题兼容：根据 ID 前缀推断角色作为回退方案

- [x] **内联确认对话框**
  所有原生 `window.confirm()` 调用均替换为内联两步确认行；
  "Offboard Agent" 重命名为 "Offboard Employee"，配合 Cancel / Offboard 内联确认；
  Group Chat 删除和考题删除均采用相同模式

- [x] **可配置权限系统**
  工具风险级别（L1/L2/L3）和各职级权限上限现已 DB 持久化，可在侧边栏新增的 **权限管理** 页面直接编辑，无需改代码或重启服务；
  `tool_risk_config` 和 `ranking_ceiling_config` 表在首次启动时从 `config.py` 自动种入默认值；
  `_ensure_tools()` 在下次打开页面时自动检测并补录新增到 `TOOL_RISK_LEVEL` 的工具；
  `agent.py` 从 LangGraph config 读取配置，终端模式和测评模式回退到代码中的硬编码默认值

- [x] **Prompt 自动优化反馈闭环**
  测评失败后，Mentor 点击「建议改进」即可触发独立 LLM 对未命中关键词和 Judge 评分的分析；
  Suggester 返回根因诊断 + 1~4 条具体 patch 建议 + 完整修订 Prompt；
  Mentor 一键应用即可创建新 `PromptVersion`；
  `eval/suggester.py`（纯函数 `build_suggester_prompt` + `generate_suggestions`）；
  `prompt_suggestions` 表缓存结果；`ExamPanel.jsx` 新增 `SuggestionPanel` 组件

- [x] **语义记忆**
  将原先平铺 JSON 记忆注入升级为 ChromaDB 向量检索；
  `load_memory_context(query=<最后一条用户消息>)` 按余弦相似度只取最相关的 Top-5 记忆片段；
  三层优雅降级：语义命中 → 重建索引后重试 → 回退到完整 JSON；
  `tools/semantic_memory.py`（`save_to_index`、`search`、`rebuild_index`）；
  `agent.py` 在每次 LLM 调用前提取最后一条 `HumanMessage` 作为查询；
  完全向下兼容——ChromaDB 不可用时行为不变

### P3 — 业务集成完善

- [x] **考题库扩充（共 41 题）**
  新增 20 道 QA 角色考题，覆盖电商场景（促销叠加、购物车边界、支付重试、注册、搜索排名）、缺陷分析、需求澄清、回归测试、风险评估和安全测试；考题库总量达 41 道 YAML 用例

- [x] **真实 Jira 缺陷创建**
  `tools/jira_create_issue.py` — 真实 Jira REST API v2（`POST /rest/api/2/issue`）；支持 Basic Auth（Cloud）和 PAT（Server/DC）；L2 风险级别，需 Mentor 审批；返回 Issue Key + URL；完全替代 `create_defect_mock.py`

- [x] **MR 驱动的测试用例生成**
  `tools/test_suite_writer.py` → `save_test_suite()`（L1 工具，支持 `component`/产品线参数）；DB 持久化 `TestSuite` / `TestCase` 模型（含 `component` 列）；12 个 REST 接口（`web/api/test_suites.py`），包含 `GET /test-suites`（全局列表，支持 `component`/`source_type`/`search` 过滤）和 `GET /test-suites/components`；Markdown + XMind 导出（ZIP + XMind Zen JSON 格式，无需第三方库）；`TestSuitePanel.jsx` — **产品线下拉筛选**替代原来的 Agent 筛选、来源类型标签（All/Jira/MR/Manual）、实时搜索框、优先级过滤（P0–P3）、树状视图 CRUD + 优先级标签；**浏览器内思维导图**（纯 SVG，点击按钮即可在浏览器内展示，无需安装 XMind 客户端）；`seed_test_suites.py` — Example Company SG 模拟数据（10 套件 / 56 用例）

- [x] **生产故障 → 考题（对话驱动）**
  `tools/propose_exam_case.py`（L1）将完整考题序列化为 YAML 并保存至 `exams/drafts/`；返回人类可读预览 + 机器可读 `DRAFT_ID:{id}` 标记；`ChatView.jsx` 中的 `ExamDraftCard` 组件检测标记，显示琥珀色边框卡片，含「加入考题库」/「丢弃」按钮；三个草稿管理接口（`GET /exam-drafts`、`POST /exam-drafts/{id}/publish`、`DELETE /exam-drafts/{id}`）

- [x] **E2E 测试执行（Playwright + LLM 视觉）**
  UI 层自动化测试执行引擎：截图 → `decide_actions()` → Playwright 操作 → 截图 → `verify_result()`，无需 CSS 选择器；
  `browser/actions.py`（Playwright 会话封装）、`browser/vision.py`（Anthropic 视觉调用，传入 base64 图片块）、`browser/executor.py`（单条用例执行循环）、`browser/runner.py`（执行编排——加载技能、组装上下文、写入 DB）；
  后台 daemon 线程中执行，前端每 3 秒轮询 `/test-runs/{id}`；
  `TestRunView.jsx` — 进度条、用例展开、执行前后截图、点击放大；
  SQLite 中新增 `test_runs` + `test_run_cases` 表；9 个 REST 接口（`web/api/test_runs.py`）

- [x] **Browser Skills — SKILL.md 风格的 E2E 上下文注入**
  用 DB 持久化的 Markdown/YAML 技能文档替代硬编码的 base URL；
  两种技能类型：*环境技能*（每次运行选一个，提供 `base_url`、凭证、测试数据）和*额外技能*（每次运行可多选，提供可复用执行提示，如登录流程、弹窗处理）；
  `browser_skills` 表；完整 CRUD REST API（`web/api/browser_skills.py`）；
  `BrowserSkillsPanel.jsx` — 两 Tab UI（Environment / Extra），左侧列表 + 右侧等宽字体编辑器，内联保存/删除，未保存状态提示；
  所有选中技能拼接后注入到每次 `decide_actions` 和 `verify_result` 的调用提示中；
  `TestSuitePanel.jsx` 中的"启动执行"弹窗新增环境技能下拉（必选）+ 额外技能多选复选框

- [x] **Android UI E2E 自动化（ADB + Claude 视觉）**
  将 E2E 执行引擎扩展至 Android 设备和模拟器，通过 ADB 驱动——无需 Appium 或 XPath；
  `android/actions.py`（ADB 会话封装——截图、tap、swipe、type_text、press_key、launch_app、wait）、`android/vision.py`（动态屏幕分辨率注入提示词——每条用例执行前通过 `adb shell wm size` 查询）、`android/executor.py`（单条用例执行循环，复用相同的步骤/结果 schema）、`android/runner.py`（编排器，复用 browser runner 的 `_assemble_skills_context`）；
  DB 新增 `test_runs.platform` 列（`web` | `android`）并自动迁移；API 根据平台路由到对应 runner；
  Start Run 弹窗新增 `🌐 Web` / `🤖 Android` 切换；`TestRunView.jsx` 展示 `🤖 Android` 标识；
  环境技能扩展支持 `device_serial`、`app_package`、`app_main_activity` 字段

- [x] **Test Platform — 统一测试管理平台**
  将原"Test Suites"菜单重构为五 Tab 的统一测试管理平台（`/test-platform`）：
  **Suites Tab** — 测试套件管理（原有功能，新增测试用例内联编辑：铅笔图标点击即可展开编辑表单，保存调用 `PUT /test-suites/{id}/cases/{caseId}`）；
  **Plans Tab** — 测试计划管理：创建/编辑/删除 Test Plan（可关联多个 Suite）、一键执行 Plan（为每个 Suite 并行启动独立 test run，后台 daemon 线程执行）；`test_plans` 表；完整 CRUD + 执行接口（`web/api/test_plans.py`）；
  **Runs Tab** — 执行历史：全局 test run 列表，支持按 Suite / Status / Platform 筛选 + 实时搜索；有 running/pending 的 run 时每 5 秒自动刷新；点击行跳转 TestRunView；
  **Analytics Tab** — 数据看板：总执行量/通过率统计卡、各 Suite 通过率横向条形图、近 60 天通过率趋势折线图（纯 SVG 实现，无第三方图表库）、Top 8 失败用例排行、状态分布甜甜圈图；`GET /test-runs/analytics` 聚合接口；
  **Test Skills Tab** — 原 Browser Skills 菜单移入平台内（`/browser-skills` 自动 redirect 到 `/test-platform/skills`）；
  `seed_test_platform.py` — 5 个测试计划 + 27 条历史执行记录（Sprint 32–34 通过率 70%→93% 上升趋势）

- [x] **TestRunView 体验升级**
  **步骤级截图与日志**：修复 runner 步骤格式转换 bug（`steps` 字段从字符串数组转换为 `{description, expected_result}` 对象数组后再传入 executor），每个步骤记录执行前/后截图、动作序列、通过/失败原因；
  **Terminate 功能**：Header 新增红色 Terminate 按钮（仅 running/pending 状态可见），点击弹出自定义 Modal 确认（不使用浏览器原生 `confirm()`）；`POST /api/test-runs/{id}/terminate` 立即更新 DB 状态为 `terminated` 并写入内存信号集，runner 线程在每条 case 之间检查信号后停止，步骤5的 `UPDATE` 增加 `status != 'terminated'` 守卫防止覆盖；`terminated` 状态显示为黄色 ⊘ 标识；
  **执行中动态刷新**：运行时 RefreshCw 图标自动旋转（`animate-spin`），每 3 秒自动拉取最新状态；
  **返回按钮**：点击返回跳转 `/test-platform/runs` 而非原来的 `/test-suites`；
  **滚动修复**：根元素改为 `h-full`（原 `flex-1`），确保 flex 高度约束正确传递，展开大截图后页面可正常滚动

- [ ] **Group Chat 知识蒸馏**
  删除 Group Chat 时同样提供 Save to KB 选项（目前只有单人 Chat 有此功能）

- [ ] **Xray / Zephyr 集成**
  将设计好的测试用例直接创建为测试执行记录，实现从设计到执行的闭环

### P4 — 长期方向

- [ ] **多模态支持**
  接收截图、UI 设计稿，辅助 UI 测试用例设计

- [ ] **Agent 定时调度**
  定时自动运行 Exam、生成周报，无需手动触发

---

## V3 · 规划中

> **主题：** 从*工具平台*（人触发、Agent 响应）进化为*团队基础设施*（Agent 主动感知工程事件、在团队沟通里出现、被外部系统直接调用）。

### 现状断点

| 断点 | 描述 |
|------|------|
| 主动性不足 | 所有动作都需要人来发起，Agent 无法感知外部事件 |
| 孤岛式工作 | Agent 独立作业；Group Chat 是临时讨论，不是结构化任务流转 |
| 平台对外封闭 | 所有能力被锁在 Web UI 里，CI/CD 流水线和外部系统无法调用 Agent |

---

### P0 — 事件驱动激活

- [ ] **Webhook + 事件驱动触发**
  新增 `POST /api/webhooks/{agent_id}` 端点，接收外部事件；将事件映射到 Prompt 模板，在后台唤醒对应 Agent 执行；支持的触发源：GitLab MR（opened / merged）、Jira Issue 创建/更新、定时 cron。

  示例触发流程：
  ```
  GitLab MR opened
    → QA Agent：分析 diff → 推荐回归范围 → 生成测试计划
    → Dev Agent：code review 要点 + 边界条件提醒

  Jira Critical Bug 创建
    → QA Agent：关联历史 case → 评估影响面 → 生成复现步骤草稿

  Sprint 结束（定时）
    → QA Agent：生成本周测试覆盖报告 + 遗留风险清单
  ```

- [ ] **Slack / 飞书 / 钉钉 双向集成**
  - **出方向**：Agent 执行结果推送摘要消息到指定 channel
  - **入方向**：在 channel 里 @ 机器人（`@agent "帮我分析 SPPT-12345"`）→ Agent 执行并在 thread 里回复

  这是让平台从"单人工具"变成"团队基础设施"的关键一步。

---

### P1 — 结构化多 Agent 流水线

- [ ] **Pipeline（结构化任务流）**
  有序的 Agent 节点链——每个节点有明确的输入来源和输出目标，取代 Group Chat 用于正式的跨角色工作流。

  示例流水线：
  ```
  PM Agent — 分析需求文档
    ↓ 输出：功能拆解 + 验收标准
  QA Agent — 接收拆解 → 生成测试用例 + 风险点
    ↓ 输出：测试计划
  Dev Agent — 接收计划 → code review checklist + 边界条件提醒
    ↓ 汇总 → 发布到 Confluence / 创建 Jira 子任务
  ```

  实现方案：`pipelines` 数据库表；YAML 配置驱动或可视化节点编辑器；每个节点的输出自动作为下一个节点的上下文注入。

- [ ] **CI/CD 测试执行触发**
  E2E 引擎已完成，打通 CI 最后一公里。`POST /api/test-runs/trigger` 接收 `{ suite_id, env, trigger: "ci" }`，返回运行状态和通过/失败结果用于流水线卡点。提供开箱即用的 GitLab CI / GitHub Actions 配置片段。

---

### P2 — 平台对外开放

- [ ] **Agent API Gateway**
  将每个 Agent 暴露为独立 REST API，允许任意外部工具"雇用" Agent：
  ```
  POST /api/agents/{id}/invoke
  { "message": "...", "context": { "jira_key": "SPPT-12345" } }
  → { "run_id": "...", "status": "running" }   # 异步
  GET  /api/agents/{id}/invoke/{run_id}
  → { "status": "done", "output": "..." }
  ```
  让 Jenkins、GitHub Actions、内部脚本和数据看板可以直接调用 Agent。

- [ ] **Webhook 出向推送（结果回调）**
  Agent 完成后台任务（Webhook 触发或定时任务）后，将结果推送到预配置的 URL——无需轮询即可与任意外部系统集成。

---

### P3 — 智能化升级

- [ ] **测试知识图谱**
  将平台里分散的数据连接成可查询的图：
  ```
  Jira 功能 ←→ 测试用例 ←→ 测试执行 ←→ 缺陷 ←→ MR
  ```
  解锁高价值查询：
  - "这个功能的历史缺陷率是多少？"
  - "哪些测试用例从来没失败过，是冗余的？"
  - "这次 MR 改动了哪些功能，对应的测试覆盖率是多少？"

- [ ] **多模态输入**
  在聊天中接受图片上传：UI 设计稿 → 自动生成界面测试用例；Bug 截图 → Agent 分析并生成复现步骤 + 关联历史相似缺陷。基础能力已在 E2E 视觉模块中具备。

- [ ] **预测性风险评分**
  基于 MR 变更的文件，对每个受影响模块的历史失败率进行评分，在测试运行开始前显示风险热力图。

---

### Context Engineering 优化

> **主题：** 在不改变任何用户可见行为的前提下，降低 token 成本、缩短响应延迟、让 context 使用更精准。

- [x] **Anthropic Prompt Caching** *(P0 — 已落地)*
  `_call_anthropic()` 现在将 `system` 从字符串改为带 `cache_control: {type: ephemeral}` 的 content block 列表，同时对工具定义末尾也标记同样的缓存控制。
  Anthropic 以内容哈希作为缓存键——用户修改了 system prompt（更新 specialization、memory 变化等），下次调用时缓存自动失效并重建新缓存，无需任何手动干预。
  预期节省：**同一 agent 多轮对话 input token 成本降低 40–60 %**（cache read 约为 cache write 的 1/10）。

- [ ] **基于 token 数的上下文压缩阈值** *(P1)*
  将 `CONTEXT_COMPRESS_THRESHOLD = 40`（消息条数）替换为 token 估算阈值（如 60 000 tokens）。
  一条 Jira 结果消息可能有 3 000 tokens，一条"收到"只有 ~5 tokens——用消息条数衡量 context 压力误差极大。
  实现方式：按 `len(str(content)) // 3` 逐条估算，累计超过阈值时触发压缩。

- [ ] **按角色过滤工具定义** *(P1)*
  `get_tool_definitions()` 目前每次无条件返回全部 16 个工具。
  添加 `ROLE_TOOLS` 映射（如 QA: [run_test, create_test_case, jira_get_issue, …]，PM: [jira_create_issue, confluence_create_page, send_email, …]），调用 `call_llm` 前只传相关工具子集。
  预期节省：**工具定义 token 减少 15–30 %**；同时降低模型误调用无关工具的概率。

- [ ] **工具结果大小限制 + 摘要** *(P1)*
  `tools_node` 目前将 `str(result)` 原文注入——Confluence 页面或 Jira 搜索结果可能超过 10 000 字符。
  添加 `MAX_TOOL_RESULT_CHARS` 上限（如 6 000），超出部分由一次轻量 LLM 调用先行摘要再注入。
  防止单次工具调用在后续轮次中持续占据大量 context。

- [ ] **修复工具调用期间的 streaming** *(P2)*
  当前判断 `use_stream = token_callback is not None and not tool_definitions` 意味着 streaming 永远不会触发（因为工具定义每次都传）。
  Anthropic API 支持 streaming + tool use（工具调用内容块以 delta 形式累积）；更新 `_call_anthropic_stream()` 处理 `input_json_delta` 事件，使大多数对话 turn 都能逐 token 流式输出。

- [ ] **动态 `max_tokens` 预算** *(P2)*
  `max_tokens=4096` 对所有调用一刀切，与任务复杂度无关。
  添加简单启发式：工具调用 turn → 1 024（只需 JSON），短问答 → 512，分析类任务 → 4 096。或在 DB 中为每个 agent 增加 `max_output_tokens` 配置字段。

---

### 优先级汇总

| 优先级 | 方向 | 理由 |
|--------|------|------|
| **P0** | Webhook + 事件驱动触发 | 解决"主动性不足"断点，立即提升日常使用频率 |
| **P0** | Slack / 飞书集成 | 让 Agent 进入团队日常沟通流，曝光度最大化 |
| **P0** | Prompt Caching ✅ | 已落地；多轮对话 input token 成本降低 40–60 % |
| **P1** | CI/CD 测试执行触发 | E2E 引擎已完成，打通最后一公里即可 |
| **P1** | Pipeline（结构化任务流） | Group Chat 的正式化升级，适合可重复的跨角色工作流 |
| **P1** | Token 压缩阈值 + 工具过滤 | 更精准的 context 管理，与 Prompt Caching 互补 |
| **P2** | Agent API Gateway | 让外部系统可以调用 Agent，打开生态集成入口 |
| **P2** | Streaming 修复 + 动态 max_tokens | UX 改善 + 输出 token 成本优化 |
| **P3** | 测试知识图谱 | 技术复杂度高，但长期分析价值极大 |
| **P3** | 多模态输入 | 基于现有视觉基础设施构建，对 UI 密集型 QA 场景价值高 |

---

*本文件随每个功能落地同步更新。*
