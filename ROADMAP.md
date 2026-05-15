# Digital Employee Platform — Roadmap

---

## V1 · Completed

### Features

| Feature | Description |
|---------|-------------|
| Multi-Agent Management | Create, edit, and offboard Agents per business line; built-in quick-create presets (promotions, payments, platform, data quality) |
| Real-time Chat | WebSocket streaming: thinking process, tool calls, and tool results visible step by step |
| L1/L2 Permission System | L1 tools auto-execute; L2 tools pause for Mentor approval (Human-in-the-Loop) |
| Agent Ranking System | Intern / Junior / Senior / Lead mapped to different permission ceilings; system prompt identity description dynamically injected at runtime |
| Tool Integrations | Local KB RAG, Confluence hybrid retrieval, Jira JQL + issue details, GitLab MR diff analysis |
| Cross-Session Memory | `save_to_memory` writes to local JSON; automatically injected into system prompt on the next conversation |
| Main + Branch Knowledge Base | Main KB shared across all Agents; Branch KB isolated per Agent; document upload; one-click Branch → Main promotion |
| Conversation → KB Distillation | When deleting a conversation, optionally save a summary to the Agent's Branch KB; LLM distils the conversation highlights and writes to ChromaDB |
| Group Chat | Multi-turn collaboration with 2+ Agents; Supervisor Pattern routing; PASS mechanism; double termination guard; real-time streaming |
| Exam Platform | YAML-driven exam questions; keyword auto-scoring + Mentor manual scoring; async execution; score trend chart; multi-Agent comparison |
| Behavior Audit Log | All tool calls + L2 decisions written to SQLite; web visualization (stat cards, trend chart, event detail table) |

### Technical Architecture

| Component | Implementation |
|-----------|----------------|
| Agent Orchestration | LangGraph StateGraph (supports cycles) + interrupt_before HITL pause/resume |
| Multi-turn Conversation State | MemorySaver checkpointer, isolated by thread_id |
| RAG | ChromaDB + OpenAI embedding; Main + Branch dual collections; two-stage retrieval strategy |
| Async Bridge | `asyncio.to_thread` + `asyncio.Queue` to bridge synchronous LangGraph to async WebSocket |
| Multi-Agent | Supervisor Pattern; `operator.add` reducer; GroupChatState; fresh thread_id per session |
| System Prompt | Static template + three-layer runtime injection (ranking / specialization / memory); prompt never persisted to DB |
| Permission Routing | Dual-axis routing: TOOL_RISK_LEVEL × Agent Ranking ceiling |
| Storage | SQLite + SQLAlchemy ORM (Agents / Conversations / Messages / ExamRuns / AuditLogs) |
| Frontend | React + Vite + Tailwind CSS; recharts charts; WebSocket real-time communication |
| LLM Adapter | Unified `call_llm` interface supporting Anthropic / OpenAI; switch with one line in `.env` |

---

## V2 · Planned

### P0 — Tech Debt & Core Experience

- [x] **Token-level streaming**
  `llm_client` supports streaming mode; `token_callback` injected into `qa_agent_node` via LangGraph config;
  WebSocket handler's `_astream` multiplexes node events and token deltas over the same queue;
  frontend implements character-by-character typing effect via `message_start → token* → done` protocol

- [x] **Context window management**
  Conversation history loaded from DB before each turn; when message count exceeds `CONTEXT_COMPRESS_THRESHOLD` (default 40), a single LLM call compresses older messages into a summary;
  DB retains full history; only the in-flight state passed to LangGraph is compressed

- [x] **Token usage tracking**
  `LLMResponse` carries `input_tokens / output_tokens`; `qa_agent_node` writes to `audit_logs` after each LLM call
  (`event_type=llm_call`); Audit Log summary API aggregates token counts and estimated Claude Sonnet cost;
  AuditPanel adds three new stat cards: Input Tokens / Output Tokens / Est. Cost;
  event table adds a Cost column, showing yellow dollar amounts only for `llm_call` rows ($3/M input + $15/M output)

- [x] **LLM observability (three pillars)**
  **P0 Distributed Tracing**: per-turn `trace_id` propagated through LangGraph config; all audit events share the same trace;
  `audit_logs` gains `trace_id`, `node_name`, `extra_data_json` fields;
  `/api/audit/trace/{id}` returns the full event waterfall; AuditPanel expanded row shows a "View trace" link;
  **P1 Health Score**: summary API adds a `health` field (composite score 0–1, P95 latency, error rate trend); AuditPanel shows a Health Score card;
  **P2 Conversation Quality Scoring**: async LLM-as-Judge scoring after each turn (helpfulness / boundaries / clarity),
  written as `event_type=quality_score` in audit_logs; AuditPanel shows a quality trend line chart;
  **P3 KB Usage Analytics**: `execute_tool` parses `top_score` and `result_count` from search_knowledge_base results
  and stores them in `extra_data_json`; summary API adds `kb_stats` (`low_relevance_rate`, `avg_top_score`)

### P1 — Evaluation System Upgrades

- [x] **LLM-as-Judge**
  After exam completion, use an independent LLM to score Agent output, reducing reliance on manual Mentor scoring; combined with the existing Mentor Score to form a three-layer scoring model

- [x] **Prompt version management**
  Record version snapshots whenever an Agent's system prompt changes; compare exam score changes across different prompt versions

### P2 — Product & UX

- [x] **Multi-role digital employee platform**
  Expanded from QA-only to a general-purpose digital employee platform supporting QA / Dev / PM / SRE / PJ;
  each role has its own system prompt (`agent/prompts.py`) and onboarding presets;
  role badge shown in sidebar; agents grouped by role when multiple roles coexist

- [x] **Role prompt template management**
  System-level CRUD for per-role base prompt templates; new `/role-prompts` page in the sidebar;
  newly onboarded agents are automatically seeded with the matching role template
  (priority: custom DB template → built-in dict → QA fallback);
  editor supports save / reset-to-default / unsaved-changes indicator

- [x] **i18n (English / Chinese)**
  All UI text extracted into the `TRANSLATIONS` dict in `i18n.jsx`; EN/ZH toggle in the top bar;
  language preference persisted to `localStorage`; `useLang()` hook available in all components

- [x] **Dark / Light mode**
  System-preference-aware on first load; manual toggle in the top bar;
  Tailwind `dark:` variant used throughout; preference persisted to `localStorage`

- [x] **Exam platform — role support**
  Explicit `role` field added to question YAML, `ExamPayload`, and REST API responses;
  "Select Exams" → "Select Questions" with search input + role filter pills;
  Manage tab questions grouped by role (QA / Dev / PM / SRE / PJ) with colored group headers and role-dot badges;
  "New Exam" modal → "New Question" with a Role dropdown field;
  role inferred from ID prefix as a backward-compatible fallback

- [x] **Inline confirm dialogs**
  All native `window.confirm()` calls replaced with inline two-step confirm rows;
  "Offboard Agent" renamed to "Offboard Employee" with Cancel / Offboard inline confirm;
  Group Chat delete and exam question delete use the same pattern

- [x] **Configurable permission system**
  Tool risk levels (L1/L2/L3) and ranking permission ceilings are now DB-backed and editable
  from the new **Permissions** sidebar page — no code changes or restarts required;
  `tool_risk_config` and `ranking_ceiling_config` tables seeded from `config.py` defaults on first run;
  `_ensure_tools()` auto-detects and backfills new tools added to `TOOL_RISK_LEVEL` on next page load;
  `agent.py` reads config from LangGraph config; terminal mode and exam mode fall back to hardcoded defaults

- [x] **Prompt auto-improvement feedback loop**
  After a failed exam run, Mentor clicks "Suggest Improvements" to trigger an independent LLM analysis
  of missed keywords and judge scores; the Suggester returns a root-cause diagnosis + 1–4 concrete patch suggestions
  + a full revised prompt; Mentor can apply with one click to create a new `PromptVersion`;
  `eval/suggester.py` (pure functions: `build_suggester_prompt` + `generate_suggestions`);
  `prompt_suggestions` DB table caches results; `SuggestionPanel` component in `ExamPanel.jsx`

- [x] **Semantic memory**
  Upgraded flat JSON memory injection to ChromaDB-backed vector retrieval;
  `load_memory_context(query=<last user message>)` retrieves only the top-5 most relevant memory
  fragments by cosine similarity; three-layer graceful degradation: semantic hit → rebuild-and-retry
  → full JSON fallback; `tools/semantic_memory.py` (`save_to_index`, `search`, `rebuild_index`);
  `agent.py` extracts the last `HumanMessage` as the query before each LLM call;
  fully backward-compatible — no behavior change when ChromaDB is unavailable

### P3 — Business Integration

- [x] **Exam library expansion (41 questions)**
  Added 20 new QA-role exam questions covering e-commerce scenarios (promo stacking, cart boundary conditions, payment retry, registration, search ranking), defect analysis, requirements clarification, regression testing, risk assessment, and security testing; total exam library now stands at 41 YAML cases

- [x] **Real Jira defect creation**
  `tools/jira_create_issue.py` — real Jira REST API v2 (`POST /rest/api/2/issue`); supports Basic Auth (Cloud) and PAT (Server/DC); L2 risk level requires Mentor approval; returns issue key + URL on success; fully replaces `create_defect_mock.py`

- [x] **MR-driven test suite generation**
  `tools/test_suite_writer.py` → `save_test_suite()` (L1 tool, accepts `component`/product-line parameter); DB-backed `TestSuite` / `TestCase` models with `component` column; 12-endpoint REST API (`web/api/test_suites.py`) including `GET /test-suites` (global list with `component`/`source_type`/`search` filters) and `GET /test-suites/components`; Markdown + XMind export (ZIP + XMind Zen JSON format, no third-party library required); `TestSuitePanel.jsx` — **product-line dropdown filter** replaces the old agent-based filter, source-type pills (All/Jira/MR/Manual), live search, priority filter (P0–P3), tree-view CRUD + priority badges; **in-browser mind map** (pure SVG, click to expand in browser — no XMind client required); `seed_test_suites.py` — Example Company SG mock data (10 suites / 56 cases)

- [x] **Production failure → exam question via chat**
  `tools/propose_exam_case.py` (L1) serialises a complete exam question as YAML and saves it to `exams/drafts/`; returns a human-readable preview plus a machine-readable `DRAFT_ID:{id}` marker; `ExamDraftCard` component in `ChatView.jsx` detects the marker and shows an amber-bordered card with "Add to Exam Library" / "Discard" buttons; three draft management endpoints (`GET /exam-drafts`, `POST /exam-drafts/{id}/publish`, `DELETE /exam-drafts/{id}`)

- [x] **E2E test execution (Playwright + LLM vision)**
  UI-layer automated test execution engine: screenshot → `decide_actions()` → Playwright actions → screenshot → `verify_result()` — no CSS selectors required;
  `browser/actions.py` (Playwright session wrapper), `browser/vision.py` (Anthropic vision calls with base64 image blocks), `browser/executor.py` (per-case execution loop), `browser/runner.py` (run orchestrator — loads skills, assembles context, writes to DB);
  runs in a background daemon thread; frontend polls `/test-runs/{id}` every 3 s;
  `TestRunView.jsx` — progress bar, per-case expand, before/after screenshots, click-to-enlarge;
  `test_runs` + `test_run_cases` tables in SQLite; 9-endpoint REST API (`web/api/test_runs.py`)

- [x] **Browser Skills — SKILL.md-style context injection for E2E**
  Replaces hardcoded base URLs with DB-backed Markdown/YAML skill documents;
  two skill types: *environment skills* (one selected per run — provides `base_url`, credentials, test data) and *extra skills* (multi-selectable per run — reusable execution hints such as login flows and popup handling);
  `browser_skills` table; full CRUD REST API (`web/api/browser_skills.py`);
  `BrowserSkillsPanel.jsx` — two-tab UI (Environment / Extra), left list + right monospace editor, inline save/delete, unsaved-changes indicator;
  all selected skills are concatenated and injected into every `decide_actions` and `verify_result` prompt call;
  Start Run modal in `TestSuitePanel.jsx` — env skill dropdown (required) + extra skills checkboxes (multi-select)

- [x] **Android UI E2E automation (ADB + Claude vision)**
  Extends the E2E execution engine to Android devices and emulators via ADB — no Appium or XPath required;
  `android/actions.py` (ADB session wrapper: screenshot, tap, swipe, type_text, press_key, launch_app, wait), `android/vision.py` (dynamic screen-resolution injection into the system prompt — queries `adb shell wm size` before each case), `android/executor.py` (per-case execution loop reusing the same step/result schema), `android/runner.py` (orchestrator, reuses `_assemble_skills_context` from the browser runner);
  `test_runs.platform` column (`web` | `android`) added to DB with automatic migration; API routes to the correct runner based on platform;
  Start Run modal adds `🌐 Web` / `🤖 Android` toggle; `TestRunView.jsx` shows `🤖 Android` badge;
  environment skill extended to accept `device_serial`, `app_package`, `app_main_activity`

- [x] **Test Platform — unified test management hub**
  Restructured the "Test Suites" menu into a five-tab unified test management platform (`/test-platform`):
  **Suites Tab** — test suite management (existing, plus new inline case editing: pencil icon opens an inline edit form, saves via `PUT /test-suites/{id}/cases/{caseId}`);
  **Plans Tab** — test plan management: create/edit/delete Test Plans (each plan groups multiple suites), one-click execution launches a parallel background run per suite; `test_plans` table; full CRUD + execute API (`web/api/test_plans.py`);
  **Runs Tab** — execution history: global list of all test runs with Suite / Status / Platform filters and live search; auto-refreshes every 5 s while any run is active; click a row to open TestRunView;
  **Analytics Tab** — dashboard: total runs / pass-rate stat cards, per-suite pass-rate horizontal bar chart, 60-day pass-rate trend line chart (pure SVG, no third-party chart library), Top-8 failing cases ranking, status distribution donut chart; `GET /test-runs/analytics` aggregation endpoint;
  **Test Skills Tab** — former Browser Skills page moved inside the platform (`/browser-skills` redirects to `/test-platform/skills`);
  `seed_test_platform.py` — 5 test plans + 27 historical runs (Sprint 32–34 pass rate 70%→93% upward trend)

- [x] **TestRunView UX upgrades**
  **Step-level screenshots & logs**: fixed runner step-format conversion bug (transforms `steps` string array into `{description, expected_result}` object array before passing to executor); each step now records before/after screenshots, action sequence, and pass/fail reason;
  **Terminate**: red Terminate button in the header (visible only when running/pending); click opens a custom in-app confirmation modal (no native browser `confirm()`); `POST /api/test-runs/{id}/terminate` immediately sets DB status to `terminated` and adds the run ID to an in-memory signal set; runner thread checks the signal between cases and stops; the step-5 `UPDATE` adds a `status != 'terminated'` guard; terminated status shown as yellow ⊘ badge across all views;
  **Live refresh**: RefreshCw icon animates (`animate-spin`) while active; auto-polls every 3 s;
  **Back button**: navigates to `/test-platform/runs` instead of the old `/test-suites`;
  **Scroll fix**: root element changed to `h-full` (was `flex-1`) so flex height constraints propagate correctly, allowing the page to scroll normally even when step screenshots are expanded

- [ ] **Group Chat knowledge distillation**
  Offer a "Save to KB" option when deleting a Group Chat (currently only available for individual conversations)

- [ ] **Xray / Zephyr integration**
  Create test execution records directly from designed test cases, closing the loop from design to execution

### P4 — Long-term Directions

- [ ] **Multimodal support**
  Accept screenshots and UI design mockups to assist with UI test case design

- [ ] **Scheduled Agent tasks**
  Automatically run Exams and generate weekly reports on a schedule, without manual triggering

---

## V3 · Planned

> **Theme:** Evolve from a *tool platform* (human triggers, Agent responds) to *team infrastructure* (Agents proactively sense engineering events, surface in team communication, and are callable by external systems).

### Current Gaps

| Gap | Description |
|-----|-------------|
| Insufficient proactivity | Every action requires a human to initiate it — Agents cannot sense external events |
| Siloed operation | Agents work independently; Group Chat is ad-hoc discussion, not structured task handoff |
| Closed platform | All capabilities are locked inside the Web UI; CI/CD pipelines and external systems cannot call Agents |

---

### P0 — Event-Driven Activation

- [ ] **Webhook + event-driven triggers**
  Expose `POST /api/webhooks/{agent_id}` to receive external events; map events to prompt templates and wake the target Agent in the background; supported trigger sources: GitLab MR (opened / merged), Jira issue created/updated, scheduled cron.

  Example flows:
  ```
  GitLab MR opened
    → QA Agent: analyse diff → recommend regression scope → generate test plan
    → Dev Agent: code review checklist + boundary condition reminders

  Jira Critical Bug created
    → QA Agent: correlate historical cases → assess blast radius → draft reproduction steps

  Sprint end (cron)
    → QA Agent: generate weekly test coverage report + outstanding risk list
  ```

- [ ] **Slack / Feishu / DingTalk bidirectional integration**
  - **Outbound**: Agent execution results pushed as summary messages to a configured channel
  - **Inbound**: Mention the bot in a channel (`@agent "analyse SPPT-12345"`) → Agent executes and replies in thread

  This is the key step that transforms the platform from a single-user tool into team infrastructure.

---

### P1 — Structured Multi-Agent Pipelines

- [ ] **Pipeline (structured task flow)**
  A sequential chain of Agent nodes — each node has a defined input source and output target, replacing ad-hoc Group Chat for formal cross-role workflows.

  Example pipeline:
  ```
  PM Agent — analyse requirements doc
    ↓ output: feature breakdown + acceptance criteria
  QA Agent — receive breakdown → generate test cases + risks
    ↓ output: test plan
  Dev Agent — receive plan → code review checklist + edge-case reminders
    ↓ aggregated → publish to Confluence / create Jira sub-tasks
  ```

  Implementation: `pipelines` DB table; YAML-driven or visual node editor; each node's output is automatically injected as context for the next node.

- [ ] **CI/CD test execution trigger**
  The E2E engine is complete — this closes the last mile to CI. `POST /api/test-runs/trigger` accepts `{ suite_id, env, trigger: "ci" }` and returns run status and pass/fail for pipeline gating. Provides ready-to-use GitLab CI / GitHub Actions configuration snippets.

---

### P2 — Platform Openness

- [ ] **Agent API Gateway**
  Expose each Agent as a standalone REST API so any external tool can "hire" it:
  ```
  POST /api/agents/{id}/invoke
  { "message": "...", "context": { "jira_key": "SPPT-12345" } }
  → { "run_id": "...", "status": "running" }   # async
  GET  /api/agents/{id}/invoke/{run_id}
  → { "status": "done", "output": "..." }
  ```
  Enables Jenkins, GitHub Actions, internal scripts, and dashboards to call Agents directly.

- [ ] **Webhook outbound (result push)**
  When an Agent finishes a background task (webhook-triggered or scheduled), push the result to a pre-configured URL — enabling integration with any external system without polling.

---

### P3 — Intelligence Layer

- [ ] **Test knowledge graph**
  Connect the platform's scattered data into a queryable graph:
  ```
  Jira Feature ←→ Test Cases ←→ Test Runs ←→ Defects ←→ MR
  ```
  Unlocks high-value queries:
  - "What is the historical defect rate for this feature?"
  - "Which test cases have never failed — are they redundant?"
  - "This MR touches these features; what is the current test coverage?"

- [ ] **Multimodal input**
  Accept image uploads in chat: UI design mockups → auto-generate interface test cases; bug screenshots → Agent analyses and generates reproduction steps + links to similar historical defects. The foundational capability already exists in the E2E vision module.

- [ ] **Predictive risk scoring**
  Based on changed files in an MR, score each affected component's historical failure rate and surface a risk heatmap before the test run starts.

---

### Context Engineering Optimizations

> **Theme:** Reduce token costs, improve response latency, and make context usage smarter — without changing any user-visible behaviour.

- [x] **Anthropic Prompt Caching** *(P0 — shipped)*
  `_call_anthropic()` now passes `system` as a content-block list with `cache_control: {type: ephemeral}` applied to the system prompt block, and marks the end of the tool definition list with the same cache control.
  Anthropic uses content hash as the cache key — when a user modifies the system prompt (updates specialization, memory changes, etc.), the cache automatically invalidates and rebuilds on the very next call with no manual intervention required.
  Expected saving: **40–60 % reduction in input token cost** for same-agent multi-turn conversations (cache read costs ~1/10 of cache write).

- [ ] **Token-based context compression threshold** *(P1)*
  Replace the current `CONTEXT_COMPRESS_THRESHOLD = 40` (message count) with a token-estimated threshold (e.g. 60 000 tokens).
  A Jira result message can be 3 000 tokens; a simple acknowledgement is ~5 tokens — message count is a poor proxy for context pressure.
  Implementation: estimate per-message tokens as `len(str(content)) // 3`; trigger compression when the running total exceeds the threshold.

- [ ] **Role-based tool definition filtering** *(P1)*
  `get_tool_definitions()` currently returns all 16 tools unconditionally.
  Add a `ROLE_TOOLS` map (e.g. QA: [run_test, create_test_case, jira_get_issue, …], PM: [jira_create_issue, confluence_create_page, send_email, …]) and pass only the relevant subset before calling `call_llm`.
  Expected saving: **15–30 % of tool-definition tokens**; also reduces the likelihood of the model invoking irrelevant tools.

- [ ] **Tool result size cap + summarisation** *(P1)*
  `tools_node` currently injects `str(result)` verbatim — a Confluence page or Jira search result can exceed 10 000 characters.
  Add a `MAX_TOOL_RESULT_CHARS` limit (e.g. 6 000); results that exceed it are summarised by a lightweight LLM call before injection.
  Prevents a single tool call from dominating the context window across subsequent turns.

- [ ] **Fix streaming during tool-use turns** *(P2)*
  The current guard `use_stream = token_callback is not None and not tool_definitions` means streaming is *never* active, because tool definitions are always passed.
  Anthropic's API supports streaming alongside tool use (tool_use content blocks accumulate as deltas); update `_call_anthropic_stream()` to handle `input_json_delta` events so most conversation turns stream token-by-token even when tools are available.

- [ ] **Dynamic `max_tokens` budget** *(P2)*
  `max_tokens=4096` is applied to every call regardless of task complexity.
  Add a simple heuristic: tool-call turns → 1 024 (only JSON needed), short queries → 512, analysis tasks → 4 096. Alternatively, expose a per-agent `max_output_tokens` field in the DB.

---

### Priority Summary

| Priority | Direction | Rationale |
|----------|-----------|-----------|
| **P0** | Webhook + event-driven triggers | Closes the "insufficient proactivity" gap; immediately increases daily usage frequency |
| **P0** | Slack / Feishu integration | Puts Agents into the team's daily communication flow for maximum visibility |
| **P0** | Prompt Caching ✅ | Shipped; 40–60 % input token cost reduction for multi-turn conversations |
| **P1** | CI/CD test execution trigger | E2E engine is complete — last-mile wiring closes the loop |
| **P1** | Pipeline (structured task flow) | Formal upgrade from ad-hoc Group Chat; suitable for repeatable cross-role workflows |
| **P1** | Token-based compression + tool filtering | More precise context management; complements Prompt Caching |
| **P2** | Agent API Gateway | Lets external systems call Agents; opens the door to ecosystem integrations |
| **P2** | Streaming fix + dynamic max_tokens | UX improvement + output token cost reduction |
| **P3** | Test knowledge graph | High technical complexity; very high long-term analytical value |
| **P3** | Multimodal input | Builds on existing vision infrastructure; high value for UI-intensive QA scenarios |

---

*This file is updated in sync with each feature release.*
