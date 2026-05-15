# Digital Employee Platform · MVP

---

## 1. What It Is

A **multi-role digital employee platform** covering Dev, QA, Product, Operations, and Project Management — each employee specialises in a specific domain, operates under behavioural constraints, uses tools, and can be quantitatively assessed.

**Key Behaviors**
- Proactively clarifies ambiguous requirements rather than making assumptions
- Explicitly refuses unauthorised requests without seeking workarounds
- L2 tools require Mentor approval before execution (Human-in-the-Loop)
- Every tool call and L2 decision is automatically written to an audit trail
- Quantifiable assessment via an exam question bank, supporting iterative Mentor-led training

**Integrated Tool Capabilities**
- 🔍 **Local Knowledge Base**: Semantic search over local `.txt`/`.md`/`.pdf` files (RAG, incremental updates)
- 📖 **Confluence**: Real-time search + lazy-loaded local cache, with automatic supplementary queries when quality is insufficient
- 🎫 **Jira**: JQL search + Issue details; proactively checks historical bugs before designing test cases
- 🔀 **GitLab MR**: Reads PR diffs, analyses changes by module, recommends regression test scope
- 🧠 **Cross-Session Memory**: Automatically saves project context, recent work, and QA notes; picks up where it left off after a restart

---

## 2. Quick Start

### 1. Install Dependencies

```bash
cd app
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
cp .env.example .env
```

Edit `.env` and fill in the values as needed. **Simply change `LLM_PROVIDER` to switch models — no code changes required.**

```bash
# Using Claude (default)
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx
EMBEDDING_API_KEY=sk-xxxxxxxxxxxxxxxx   # Dedicated key for knowledge base vector search (OpenAI text-embedding-3-small)

# Using GPT-4
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx      # LLM inference key
# EMBEDDING_API_KEY=                    # Optional — falls back to OPENAI_API_KEY if not set
# MODEL_NAME=gpt-4o                     # Optional, default already set
# OPENAI_BASE_URL=https://...           # Optional: Azure OpenAI endpoint or other proxy
```

> **Note:** Knowledge base vector search always uses OpenAI `text-embedding-3-small`, regardless of `LLM_PROVIDER`. `EMBEDDING_API_KEY` is its dedicated config entry — set it separately when using Claude; when using GPT-4, it falls back to `OPENAI_API_KEY` automatically so no duplicate key is needed.

### 3. Initialise the Knowledge Base

```bash
python knowledge/setup_kb.py          # Incremental update (default)
python knowledge/setup_kb.py --full   # Force full rebuild
```

Chunks `.txt`, `.md`, and `.pdf` files in the `knowledge/` directory and writes them to the local ChromaDB vector store (`knowledge/.chroma/`).

**Incremental mode (default)**: Detects file changes via MD5 hash comparison.
- File unchanged → Skip, **no OpenAI API call**
- File modified → Delete old chunks, re-embed
- New file → Embed and write directly
- Deleted file → Remove corresponding chunks from the vector store

**`--full` mode**: Clears the entire vector store and rebuilds from scratch. Use when changing the embedding model or needing a complete reset.

> ⚠️ `setup_kb.py` **only manages local files**. Confluence pages cached via `save_confluence_page` are unaffected; they are listed separately on each run (marked with `~`) to confirm they are still present.

### 4. Start

```bash
# Step 1: Install dependencies (already included in requirements.txt)
pip install -r requirements.txt

# Step 2: Build the React frontend (run once, or whenever the frontend changes)
cd web/frontend
npm install
npm run build   # Output to web/frontend/dist/, served directly by FastAPI
cd ..

# Step 3: Start the web server
python web/server.py
# Visit http://localhost:8000
# API docs at http://localhost:8000/docs
```

**Frontend development mode** (hot reload, for local development):

```bash
# Terminal 1: Start the backend
python web/server.py

# Terminal 2: Start the frontend dev server
cd web/frontend
npm run dev   # → http://localhost:5173, proxied to :8000
```

---

## 3. Digital Employee Management Platform

The **Web Platform** addresses multi-person collaboration and team management, providing unified management for digital employees across roles — QA, Engineering, Product, Operations, and Project Management.

### Core Features

**Multi-Role Agent Management**
- Supports five roles — QA, Dev, PM, SRE, PJ — each Agent has its own Prompt, Jira project, and Confluence Space configuration
- Built-in quick-create presets per role (e.g. e-commerce promotional QA, backend developer, product manager)
- When multiple roles are active, the sidebar groups Agents by role with a distinct colour badge per role

**Role Prompt Template Management**
- System-level CRUD for per-role base prompt templates (QA / Dev / PM / SRE / PJ), editable from the **Role Prompts** page in the sidebar
- Newly onboarded Agents are automatically seeded from the matching role template (priority: DB custom template → built-in default → QA fallback)
- Save / Reset-to-default with an unsaved-changes indicator; template changes affect only future onboards, not existing Agents

**Prompt Manager (Per-Agent Versioned Prompts)**
- Each Agent has two independently versioned prompt layers, accessible via the **Prompt** button in the chat header:
  - **Base Prompt**: core identity, permission boundaries, behavioural rules, and tool-usage strategy
  - **Specialization**: domain-specific business rules, known risk areas, and conventions for that product line
- Every save creates a new immutable version; old versions can be activated (rolled back) at any time
- The version history sidebar shows creation time, change note, and — for Base Prompt versions — the exam pass rate achieved under that version
- Exam runs record which prompt version was active, enabling before/after comparison
- On first open, Base Prompt is seeded from the shared default template; Specialization is seeded from the value entered at Agent creation

**Real-Time Chat**
- **Token-level streaming**: final replies appear character-by-character (Anthropic `messages.stream` / OpenAI `stream=True`); tool-call phases continue to stream at node level; protocol: `message_start → token* → done`
- **Context window management**: before each LangGraph run, conversation history is loaded from DB; if message count ≥ `CONTEXT_COMPRESS_THRESHOLD` (default 40), the oldest messages are summarised with a single LLM call and replaced by one `[Earlier conversation summary]` message — the full history is preserved in DB
- Thinking process, tool calls, and tool results stream live; `asyncio.to_thread` + `asyncio.Queue` bridges synchronous LangGraph to the async event loop
- L2 tools (e.g. caching a Confluence page) display an inline approval card in chat; click Approve or Reject
- Each Agent maintains independent conversation history; conversations support inline rename (pencil icon on hover, Enter to confirm)

**Behavior Audit Log** *(see the [dedicated section](#6-behavior-audit-log) for full details)*
- Every tool call automatically written to the SQLite `audit_logs` table: execution duration, success/failure, full input args, 300-char result preview
- Every LLM call recorded as `event_type=llm_call`, capturing `input_tokens`, `output_tokens`, and wall-clock duration
- L2 approval decisions (approve/reject) written to the same table, forming a complete operation trail
- Sidebar **Audit Log** dashboard: stat cards (tool calls, success rate, avg duration, L2 decisions, **input tokens, output tokens, estimated cost**); daily trend chart; Top Tools ranking; paginated event table with a **Cost column** for LLM calls, expanding to show per-call token breakdown

**Group Chat (Multi-Agent Collaboration)**
- Create a group chat with 2+ Agents to collaborate on complex tickets spanning multiple business lines (e.g. Checkout QA + Promotion QA handling a cross-domain Jira ticket)
- Agents respond in sequence under a **Supervisor LLM** that routes to the most relevant domain expert; discussion terminates automatically when the Supervisor judges the question resolved or all Agents have had their say
- Real-time streaming: each Agent's thinking indicator and response stream live to the browser over WebSocket; Agents with nothing to contribute from their domain emit a subtle "nothing to add" indicator instead of a full reply
- Delete group chats from the sidebar; conversation history is persisted across sessions

**Exam Platform** *(see the [dedicated section](#7-exam-platform) for full details)*
- Browse all exam questions grouped by role (with colour-coded group headers); run any single question or the full suite against any Agent with one click
- **Select Questions** panel supports keyword search + role filter (QA / Dev / PM / SRE / PJ)
- Runs execute asynchronously (background thread); browser polls for completion — no blocking
- Auto-scoring (keyword hits) is displayed immediately; Mentor scoring form appears inline in the history table for exams that have evaluation criteria
- Score Trend chart tracks pass/fail history over time; Agent Comparison tab lets you select multiple Agents and view a grouped bar chart + latest-score comparison table

**Knowledge Base Management (Main + Branch Architecture)**
- **Main KB**: shared knowledge base for all Agents (team-wide standards, QA guidelines)
- **Branch KB**: private knowledge base per Agent (business-line docs, historical bugs)
- Upload documents via the Web UI; view real-time chunk counts per source
- Select valuable sources from a Branch and one-click Promote to Main KB
```
Document upload
  ↓
User selects: write to Main KB or Branch KB
  ↓
Agent searches both collections at inference time, merging results by relevance
  ↓
Mentor finds Branch content valuable for the team → select sources → Promote to Main
```

**Permission Configuration**
- Tool risk levels (L1/L2/L3) and per-ranking permission ceilings are configurable directly from the **Permissions** page in the sidebar — no code changes or server restarts required
- Default values are seeded from `config.py` on first startup; tools subsequently added to `TOOL_RISK_LEVEL` are automatically detected and registered on the next page load

**Conversation → Knowledge Base (Knowledge Distillation)**
- When deleting a conversation, a modal prompts: *Save to KB then delete / Delete without saving / Cancel*
- "Save to KB": a single LLM call distils the full transcript into a structured KB article (title + body), which is chunked, embedded, and written to the Agent's Branch KB (`qa_knowledge_{agent_id}`)
- The saved article is immediately searchable via `search_knowledge_base` in future conversations — valuable QA discussions are never lost
- Endpoint: `POST /conversations/{id}/save-to-kb`

### Architecture Diagram

```
Browser
  │  HTTP REST + WebSocket
  ▼
FastAPI (web/server.py :8000)
  │
  ├─ /api/agents/*                     → Agent CRUD (SQLite)
  ├─ /api/conversations/*              → Conversation management
  ├─ /api/conversations/{id}/ws        → WebSocket real-time inference (token streaming)
  ├─ /api/conversations/{id}/save-to-kb → Distil transcript → Branch KB
  ├─ /api/audit/*                      → Audit log queries, statistics, trace waterfall
  ├─ /api/exams/*                      → Exam CRUD + async run management + LLM-as-Judge
  ├─ /api/role-prompts/*               → System-level role prompt template CRUD
  ├─ /api/permissions/*                → Tool risk levels + per-ranking ceiling configuration
  ├─ /api/group-chats/*                → Group chat CRUD + WebSocket multi-agent orchestration
  ├─ /api/agents/{id}/knowledge/*      → Knowledge base management
  ├─ /api/test-suites/*                → Test suite + case CRUD, Markdown/XMind export
  ├─ /api/test-runs/*                  → E2E run lifecycle, terminate, analytics, screenshots
  ├─ /api/test-plans/*                 → Test plan CRUD + parallel execute
  └─ /api/browser-skills/*             → Environment + extra skill management
         │
         ▼
   LangGraph Agent (each agent_id has an independently compiled graph)
         │
    ┌────┴────┐
    │         │
  Main KB   Branch KB
  (shared)  (per-agent)
  ChromaDB  ChromaDB
```

---

## 4. Agent Execution Flow

```
User input
    ↓
[qa_agent] Claude inference
    ↓ Any tool calls?
    ├─ No → Output conclusion, end
    │
    ├─ L1 tools (read_doc / search_kb)
    │    → [tools] Auto-execute → Return results → Continue inference
    │
    └─ L2 tools (create_defect)
         → [human_review] Pause, display pending approval
         → Mentor inputs y/n
             ├─ y → Execute tool → Continue inference
             └─ n → Cancel, continue inference
```

### System Prompt Construction

The system prompt is **not stored anywhere** — it is assembled fresh on every LLM call and discarded afterwards. What is persisted in the database is the raw material (versioned prompt content and Agent metadata), never the assembled string.

```
DB (two tables)
  ┌─ prompt_versions (per-agent versioned, primary source)
  │    ├─ type="base",           is_active=True  → base_prompt content
  │    └─ type="specialization", is_active=True  → specialization content
  │
  └─ qa_agents (metadata + fallbacks)
       ├─ ranking        = "Senior"   ← formats {ranking_description} placeholder
       └─ specialization = "..."      ← fallback when no active spec version exists

        │  Active versions read at WebSocket connect; LangGraph config built
        ▼

  lg_config = {
    "configurable": {
      "agent_id":       "<uuid>",
      "ranking":        "Senior",
      "base_prompt":    "<active base version content>",       ← from prompt_versions
      "specialization": "<active spec version content>",       ← from prompt_versions, fallback to agent.specialization
    }
  }

        │  Assembled fresh inside qa_agent_node on every LLM call
        ▼

  # 1. Semantic memory retrieval (latest user message as query)
  memory_context = load_memory_context(agent_id, query=<latest user message>)

  # 2. Assemble System Prompt
  build_system_prompt(
    base_prompt    = "<active version>"   → if empty, falls back to role default template (ROLE_PROMPTS[agent.role])
                                            then formats with {agent_id} / {agent_version} / {ranking_description}
    specialization = "..."               → appended as 【Domain Specialization】 block (if non-empty)
    memory_context = "..."               → appended cross-session memory fragments (if non-empty)
  )

        │
        ▼

  Final System Prompt structure:
  ┌──────────────────────────────────────────┐
  │  base prompt (formatted)                  │  ← identity / permission boundaries / behavioural rules / tool strategy
  ├──────────────────────────────────────────┤
  │  ═══...═══                               │
  │  【Domain Specialization】 (optional)    │  ← domain-specific rules, known risks, conventions
  │  ═══...═══                               │
  │  {specialization content}                │
  ├──────────────────────────────────────────┤
  │  {memory_context} (optional)             │  ← semantically retrieved cross-session memory fragments
  └──────────────────────────────────────────┘

  call_llm(system_prompt=<assembled string>, ...)
  # assembled per call, not persisted
```

**base_prompt fallback chain (`agent/prompts.py`):**

```
prompt_versions.type='base', is_active=True
  │ if empty
  ▼
role_prompt_templates[agent.role]  (DB-level customisable system template)
  │ if empty
  ▼
ROLE_PROMPTS[agent.role]  (built-in code defaults, role-specific: QA / Dev / PM / SRE / PJ)
```

Ranking → identity description mapping (`agent/prompts.py`):

| Ranking | Identity in prompt |
|---------|--------------------|
| Intern  | newly hired, intern-level |
| Junior  | junior-level |
| Senior  | senior-level |
| Lead    | lead-level |

**Key benefit:** activating a new version in the Prompt Manager takes effect on the very next message — no restart, no data migration. `base_prompt` and `specialization` are versioned independently and can be rolled back separately.

**Permission levels** (defaults defined in `TOOL_RISK_LEVEL` in `config.py`; adjustable at runtime from the **Permissions** page in the sidebar):

| Level | Meaning | Current Tools |
|-------|---------|---------------|
| L1 | Auto-execute, no approval needed | `read_requirement_doc`, `search_knowledge_base`, `search_confluence`, `search_jira`, `get_jira_issue`, `get_gitlab_mr_diff`, `write_output_file`, `save_to_memory` |
| L2 | Requires Mentor confirmation | `create_defect_mock`, `save_confluence_page` |
| L3 | Output plan only, no execution (planned) | Future: trigger CI, change config |

---

## 5. Knowledge Retrieval and Memory System

The cross-session memory system uses ChromaDB vector search to retrieve only the most relevant memory fragments for each conversation, rather than injecting the entire memory JSON into every prompt.

### Workflow

```
Agent receives user message
  ↓
qa_agent_node extracts the last user message as the query
  ↓
Calls load_memory_context(agent_id, query=<message content>)
  ↓
Semantic search: ChromaDB cosine similarity over all saved memory entries
  ├─ Hits found → return top-5 fragments with relevance scores
  ├─ Empty index → rebuild index from JSON, retry search
  └─ Any exception → fall back to full JSON context (graceful degradation)
  ↓
Relevant memory fragments injected into the system prompt
```

Memory is automatically indexed on save: `save_to_memory` calls `save_to_index` (best-effort, never raises). The index lives in a ChromaDB collection named `agent_memory_{agent_id}`, embedded with OpenAI `text-embedding-3-small`.

### Three-Layer Fallback

1. **Semantic hit**: return top-5 fragments ranked by cosine similarity
2. **Empty index**: rebuild from the full JSON memory file, then retry — handles first-time use and pre-existing Agents
3. **Any exception** (ChromaDB unavailable, no API key, etc.): return the full JSON context unchanged — zero regression for existing deployments

### Key Files

- `tools/semantic_memory.py` — `save_to_index`, `delete_from_index`, `search`, `rebuild_index`
- `tools/memory_manager.py` — `load_memory_context` with `query` parameter; `save_to_memory` with semantic mirror
- `agent/agent.py` — extracts the last `HumanMessage` content as the query before calling `load_memory_context`

### Persistent Storage and Memory Categories

```
Each startup
  ↓
Read memory/agent_memory.json → inject into System Prompt
  ↓
Agent calls save_to_memory during the conversation to save valuable information
  ↓
Next startup auto-loads the file, picking up where it left off
```

The **welcome panel** shows memory status on startup:
- `🧠 Memory loaded from previous sessions` — historical memory found
- `🆕 No previous memory (first session)` — first run

### Memory Categories

| Category | What It Stores | Retention |
|----------|----------------|-----------|
| `user_preferences` | Default project, team, output style | Indefinite |
| `active_context` | Current Sprint, focused feature modules | Indefinite |
| `qa_notes` | Risk patterns, team conventions, known flaky areas | Indefinite |
| `recent_work` | Analysed tickets, generated test cases, reviewed MRs | Rolling: last 20 entries |
| `session_summary` | Brief summary of each session | Rolling: last 5 entries |

### Agent Memory Behavior

The Agent **proactively** calls `save_to_memory` at these moments — no prompting needed:
- You mention a default project or team → saved to `user_preferences`
- Completing analysis of a Jira ticket or MR → key findings saved to `recent_work`
- Discovering a risk pattern or team convention → saved to `qa_notes`
- End of conversation → brief summary saved to `session_summary`

### Memory File

Memory is stored in `memory/agent_memory.json` (gitignored — not committed to the repo). You can view or edit it directly:

```json
{
  "user_preferences": {
    "default_jira_project": {"value": "SPPT", "updated": "2026-04-21"}
  },
  "active_context": {
    "current_sprint": {"value": "Sprint 42, focus: voucher redemption", "updated": "2026-04-21"}
  },
  "qa_notes": {
    "voucher_risk_areas": {"value": "DB migration + idempotency are historically high-risk", "updated": "2026-04-21"}
  },
  "recent_work": [
    {"date": "2026-04-21", "label": "SPPT-97814 analysis", "content": "Voucher MR, DB migration risk flagged"}
  ],
  "session_summaries": [
    {"date": "2026-04-21", "content": "Analysed SPPT-97814 MR, recommended regression on DB + API layers"}
  ]
}
```

### Knowledge Base Integration

Using Confluence as an example. This framework implements a **real-time search + lazy-loaded local cache** hybrid RAG architecture, enabling the Agent to reference the latest internal documentation during inference.

### Architecture

```
User question
   │
   ▼
Agent determines it needs to retrieve information
   │
   ├─► search_knowledge_base (local ChromaDB)
   │        │
   │        └─► Agent evaluates result quality — not "present or not", but "good enough or not"
   │                  ✅ High relevance and complete content → use directly, skip Confluence
   │                  ⚠️ Proceed to query Confluence if any condition is met:
   │                       - Top relevance score < 75%
   │                       - Content covers only part of the question
   │                       - Content appears outdated (mentions old versions / deprecated rules)
   │                       - No local results at all
   │
   ├─► search_confluence (Confluence REST API, live)
   │        Returns: title / summary / link / page_id
   │        Answers using combined local + Confluence content
   │        │
   │        └─► Agent decides: does this page have sustained value for future tasks?
   │                  Yes → suggest Mentor run save_confluence_page
   │                  No  → use summary inline, do not persist
   │
   └─► save_confluence_page (L2, requires Mentor confirmation)
            Fetch full content → strip HTML → chunk → embed → write to local ChromaDB
            The next similar question goes straight to local — no Confluence call needed
```

> **Design principle**: The trigger for retrieval is **quality**, not **presence**. Even when local results exist, insufficient relevance prompts a Confluence follow-up rather than settling for low-quality content. `search_knowledge_base` results are annotated with quality hints (`✅ Good relevance` / `⚠️ Recommend supplementary query`) to help the Agent decide.

**Tool roles:**

| Tool | Level | Function | When to Use |
|------|-------|----------|-------------|
| `search_confluence` | L1 (autonomous) | Real-time Confluence search | Local KB has no answer, or content may be stale |
| `save_confluence_page` | L2 (requires confirmation) | Cache page to local vector store | Page has lasting value for current and future tasks |

### Usage Example

```
You: Design test cases for scenarios where discount coupons and discount codes stack

Agent: (queries local KB — no match)
       calls search_confluence("coupon stacking rules space=QA")
       finds 3 relevant pages: "Promotion Engine Design Spec", "Coupon Stacking Rules v2" …

       [Test cases generated based on Confluence documentation]
       TC-001 Discount coupon + discount code used simultaneously …
       …

       💡 "Coupon Stacking Rules v2" (page_id: 98765) contains valuable content.
          Recommend Mentor confirm caching it to the local knowledge base.
```

### Notes

- **L2 permission** — triggers Mentor confirmation before execution
- Saving the same page multiple times automatically **updates** it (old chunks deleted, new chunks written) — no manual cleanup needed
- Cached pages appear in `search_knowledge_base` results with source `confluence:<page_title>`
- Prioritise caching **infrequently-changing, frequently-referenced** specification docs; avoid caching high-velocity documents (e.g. daily test summaries)

---

## 6. Behavior Audit Log

Every tool invocation, every LLM call, and every Mentor L2 approve/reject decision is automatically written to a persistent audit trail. No extra configuration is needed — it is always on. The QA Lead can use this to review Agent activity, catch reliability issues, and report both ROI and API spend to management.

### What Gets Recorded

The `event_type` field determines the meaning of each entry — three types exist:

| `event_type` | When emitted | Key payload |
|---|---|---|
| `tool_call` | After each tool execution | tool name, args, result preview, duration, success flag |
| `llm_call` | After each LLM API response | model name, input/output token counts, duration |
| `l2_decision` | When Mentor approves or rejects | `l2_approved` boolean |

Shared base fields across all types:

| Field | Description |
|-------|-------------|
| `agent_id` / `agent_name` | Which Agent made the call |
| `conversation_id` | Web conversation context |
| `trace_id` | UUID shared by all events within a single user turn — enables end-to-end tracing |
| `tool_name` | Tool name; for `llm_call` events this stores the model name (e.g. `claude-sonnet-4-6`) |
| `tool_args` | Full input arguments (serialised JSON) |
| `result_preview` | First 300 characters of the output |
| `duration_ms` | Wall-clock execution time in milliseconds |
| `success` | Whether the call completed without error |
| `error_msg` | Error detail when `success = false` |
| `input_tokens` | LLM input token count (populated for `llm_call` events only) |
| `output_tokens` | LLM output token count (populated for `llm_call` events only) |
| `l2_approved` | `true` / `false` (populated for `l2_decision` events only) |
| `created_at` | UTC timestamp |

### Token Billing

After each LLM call, `agent.py` reads `input_tokens` / `output_tokens` from the response object and writes a `llm_call` audit entry via `log_llm_call()`. The summary endpoint `/api/audit/summary` aggregates all `llm_call` events in the requested time window and estimates cost using:

```
estimated_cost_usd = (total_input_tokens  / 1_000_000) × $3.00
                   + (total_output_tokens / 1_000_000) × $15.00
```

> Pricing is based on Claude Sonnet API rates ($3 / $15 per million tokens for input / output). If you switch models, update the coefficients in `audit.py` accordingly.

The `tokens` block in the summary response:

```json
{
  "tokens": {
    "input":  12400,
    "output": 3100,
    "estimated_cost_usd": 0.0838
  }
}
```

Per-turn token breakdowns are also available via `GET /api/audit/trace/{trace_id}`, which returns `total_input_tokens` and `total_output_tokens` across all events for that conversation turn.

### Web Dashboard (AuditPanel)

Click **Audit Log** in the sidebar to open the dashboard. It calls `/api/audit/summary` and `/api/audit` on load and whenever filters change.

**Stat cards (first row):**
- **Tool Calls** — total invocations in the selected period
- **Success Rate** — green if ≥ 95%, yellow otherwise
- **Avg Duration** — mean latency per tool call
- **L2 Decisions** — approved ✅ vs. rejected ❌ counts side by side

**Token usage cards (second row — shown when `llm_call` data exists):**
- **Input Tokens** — cumulative input tokens for the period
- **Output Tokens** — cumulative output tokens for the period
- **Est. Cost (USD)** — estimated spend using the formula above (4 decimal places)

**Trend chart** — daily bar chart (recharts `BarChart`) showing tool call volume over the last N days.

**Top Tools** — horizontal bar per tool showing relative call share, absolute count, avg latency, and error count if non-zero.

**Event table** — paginated at 50 rows per page:
- Columns: Time, Agent, Tool, Type (colour-coded badge), Duration, Status/Cost
- `llm_call` rows show a per-call estimated cost in the Cost column (yellow text)
- Click any row to expand an inline detail drawer with full arguments, result preview, and for `llm_call` rows, the input/output token breakdown
- Inline filters: tool name text input, event type dropdown (includes `llm_call`); apply with Enter or blur

**Filter bar (header):** Agent dropdown (all Agents or one), time window selector (1d / 7d / 14d / 30d / 90d), manual refresh button.

---

## 7. Exam Platform

The Exam Platform closes the **train → evaluate → adjust** loop entirely inside the web UI — no more manual copy-paste.

### How It Works

```
Mentor opens /exams in browser
  ↓
Selects an Agent + exam question (or "All Questions") → clicks Run
  ↓
Server creates an ExamRun row with status="running", returns the run ID immediately
  ↓
Background thread: builds a LangGraph Agent with the Agent's specialization,
  invokes it with the exam prompt, auto-scores keyword hits, writes results
  ↓
Browser polls every 3 s until status → "done"
  ↓
Mentor reviews the auto-score + output; fills in Mentor scoring sliders → Submit
  ↓
Server recalculates total_score and passed, row updated
```

### Web UI Features

**Header bar**
- Agent dropdown (select one to run, or "All Agents" to view full history)
- Exam question dropdown (specific file or "All Questions")
- **Run** button (disabled until an Agent is selected)
- Refresh icon to reload history

**Running indicator strip** — shows a spinner per in-flight run with Agent name and exam ID; disappears when all finish.

**History tab**
- Summary stat cards: Total Runs, Pass Rate, Avg Score
- **Score Trend line chart**: x = date, one line per exam question, y = total score; tracks improvement over time
- **Run history table**: Time / Agent / Exam / Auto Score / Total Score / Elapsed / Result
  - Click any row to expand a detail drawer showing:
    - Score breakdown (auto score × weight + Mentor score × weight)
    - Keyword check (missed keywords highlighted in red)
    - Full Agent output (scrollable, up to 12 lines visible)
    - **Mentor scoring form**: one slider per criterion (0.0–1.0); Submit sends scores and redraws the row with the final result

**Compare tab**
- Agent selection panel (toggle buttons with colour dots)
- **Grouped bar chart**: x = exam ID, bars grouped by Agent, y = latest total score
- **Comparison table**: one row per exam, columns per selected Agent, colour-coded scores

### Scoring Model

Scoring runs in two layers, implemented in `eval/judge.py`:

**Layer 1 — Rule Checks (`evaluate_rules`)**

Pure string matching, no LLM involved. Each `rules` entry in the exam YAML is evaluated independently (currently supports `contains_any`), producing a pass/fail list that feeds `auto_score`:

```
auto_score = (rules passed / total rules) × 100
```

**Layer 2 — LLM-as-Judge (`evaluate_criteria`)**

When the exam YAML defines `criteria`, the system automatically calls an LLM to score each rubric criterion — no human intervention needed.

```
Judge system prompt:  expert QA examiner role, rigorous but fair
User prompt:          exam scenario + Agent input + full Agent output + criteria (with weights)
LLM returns JSON:
  {
    "<criterion_id>": {
      "score":     0–3,          # 0 = no match  /  3 = fully met
      "evidence":  "direct quote from Agent output (≤150 chars)",
      "reasoning": "explanation for the score (≤200 chars)"
    }
  }
```

`judge_to_score` converts per-criterion scores into a weighted 0–100 value:

```
judge_score = Σ (score_i / 3 × 100 × weight_i)   (weights are normalised)
```

**Final roll-up**

```
total_score = auto_score × auto_weight + judge_score × mentor_weight
passed      = total_score ≥ pass_threshold
```

Three modes are selected automatically based on the exam YAML:

| Exam configuration | Behaviour |
|---|---|
| Has `criteria` | LLM-as-Judge runs automatically; `passed` is resolved immediately |
| No `criteria`, has `mentor_criteria` | Judge skipped; `passed` stays `null` until Mentor submits scores manually |
| Neither | Pure rule-based auto-scoring; `mentor_weight` is folded into `auto_weight` |

Mentor can still override Judge scores via sliders after the fact; the server recalculates `total_score` on submission. Weights and threshold come from the YAML definition (`auto_score_weight` default 0.6, `mentor_score_weight` default 0.4, `pass_threshold` default 70).

### Prompt Auto-Improvement (Feedback Loop)

When an exam run fails, the platform can automatically analyse the failure and propose targeted prompt improvements — closing the train → evaluate → adjust loop with a single click.

```
Exam run fails (keyword misses, low Judge scores)
  ↓
Mentor clicks "Suggest Improvements" in the ExamPanel
  ↓
Server calls eval/suggester.py:
  - Loads the active prompt version + exam YAML
  - Sends missed keywords and Judge score breakdowns to a second LLM
  - Receives: { diagnosis, suggestions[{point, rationale, patch}], patched_prompt }
  ↓
SuggestionPanel renders the diagnosis + collapsible suggestion cards (with patch text)
  ↓
Mentor clicks "Apply to New Prompt Version"
  ↓
Server creates a new PromptVersion from patched_prompt (old version deactivated)
  ↓
Re-run the exam against the new version to verify improvement
```

---

## 8. GitLab MR Code Change Awareness

One of the most time-consuming parts of daily QA work: **reading requirements and code diffs, then deciding which regression tests to run**. The Agent can now automate this analysis.

### Workflow

```
You provide a Jira ticket (e.g. SPPT-12345)
  ↓
get_jira_issue reads the ticket details
  ↓
Agent extracts the GitLab MR URL from the description / comments
  ↓
get_gitlab_mr_diff fetches the complete diff
  ↓
Changed files are categorised by module (API / DB / Messaging / Frontend / …)
  ↓
Structured regression test recommendations are produced
```

### Output Example

```
📁 API Layer
  [MODIFIED] src/controller/CartController.java  (+45 -12)
  [MODIFIED] src/service/CartService.java         (+30 -8)

📁 Database Migration
  [ADDED]    db/migration/V20240420__add_cart_column.sql  (+15 -0)

── Regression Scope Recommendations ──
  • API Layer:
      - API integration test
      - Contract test
  • Database Migration:          ← High risk, test first
      - DB migration test
      - Data integrity check
```

### Usage Example

```
You: Analyse ticket SPPT-12345 — what regression tests should I run?

Agent: (calls get_jira_issue → finds MR URL → calls get_gitlab_mr_diff)

       This MR modifies 8 files across the following modules:
       - API Layer: CartController, CartService (interface logic changes)
       - Database Migration: new cart table column (high risk)
       - Messaging: CartEventProducer (async notifications)

       Recommended regression scope:
       1. Full add/modify/remove cart flow (API integration test)
       2. Pre- and post-migration data consistency verification
       3. Cart success event delivery verification (message queue integration test)
       4. Related E2E: checkout upstream chain
```

---

## 9. E2E Test Execution (Playwright + LLM Vision)

The platform includes a UI-layer automated test execution engine that drives a real browser using Playwright and uses Claude's vision capability to interpret screenshots and decide actions — **no CSS selectors or XPath required**.

### How It Works

Each test case step is executed in a loop:

```
Screenshot → decide_actions(screenshot, step description)
           → execute actions (click, type, scroll, …)
           → screenshot → verify_result(screenshot, expected result)
           → pass / fail + save evidence screenshots
```

`decide_actions` and `verify_result` both call the Anthropic API with the screenshot as a base64 image block. Claude identifies elements visually and returns structured JSON (`{"type":"click","x":…,"y":…}`). The Agent decomposes multi-action steps autonomously — no rigid one-action-per-step constraint.

Execution runs in a background thread on the backend; the frontend polls for progress every 3 s. Screenshots are saved to `output/test_runs/<run_id>/` and served via a dedicated API endpoint.

### Browser Skills

Context required for test execution (environment URL, credentials, test data, execution hints) is stored as **Browser Skills** in the DB — not hardcoded in the UI. Two types:

- **Environment Skills** — one per target environment; must contain a `base_url:` line; provides credentials, test data, and environment-specific notes. Exactly one is selected per run.
- **Extra Skills** — reusable execution hints (e.g. "Login Flow", "Popup Handling", "Checkout Patterns"). Multi-selectable per run.

All selected skills are concatenated and injected as a context block into every `decide_actions` and `verify_result` prompt call, ensuring Claude always has the correct credentials and environment context.

Manage skills at **Settings → Browser Skills** (`/browser-skills`): two-tab layout (Environment / Extra), left list + right monospace editor, inline save/delete.

Example environment skill:

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
  - CAPTCHA is disabled in staging
  - Payment gateway is mocked
```

### Starting a Run

In **Test Suites**, select a suite and click **▶ Run**. The modal prompts for:
- **Run name** (e.g. "Sprint 16 regression")
- **Environment skill** (required — provides base URL + credentials)
- **Extra skills** (optional multi-select)

The run starts immediately in the background and navigates to **TestRunView**.

### Android E2E Test Execution (ADB + LLM Vision)

In addition to web browsers, the platform supports UI E2E testing on Android devices and emulators via **ADB (Android Debug Bridge)** — also powered by Claude's vision, with no Appium or XPath required.

The execution flow mirrors the web flow:

```
ADB screenshot → decide_actions(screenshot, step description, resolution)
              → execute ADB actions (tap / swipe / type / keyevent / launch)
              → screenshot → verify_result()
              → pass / fail + save screenshots
```

Because Android devices vary in resolution, screen dimensions are queried dynamically via `adb shell wm size` before each test case and injected into the LLM prompt, ensuring accurate coordinate calculations.

**Example Android environment skill:**

```markdown
# Environment: Example Android Staging

device_serial: emulator-5554
app_package: com.example.app
app_main_activity: com.example.app.MainActivity

credentials:
  username: testuser@example.com
  password: Test1234
```

Select the platform (`🌐 Web` / `🤖 Android`) in the Start Run modal; the remaining flow (skill selection, viewing progress in TestRunView) is identical to the web flow.

**Prerequisites:** `adb` must be in `PATH` (install via Android Studio SDK or `brew install android-commandlinetools`) and a connected device or emulator must be visible (`adb devices`).
