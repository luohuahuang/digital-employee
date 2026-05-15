"""
Seed mock observability data for UI verification.

Generates ~300 audit_log entries over the past 7 days across all three agents,
covering all four observability pillars:
  P0 - Chain Tracing  : every entry has a trace_id; multiple nodes per trace
  P1 - Health Score   : varied latencies, some errors, trend visible over days
  P2 - Quality Score  : quality_score events per chat turn with verdicts
  P3 - KB Analytics   : search_knowledge_base tool calls with extra_data_json stats

Run: python seed_observability.py
"""

import json
import random
import sqlite3
import uuid
from datetime import datetime, timedelta

random.seed(42)

DB_PATH = "web/de_team.db"

# ── existing agents ─────────────────────────────────────────────────────────
AGENTS = [
    {"id": "41935816-c707-46be-ac71-f73882a2d5ac", "name": "Promotion QA"},
    {"id": "c33f6e64-6420-48ef-a29c-bbaaf53dfca0", "name": "Checkout QA"},
    {"id": "cc1424b6-89c8-4c01-b7d5-f0fc1930fc10", "name": "Payment QA"},
]

# ── existing conversations (reuse them) ──────────────────────────────────────
CONV_BY_AGENT = {
    "41935816-c707-46be-ac71-f73882a2d5ac": [
        "d47fa397-d229-458c-964a-d45659b75017",
        "be83b891-4605-4e6c-870f-36718178cd7a",
    ],
    "c33f6e64-6420-48ef-a29c-bbaaf53dfca0": [
        "022c8f9a-abca-4090-b399-8733c7f1315c",
        "2a2c7315-5318-4c3c-81af-a72493f31c68",
    ],
    "cc1424b6-89c8-4c01-b7d5-f0fc1930fc10": [None],  # terminal calls
}

# ── helper pools ─────────────────────────────────────────────────────────────
TOOL_NAMES = [
    "search_knowledge_base",
    "search_knowledge_base",
    "search_knowledge_base",
    "confluence_search",
    "jira_search",
    "jira_get_issue",
    "gitlab_get_mr_diff",
]

KB_QUERIES = [
    "promotion discount calculation rules",
    "coupon stacking policy",
    "payment gateway timeout handling",
    "checkout flow edge cases",
    "voucher redemption limits",
    "refund policy for digital goods",
    "cart abandonment retry logic",
    "loyalty points expiry rules",
    "flash sale concurrency test cases",
    "cross-border payment validation",
]

KB_RESULT_TEMPLATES = [
    "Found {n} relevant documents.\n1. {q} [Relevance: {s1}%]\n   Content: According to policy doc v3.2...\n2. Related concepts [Relevance: {s2}%]\n   Content: Edge cases include...\n3. FAQ entry [Relevance: {s3}%]\n   Content: Frequently asked...",
    "Found {n} relevant documents.\n1. {q} spec sheet [Relevance: {s1}%]\n   Content: Specification details...\n2. Test matrix [Relevance: {s2}%]\n   Content: Test coverage matrix shows...",
    "Found {n} relevant documents.\n1. {q} - Engineering RFC [Relevance: {s1}%]\n   Content: RFC-2024-113 describes...\n2. QA runbook [Relevance: {s2}%]\n   Content: Step-by-step verification...\n3. Known issues [Relevance: {s3}%]\n   Content: JIRA tickets related...\n4. Historical incidents [Relevance: {s4}%]\n   Content: Post-mortem analysis...",
]

QUALITY_SCENARIOS = [
    # (helpfulness, boundaries, clarity, verdict, reasoning)
    (3, 3, 3, "excellent",  "Agent gave a thorough, accurate response covering all edge cases with clear test steps."),
    (3, 3, 2, "good",       "Response was helpful and within scope, but test steps could be more structured."),
    (2, 3, 3, "good",       "Clear and well-scoped, but missed some boundary conditions in the test cases."),
    (3, 2, 3, "good",       "Comprehensive test design, though slightly overstepped domain — mentioned infra topics."),
    (2, 2, 3, "acceptable", "Adequate response but lacked depth on negative test scenarios."),
    (3, 3, 1, "acceptable", "Helpful and on-topic but the formatting was confusing; hard to extract test steps."),
    (2, 2, 2, "acceptable", "Average quality — covered the basics but missed concurrency and race-condition cases."),
    (1, 3, 2, "poor",       "Response was too brief; only 2 of 8 expected scenarios were addressed."),
    (2, 1, 2, "poor",       "Agent went off-topic and referenced unrelated product areas in several answers."),
    (3, 3, 3, "excellent",  "Excellent structured test plan with preconditions, steps, and expected results."),
    (3, 3, 2, "good",       "Good coverage of happy path and error scenarios; minor formatting improvements possible."),
    (2, 3, 2, "acceptable", "Covered main scenarios but skipped internationalization test cases."),
]

JIRA_RESULTS = [
    "Issue SPB-54879: Payment timeout on 3DS2 redirect - Priority: High - Status: In Progress",
    "Issue SPPT-97814: Coupon A+B stacking not blocked correctly - Priority: Medium - Status: Open",
    "Issue SPB-57352: Shopee VIP email not triggered after order cancellation - Priority: High - Status: Done",
    "Issue SPB-61023: Flash sale race condition allows oversell - Priority: Critical - Status: Open",
    "Found 5 issues matching 'checkout regression': SPB-6102, SPB-6089, SPB-5971, SPB-5944, SPB-5901",
]

CONFLUENCE_RESULTS = [
    "Found 3 pages: 'Payment Gateway Integration Guide' (score 0.91), 'Checkout Flow Spec v4' (score 0.87), 'Test Runbook - Payments' (score 0.82)",
    "Found 2 pages: 'Promotion Rules Engine Design' (score 0.95), 'Coupon Service API Reference' (score 0.88)",
    "Found 4 pages: 'QA Standards & Coverage Guidelines' (score 0.79), 'Release Checklist Template' (score 0.74), 'Regression Suite Overview' (score 0.71), 'Defect Triage Process' (score 0.68)",
]

GITLAB_RESULTS = [
    "MR !4421 diff: 3 files changed — payment_service.py (+45/-12), checkout_controller.py (+8/-3), tests/test_payment.py (+67/-0). Key change: added retry backoff for 3DS2 timeout.",
    "MR !3891 diff: 2 files changed — promotion_engine.py (+23/-7), coupon_validator.py (+15/-2). Key change: fixed stacking logic for VIP + flash-sale coupons.",
]

USER_PROMPTS = [
    "能帮我分析一下 SPB-54879 这个 ticket 的测试风险吗？",
    "帮我设计促销券叠加使用的测试用例",
    "查一下知识库里有没有支付超时的处理规范",
    "这个 MR 有哪些需要重点测试的地方？",
    "帮我搜索一下 Confluence 里关于 checkout 流程的文档",
    "列出所有高优先级的支付相关 bug",
    "VIP 邮件未触发问题，帮我写几个回归测试用例",
    "帮我总结一下这次 sprint 的测试覆盖情况",
    "flash sale 并发场景下有哪些测试重点？",
    "退款流程的边界条件有哪些需要覆盖？",
]


def _uid():
    return str(uuid.uuid4())


def _ts(base: datetime, offset_seconds: int = 0) -> str:
    return (base + timedelta(seconds=offset_seconds)).strftime("%Y-%m-%d %H:%M:%S.%f")


def build_kb_extra(query: str, low: bool = False) -> dict:
    """Build extra_data_json for a KB search result."""
    if low:
        top = round(random.uniform(45.0, 72.0), 1)
    else:
        top = round(random.uniform(76.0, 96.0), 1)
    count = random.randint(2, 4)
    return {
        "top_score": top,
        "result_count": count,
        "low_relevance": top < 75.0,
        "query": query,
    }


def build_kb_result_text(query: str, extra: dict) -> str:
    """Build a realistic KB result preview string."""
    n = extra["result_count"]
    s1 = extra["top_score"]
    s2 = round(s1 - random.uniform(5, 15), 1)
    s3 = round(s2 - random.uniform(5, 12), 1)
    s4 = round(s3 - random.uniform(3, 10), 1)
    tpl = random.choice(KB_RESULT_TEMPLATES)
    return tpl.format(q=query, n=n, s1=s1, s2=s2, s3=max(s3, 30.0), s4=max(s4, 25.0))


def generate_trace(agent: dict, conv_id: str | None, ts_base: datetime,
                   day_index: int, total_days: int) -> list[dict]:
    """
    Generate one complete chat turn (trace) worth of audit entries.

    day_index / total_days controls quality/error degradation towards earlier days
    so trend charts show improvement over time.
    """
    trace_id = _uid()
    rows = []

    # ── simulate 'quality' degrading in the past (day 0 = oldest, day 6 = today) ──
    quality_good = day_index >= total_days - 3   # last 3 days are better
    error_chance = 0.20 if day_index < 3 else 0.07

    offset = 0  # accumulate wall-clock offset within this trace

    # 1. LLM call — agent node
    llm_duration = random.randint(800, 3500)
    llm_success = random.random() > error_chance
    input_tok = random.randint(1200, 4800)
    output_tok = random.randint(300, 1500)
    rows.append({
        "id": _uid(),
        "agent_id": agent["id"],
        "agent_name": agent["name"],
        "conversation_id": conv_id,
        "event_type": "llm_call",
        "tool_name": "claude-sonnet",
        "tool_args_json": json.dumps({"prompt_tokens": input_tok}),
        "result_preview": "Assistant decided to call search_knowledge_base" if llm_success else None,
        "duration_ms": llm_duration,
        "success": llm_success,
        "error_msg": "LLM API timeout after 3500ms" if not llm_success else None,
        "input_tokens": input_tok,
        "output_tokens": output_tok if llm_success else 0,
        "trace_id": trace_id,
        "node_name": "agent",
        "extra_data_json": None,
        "created_at": _ts(ts_base, offset),
    })
    offset += llm_duration // 1000 + random.randint(0, 2)

    if not llm_success:
        return rows  # short trace on error

    # 2. Tool calls — 1 to 3 tools
    num_tools = random.choices([1, 2, 3], weights=[3, 4, 3])[0]
    for i in range(num_tools):
        tool_name = random.choice(TOOL_NAMES)
        tool_duration = random.randint(150, 2200)
        tool_success = random.random() > (error_chance * 0.5)

        extra = None
        result_preview = None
        tool_args = {}

        if tool_name == "search_knowledge_base":
            query = random.choice(KB_QUERIES)
            low = not quality_good and random.random() < 0.45
            extra = build_kb_extra(query, low=low)
            tool_args = {"query": query, "top_k": 4}
            if tool_success:
                result_preview = build_kb_result_text(query, extra)
            else:
                result_preview = "Error: ChromaDB connection timeout"
        elif tool_name == "jira_search" or tool_name == "jira_get_issue":
            tool_args = {"jql": "project = SPB AND priority = High"} if tool_name == "jira_search" else {"issue_key": "SPB-54879"}
            result_preview = random.choice(JIRA_RESULTS) if tool_success else "Error: Jira API rate limit exceeded"
        elif tool_name == "confluence_search":
            tool_args = {"query": "checkout flow specification", "spaces": ["QA", "ENG"]}
            result_preview = random.choice(CONFLUENCE_RESULTS) if tool_success else "Error: Confluence authentication failed"
        elif tool_name == "gitlab_get_mr_diff":
            tool_args = {"mr_iid": random.randint(3800, 4500), "project_id": "shopee/backend"}
            result_preview = random.choice(GITLAB_RESULTS) if tool_success else "Error: GitLab MR not found"

        rows.append({
            "id": _uid(),
            "agent_id": agent["id"],
            "agent_name": agent["name"],
            "conversation_id": conv_id,
            "event_type": "tool_call",
            "tool_name": tool_name,
            "tool_args_json": json.dumps(tool_args),
            "result_preview": result_preview,
            "duration_ms": tool_duration,
            "success": tool_success,
            "error_msg": None if tool_success else f"Tool {tool_name} returned non-200",
            "input_tokens": None,
            "output_tokens": None,
            "trace_id": trace_id,
            "node_name": "tools",
            "extra_data_json": json.dumps(extra) if extra else None,
            "created_at": _ts(ts_base, offset),
        })
        offset += tool_duration // 1000 + random.randint(1, 3)

    # 3. Occasional L2 decision
    if random.random() < 0.18:
        approved = random.random() > 0.25
        rows.append({
            "id": _uid(),
            "agent_id": agent["id"],
            "agent_name": agent["name"],
            "conversation_id": conv_id,
            "event_type": "l2_decision",
            "tool_name": "create_defect_mock",
            "tool_args_json": json.dumps({"title": "Regression: payment timeout not retried", "project": "SPB"}),
            "result_preview": "Defect SPB-62104 created" if approved else "Rejected by mentor — needs more evidence",
            "duration_ms": random.randint(5000, 45000),
            "success": approved,
            "error_msg": None,
            "l2_approved": approved,
            "input_tokens": None,
            "output_tokens": None,
            "trace_id": trace_id,
            "node_name": "human_review",
            "extra_data_json": None,
            "created_at": _ts(ts_base, offset),
        })
        offset += random.randint(5, 15)

    # 4. Quality score (P2) — appended after every successful turn
    scenario = random.choice(QUALITY_SCENARIOS if quality_good else QUALITY_SCENARIOS[4:])
    helpfulness, boundaries, clarity, verdict, reasoning = scenario
    total_score = round((helpfulness + boundaries + clarity) / 9.0, 3)
    quality_extra = {
        "score": total_score,
        "verdict": verdict,
        "reasoning": reasoning,
        "breakdown": {
            "helpfulness": helpfulness,
            "boundaries": boundaries,
            "clarity": clarity,
        },
    }
    rows.append({
        "id": _uid(),
        "agent_id": agent["id"],
        "agent_name": agent["name"],
        "conversation_id": conv_id,
        "event_type": "quality_score",
        "tool_name": "llm_judge",
        "tool_args_json": None,
        "result_preview": f"{total_score:.2f} ({verdict})",
        "duration_ms": random.randint(1200, 3800),
        "success": True,
        "error_msg": None,
        "input_tokens": None,
        "output_tokens": None,
        "trace_id": trace_id,
        "node_name": "quality_judge",
        "extra_data_json": json.dumps(quality_extra),
        "created_at": _ts(ts_base, offset + 1),
    })

    return rows


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Check current count
    cur.execute("SELECT COUNT(*) FROM audit_logs")
    before = cur.fetchone()[0]
    print(f"Existing audit_logs rows: {before}")

    NOW = datetime.utcnow()
    DAYS = 7
    all_rows = []

    # Generate turns: ~8-14 turns per agent per day
    for day_idx in range(DAYS):
        day_start = NOW - timedelta(days=DAYS - 1 - day_idx)
        day_start = day_start.replace(hour=9, minute=0, second=0, microsecond=0)

        for agent in AGENTS:
            convs = CONV_BY_AGENT.get(agent["id"], [None])
            num_turns = random.randint(8, 14)

            for turn in range(num_turns):
                # spread turns across 9am–8pm
                hour_offset = random.randint(0, 660) * 60  # 0–11h in seconds
                ts_base = day_start + timedelta(seconds=hour_offset + turn * 180)
                conv_id = random.choice(convs)

                trace_rows = generate_trace(agent, conv_id, ts_base, day_idx, DAYS)
                all_rows.extend(trace_rows)

    print(f"Generated {len(all_rows)} new rows across {DAYS} days")

    # Insert
    insert_sql = """
        INSERT INTO audit_logs
          (id, agent_id, agent_name, conversation_id,
           event_type, tool_name, tool_args_json, result_preview,
           duration_ms, success, error_msg, l2_approved,
           input_tokens, output_tokens,
           trace_id, node_name, extra_data_json, created_at)
        VALUES
          (:id, :agent_id, :agent_name, :conversation_id,
           :event_type, :tool_name, :tool_args_json, :result_preview,
           :duration_ms, :success, :error_msg, :l2_approved,
           :input_tokens, :output_tokens,
           :trace_id, :node_name, :extra_data_json, :created_at)
    """

    # Ensure l2_approved is present in every row
    for row in all_rows:
        row.setdefault("l2_approved", None)
        row["success"] = 1 if row["success"] else 0

    cur.executemany(insert_sql, all_rows)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM audit_logs")
    after = cur.fetchone()[0]
    print(f"New total: {after} rows (+{after - before})")

    # Print a quick breakdown
    print("\nEvent type breakdown (new data):")
    cur.execute("SELECT event_type, COUNT(*) FROM audit_logs GROUP BY event_type")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")

    print("\nSample traces (newest 3):")
    cur.execute("SELECT DISTINCT trace_id, COUNT(*) as n FROM audit_logs WHERE trace_id IS NOT NULL GROUP BY trace_id ORDER BY MIN(created_at) DESC LIMIT 3")
    for row in cur.fetchall():
        print(f"  trace={row[0][:8]}…  events={row[1]}")

    print("\nQuality score sample:")
    cur.execute("SELECT result_preview, extra_data_json FROM audit_logs WHERE event_type='quality_score' ORDER BY created_at DESC LIMIT 5")
    for row in cur.fetchall():
        extra = json.loads(row[1])
        print(f"  score={row[0]}  breakdown={extra.get('breakdown')}")

    print("\nKB low-relevance sample:")
    cur.execute("SELECT extra_data_json FROM audit_logs WHERE tool_name='search_knowledge_base' AND extra_data_json IS NOT NULL ORDER BY created_at DESC LIMIT 5")
    for row in cur.fetchall():
        extra = json.loads(row[0])
        print(f"  top={extra.get('top_score')}%  low={extra.get('low_relevance')}  count={extra.get('result_count')}")

    conn.close()
    print("\n✅ Seed complete.")


if __name__ == "__main__":
    main()
