"""
Unified entry point for the tools layer.

All tools are registered here. agent.py retrieves the tool list via get_tools() and get_tool_definitions(),
and executes tools via execute_tool().

Steps to add a new tool:
  1. Implement the function in the corresponding module
  2. Register it in _TOOL_REGISTRY
  3. Declare the risk level in TOOL_RISK_LEVEL in config.py
"""
from tools.doc_reader import read_requirement_doc
from tools.knowledge_search import search_knowledge_base
from tools.defect_mock import create_defect_mock
from tools.output_writer import write_output_file
from tools.confluence_search import search_confluence
from tools.confluence_save import save_confluence_page
from tools.jira_search import search_jira
from tools.jira_issue import get_jira_issue
try:
    from tools.jira_create_issue import create_jira_issue
except ImportError:
    create_jira_issue = None  # type: ignore
from tools.gitlab_mr import get_gitlab_mr_diff
from tools.memory_manager import save_to_memory
try:
    from tools.test_suite_writer import save_test_suite
except ImportError:
    save_test_suite = None  # type: ignore
try:
    from tools.propose_exam_case import propose_exam_case
except ImportError:
    propose_exam_case = None  # type: ignore

# ── Tool Registry ──────────────────────────────────────────────────────────────
_TOOL_REGISTRY_RAW: dict[str, callable] = {
    "read_requirement_doc":  read_requirement_doc,
    "search_knowledge_base": search_knowledge_base,
    "create_defect_mock":    create_defect_mock,
    "write_output_file":     write_output_file,
    "search_confluence":     search_confluence,
    "save_confluence_page":  save_confluence_page,
    "search_jira":           search_jira,
    "get_jira_issue":        get_jira_issue,
    "create_jira_issue":     create_jira_issue,
    "get_gitlab_mr_diff":    get_gitlab_mr_diff,
    "save_to_memory":        save_to_memory,
    "save_test_suite":       save_test_suite,
    "propose_exam_case":     propose_exam_case,
}
# Filter out tools that failed to import (e.g. missing runtime deps in test env)
_TOOL_REGISTRY: dict[str, callable] = {k: v for k, v in _TOOL_REGISTRY_RAW.items() if v is not None}

# ── Tool Definitions in Anthropic tool_use Format ─────────────────────────────────────────
_TOOL_DEFINITIONS = [
    {
        "name": "read_requirement_doc",
        "description": "Read requirement documents from the specified path and return the content. Used to understand functional requirements for designing test cases.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "File path to the requirement document (relative or absolute path)",
                }
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "search_knowledge_base",
        "description": (
            "Semantically search the knowledge base for relevant content, including: test specifications, "
            "promotion rules manual, historical defect cases, idempotent design specifications, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keywords, e.g. 'discount coupon stacking rules' or 'idempotent duplicate submission'",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "write_output_file",
        "description": (
            "Save generated content to the local output/ directory. "
            "When test cases or risk lists exceed 3 items, use file_type='csv'. "
            "content must be pure CSV format text: first row is column headers, then each row is one record separated by commas. "
            "Example: 'Case ID,Title,Scenario Type\\nTC-001,Normal Add to Cart,Normal Flow\\nTC-002,Zero Stock,Boundary Case'. "
            "Note: Do not pass JSON arrays, pass CSV format text directly. "
            "For other content (analysis reports, documentation) use file_type='md'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": (
                        "md/txt: Complete text content; "
                        "csv: Pure CSV format text, first row is column headers, each subsequent row is one record separated by commas. "
                        "Do not pass JSON arrays. Example: 'Case ID,Title\\nTC-001,Normal Add to Cart'"
                    ),
                },
                "filename": {
                    "type": "string",
                    "description": "Filename (without extension), e.g. add_to_cart_testcases. If not provided, auto-generates timestamp filename",
                },
                "file_type": {
                    "type": "string",
                    "enum": ["md", "txt", "csv"],
                    "description": "File format: csv (test cases/risk lists) / md (report documents) / txt",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "create_defect_mock",
        "description": (
            "(L2, requires Mentor confirmation) Create a defect record in the sandbox defect management system. "
            "Only for testing/training environments, will not affect production data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title":       {"type": "string", "description": "Defect title"},
                "description": {"type": "string", "description": "Defect description"},
                "severity":    {
                    "type": "string",
                    "enum": ["P0", "P1", "P2", "P3"],
                    "description": "Severity level",
                },
                "module":      {"type": "string", "description": "Module name, e.g. 'Promotion Engine'"},
            },
            "required": ["title", "description", "severity"],
        },
    },
    {
        "name": "search_confluence",
        "description": (
            "Search for relevant pages in the company Confluence knowledge base in real-time. "
            "Applicable when: local knowledge base lacks answers, need latest rule documents, or searching specific Space content. "
            "Supports natural language queries (e.g. 'discount coupon stacking rules') or CQL syntax (e.g. text~\"idempotent\" AND space=\"QA\"). "
            "Returns page title, excerpt, link, and page_id; "
            "if a page is valuable for the current task, can call save_confluence_page to cache locally."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search keywords or CQL statement. "
                        "Natural language example: 'add to cart interface idempotent design'; "
                        "CQL example: 'text~\"discount\" AND space=\"QA\"'"
                    ),
                },
                "space_key": {
                    "type": "string",
                    "description": "Optional. Limit search scope to specified Space, e.g. \"QA\", \"ARCH\", \"BE\"",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return, default 5, max 20",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "save_confluence_page",
        "description": (
            "(L2, requires Mentor confirmation) Cache the specified Confluence page to the local knowledge base. "
            "Process: fetch complete content → clean HTML → chunk → embedding → write to local ChromaDB. "
            "After caching, the page content can be directly retrieved via search_knowledge_base without accessing Confluence again. "
            "If the same page is already cached, it will automatically update (delete old chunks and rewrite). "
            "page_id is obtained from the search_confluence results."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "page_id": {
                    "type": "string",
                    "description": "Confluence page ID (numeric string), obtained from search_confluence results",
                },
            },
            "required": ["page_id"],
        },
    },
    {
        "name": "search_jira",
        "description": (
            "Search Jira issues using JQL (Jira Query Language). "
            "Use when: (1) designing test cases — find known bugs or related stories for a feature; "
            "(2) determining regression scope — look up recently fixed issues in a component; "
            "(3) analyzing defects — find similar historical issues; "
            "(4) user mentions a project/component and wants to know its issue status. "
            "Supports natural-language keywords (auto-wrapped as JQL) or raw JQL expressions. "
            "Returns: issue key, type, status, priority, summary, assignee, last-updated date, link. "
            "To view full description and comments for a specific issue, use get_jira_issue."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Natural language keywords or JQL expression. "
                        "Natural language example: 'add to cart payment timeout bug' "
                        "(auto-wrapped as: text ~ \"...\" ORDER BY updated DESC). "
                        "JQL example: 'project=QA AND status=\"In Progress\" AND priority=High'. "
                        "JQL example: 'project=SHOP AND component=\"Checkout\" AND fixVersion=\"2.4.0\"'."
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return, default 10, max 50",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_jira_issue",
        "description": (
            "Fetch the full detail of a specific Jira issue by its key. "
            "Use when: (1) user mentions a specific issue key (e.g. QA-1234, SHOP-5678); "
            "(2) search_jira returned a relevant issue and you need its full description or acceptance criteria; "
            "(3) need to read comments to understand a defect's root cause or fix context. "
            "Returns: type, status, priority, assignee, reporter, description, latest 5 comments."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_key": {
                    "type": "string",
                    "description": "Jira issue key, e.g. 'QA-1234' or 'SHOP-5678'",
                },
            },
            "required": ["issue_key"],
        },
    },
    {
        "name": "create_jira_issue",
        "description": (
            "(L2, requires Mentor confirmation) Create a real Jira issue via REST API v2. "
            "Use when: (1) QA agent discovers a defect during testing and wants to log it directly to Jira; "
            "(2) need to report test failures with structured steps, expected vs actual results. "
            "Supports: summary, description, issue type (Bug/Task/Story/Improvement), priority, "
            "labels, components, affected version, and detailed reproduction steps. "
            "Returns: issue key, type, priority, and direct link to the created issue."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Issue title (required). E.g., 'Checkout button unresponsive on mobile'",
                },
                "description": {
                    "type": "string",
                    "description": "Issue description (required). E.g., 'Users cannot complete checkout on iOS 15 devices'",
                },
                "issue_type": {
                    "type": "string",
                    "enum": ["Bug", "Task", "Story", "Improvement"],
                    "description": "Issue type. Defaults to 'Bug'",
                },
                "priority": {
                    "type": "string",
                    "enum": ["Blocker", "Critical", "Major", "Medium", "Minor"],
                    "description": "Issue priority. Defaults to 'Medium'",
                },
                "project_key": {
                    "type": "string",
                    "description": (
                        "Jira project key, e.g. 'SHOP', 'QA'. "
                        "Falls back to DEFAULT_JIRA_PROJECT if not provided."
                    ),
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Labels for categorization, e.g. ['regression', 'mobile', 'payment']",
                },
                "components": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Component names, e.g. ['Checkout', 'Payment Gateway']",
                },
                "affected_version": {
                    "type": "string",
                    "description": "Version affected by this issue, e.g. '2.3.0' or '2.3.0-beta'",
                },
                "steps_to_reproduce": {
                    "type": "string",
                    "description": (
                        "Detailed steps to reproduce the issue. "
                        "Newline-separated list, e.g. '1. Go to Checkout\\n2. Try to click button'"
                    ),
                },
                "expected_result": {
                    "type": "string",
                    "description": "What should happen (for bug reports)",
                },
                "actual_result": {
                    "type": "string",
                    "description": "What actually happened (for bug reports)",
                },
            },
            "required": ["summary", "description"],
        },
    },
    {
        "name": "save_to_memory",
        "description": (
            "Save a fact to persistent memory so it is available in future sessions. "
            "Call this proactively whenever you learn something worth remembering across sessions. "
            "Good candidates: (1) user mentions their default project / team / sprint → save to 'user_preferences'; "
            "(2) you analyze a ticket or MR → save key findings to 'recent_work'; "
            "(3) you identify a risk pattern or team convention → save to 'notes'; "
            "(4) end of a productive session → save a brief summary to 'session_summary'. "
            "Keep values concise (1-3 sentences). Do NOT save sensitive data (tokens, passwords)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": (
                        "Short identifier for the fact. "
                        "Examples: 'default_jira_project', 'voucher_risk_areas', 'sprint_42_focus', 'SPPT-97814 analysis'"
                    ),
                },
                "value": {
                    "type": "string",
                    "description": "The fact or note to save. Keep it concise (1-3 sentences).",
                },
                "category": {
                    "type": "string",
                    "enum": ["active_context", "recent_work", "notes", "user_preferences", "session_summary"],
                    "description": (
                        "active_context: current sprint/feature focus; "
                        "recent_work: completed tasks log (rolling, last 20); "
                        "notes: persistent knowledge and risk patterns; "
                        "user_preferences: default settings and preferences; "
                        "session_summary: end-of-session summary (rolling, last 5)"
                    ),
                },
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "get_gitlab_mr_diff",
        "description": (
            "Fetch the diff of a GitLab Merge Request and return a structured analysis "
            "of changed files with regression test scope recommendations. "
            "Use when: (1) user provides a Jira ticket — first call get_jira_issue to read it, "
            "then extract any GitLab MR URL from the description or comments, then call this tool; "
            "(2) user directly provides a GitLab MR URL; "
            "(3) user asks 'what should I regression test for this PR/MR/ticket'. "
            "Returns: MR metadata, changed files grouped by module (API/DB/Frontend/etc.), "
            "diff excerpts, and recommended test types per module."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mr_url": {
                    "type": "string",
                    "description": (
                        "Full GitLab MR URL. "
                        "Example: https://gitlab.yourcompany.com/group/project/-/merge_requests/42"
                    ),
                },
            },
            "required": ["mr_url"],
        },
    },
    {
        "name": "save_test_suite",
        "description": (
            "Save a structured test suite with test cases to the database. "
            "Call this AFTER gathering all requirements (from MR diff, Jira, Confluence, etc.) "
            "and structuring the test cases. Use for: (1) exporting test cases from MR analysis; "
            "(2) saving manually-created test suites; (3) persisting Jira-based test plans. "
            "Supports source tracking: source_type can be 'manual' | 'mr' | 'jira' with optional "
            "source_ref (MR URL/number) and jira_key (e.g. 'SHOP-1234'). "
            "Returns: confirmation with suite ID and case count."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Suite name, e.g. 'Checkout Flow Tests' or 'Payment Integration Tests'",
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of the suite scope and purpose",
                },
                "test_cases": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Test case title"},
                            "category": {"type": "string", "description": "e.g. 'Happy Path', 'Edge Case', 'Error Handling'"},
                            "preconditions": {"type": "string", "description": "Setup steps before test execution"},
                            "steps": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of numbered execution steps"
                            },
                            "expected": {"type": "string", "description": "Expected result or behavior"},
                            "priority": {
                                "type": "string",
                                "enum": ["P0", "P1", "P2", "P3"],
                                "description": "Test priority (default: P1)"
                            },
                        },
                        "required": ["title", "steps", "expected"],
                    },
                    "description": "Array of test case objects",
                },
                "component": {
                    "type": "string",
                    "description": "Business component this suite belongs to, e.g. 'Promotion', 'Checkout', 'Payment', 'Order', 'User'. Used for grouping and filtering.",
                },
                "source_type": {
                    "type": "string",
                    "enum": ["manual", "mr", "jira"],
                    "description": "Origin of the test suite (default: 'manual')",
                },
                "source_ref": {
                    "type": "string",
                    "description": "Source reference: MR URL, MR number, or ticket ID",
                },
                "jira_key": {
                    "type": "string",
                    "description": "Jira ticket key if created from Jira, e.g. 'SHOP-1234'",
                },
            },
            "required": ["name", "description", "test_cases"],
        },
    },
    {
        "name": "propose_exam_case",
        "description": (
            "Propose a new exam case as a structured YAML draft when analyzing a production failure "
            "or test scenario. The agent reviews requirements, identifies test criteria, and proposes "
            "an exam that can be added to the exam library for future evaluation. "
            "The proposal is saved as a draft in exams/drafts/ for mentor review before publishing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "exam_id": {
                    "type": "string",
                    "description": "Unique exam identifier, e.g. 'qa-checkout-refund-edge-001'",
                },
                "skill": {
                    "type": "string",
                    "description": "Skill being tested, e.g. 'defect_analysis', 'test_case_design', 'risk_assessment'",
                },
                "scenario": {
                    "type": "string",
                    "description": "One-sentence scenario description that explains what the exam tests",
                },
                "difficulty": {
                    "type": "string",
                    "enum": ["L1", "L2", "L3"],
                    "description": "Difficulty level: L1 (junior), L2 (mid), L3 (senior)",
                },
                "input_message": {
                    "type": "string",
                    "description": "The prompt/question text that will be given to the agent during the exam",
                },
                "expected_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of keywords for auto-scoring (e.g. ['root cause', 'impact', 'fix'])",
                },
                "criteria": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "description": {"type": "string"},
                            "weight": {"type": "number"},
                            "rubric": {
                                "type": "object",
                                "properties": {
                                    "0": {"type": "string"},
                                    "1": {"type": "string"},
                                    "2": {"type": "string"},
                                    "3": {"type": "string"},
                                },
                            },
                        },
                    },
                    "description": "Optional rubric-based criteria for LLM-as-Judge evaluation",
                },
                "mentor_criteria": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of human judgment checklist items for mentor scoring",
                },
                "auto_score_weight": {
                    "type": "number",
                    "description": "Weight for keyword-based auto-scoring (default: 0.40)",
                },
                "mentor_score_weight": {
                    "type": "number",
                    "description": "Weight for mentor judgment scoring (default: 0.60)",
                },
                "pass_threshold": {
                    "type": "integer",
                    "description": "Passing score threshold (0-100, default: 75)",
                },
                "origin": {
                    "type": "string",
                    "enum": ["production_failure", "designed"],
                    "description": "Origin of the exam case (default: 'production_failure')",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for categorization, e.g. ['discount', 'payment', 'edge-case']",
                },
                "role": {
                    "type": "string",
                    "enum": ["QA", "Dev", "PM", "SRE", "PJ"],
                    "description": "Role for which this exam is designed (default: 'QA')",
                },
            },
            "required": [
                "exam_id",
                "skill",
                "scenario",
                "difficulty",
                "input_message",
            ],
        },
    },
]


def get_tool_definitions() -> list[dict]:
    """Return the tool definitions list in Anthropic API format."""
    return _TOOL_DEFINITIONS


def get_tools() -> list[callable]:
    """Return the list of tool functions (for use by other frameworks)."""
    return list(_TOOL_REGISTRY.values())


def build_tool_registry(
    agent_id: str = None,
    agent_name: str = "",
    conversation_id: str = None,
    trace_id: str = None,
    node_name: str = "",
) -> dict:
    """
    Build an agent-specific tool registry with context args bound via closure.
    Only binds kwargs that the target function actually accepts, so generic
    tools (e.g. read_requirement_doc) are unaffected.
    """
    import functools

    def _bind(fn, **kwargs):
        """Bind keyword arguments to a function, ignoring unsupported params."""
        import inspect
        sig = inspect.signature(fn)
        supported = set(sig.parameters.keys())
        bound_kwargs = {k: v for k, v in kwargs.items() if k in supported and v is not None}
        return functools.partial(fn, **bound_kwargs) if bound_kwargs else fn

    context = dict(
        agent_id=agent_id,
        agent_name=agent_name,
        conversation_id=conversation_id,
        trace_id=trace_id,
        node_name=node_name,
    )
    registry = {}
    for name, fn in _TOOL_REGISTRY.items():
        registry[name] = _bind(fn, **context)
    return registry


def execute_tool(
    name: str,
    args: dict,
    agent_id: str = None,
    conversation_id: str = None,
    agent_name: str = "",
    trace_id: str = None,
    node_name: str = None,
) -> str:
    """Execute a tool by name and return the string result.

    Automatically records an audit log entry (timing + result preview).
    For search_knowledge_base calls, extracts retrieval stats (top_score,
    result_count, low_relevance) and stores them in extra_data_json (P3).
    Logging is best-effort — failures are silently ignored.
    """
    import re
    import time
    from tools.audit_logger import log_tool_call

    registry = (
        build_tool_registry(
            agent_id=agent_id,
            agent_name=agent_name or "",
            conversation_id=conversation_id,
            trace_id=trace_id,
            node_name=node_name or "",
        )
        if agent_id else _TOOL_REGISTRY
    )
    if name not in registry:
        return f"[Error] Unknown tool: {name}"
    if "__parse_error__" in args:
        return f"[Error] Tool parameter parsing failed, please check parameter format: {args['__parse_error__']}"

    t0 = time.monotonic()
    try:
        result = str(registry[name](**args))
        duration_ms = int((time.monotonic() - t0) * 1000)

        # ── P3: KB retrieval analytics ─────────────────────────────────────
        extra_data = None
        if name == "search_knowledge_base":
            extra_data = _extract_kb_stats(result)

        log_tool_call(
            agent_id=agent_id or "terminal",
            agent_name=agent_name,
            conversation_id=conversation_id,
            tool_name=name,
            tool_args=args,
            result=result,
            duration_ms=duration_ms,
            success=True,
            trace_id=trace_id,
            node_name=node_name,
            extra_data=extra_data,
        )
        return result
    except Exception as e:
        duration_ms = int((time.monotonic() - t0) * 1000)
        error_str = str(e)
        log_tool_call(
            agent_id=agent_id or "terminal",
            agent_name=agent_name,
            conversation_id=conversation_id,
            tool_name=name,
            tool_args=args,
            result=error_str,
            duration_ms=duration_ms,
            success=False,
            error_msg=error_str,
            trace_id=trace_id,
            node_name=node_name,
        )
        return f"[Error] Tool {name} execution failed: {e}"


def _extract_kb_stats(result: str) -> dict | None:
    """Parse KB retrieval stats from search_knowledge_base result text (P3).

    The result already contains lines like 'Relevance: 82.5%' per chunk.
    We extract the top (first) score, count the chunks, and flag low relevance.
    Returns None if no stats can be parsed.
    """
    import re
    scores = [float(m) for m in re.findall(r"Relevance:\s*([\d.]+)%", result)]
    if not scores:
        return None
    top_score = scores[0]
    return {
        "top_score": top_score,
        "result_count": len(scores),
        "low_relevance": top_score < 75.0,
    }
