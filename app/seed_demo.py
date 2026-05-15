"""
seed_demo.py — Populate a rich multi-role demo dataset.

Creates agents for QA / Dev / PM / SRE / PJ roles, realistic conversations,
exam runs, and audit logs, so the UI has something interesting to show in a demo.

Usage (from app/ directory):
    python3 seed_demo.py
"""
import json
import math
import random
import sqlite3
import uuid
from datetime import datetime, timedelta

DB_PATH = "web/de_team.db"

random.seed(42)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _uid(): return str(uuid.uuid4())
def _now(): return datetime.utcnow()
def _ago(days=0, hours=0, minutes=0):
    return datetime.utcnow() - timedelta(days=days, hours=hours, minutes=minutes)
def _ts(dt): return dt.strftime("%Y-%m-%d %H:%M:%S.%f")


# ── Agent definitions ──────────────────────────────────────────────────────────

AGENTS = [
    # ── QA ──────────────────────────────────────────────────────────────────────
    {
        "id": _uid(), "role": "QA", "name": "Alice · Promo QA",
        "product_line": "promotion", "avatar_emoji": "🎫", "ranking": "Senior",
        "description": "Specialises in voucher rules, campaign edge cases, and discount stacking",
        "specialization": "Focus on promotion service: discount calculation, coupon redemption, stacking rules, expiry edge cases",
        "default_jira_project": "PROMO", "confluence_spaces": '["PROMO","QA"]',
    },
    {
        "id": _uid(), "role": "QA", "name": "Bob · Checkout QA",
        "product_line": "checkout", "avatar_emoji": "🛒", "ranking": "Junior",
        "description": "Covers cart management, order placement flow, and address validation",
        "specialization": "Focus on checkout service: cart operations, order creation, address validation, payment gateway handoff",
        "default_jira_project": "CART", "confluence_spaces": '["CHECKOUT","QA"]',
    },
    {
        "id": _uid(), "role": "QA", "name": "Carol · Payment QA",
        "product_line": "payment", "avatar_emoji": "💳", "ranking": "Lead",
        "description": "Deep expertise in payment gateway integrations, refunds, and PCI compliance",
        "specialization": "Focus on payment service: gateway integration, refund flows, idempotency, PCI-DSS compliance boundaries",
        "default_jira_project": "PAY", "confluence_spaces": '["PAYMENT","COMPLIANCE"]',
    },
    # ── Dev ──────────────────────────────────────────────────────────────────────
    {
        "id": _uid(), "role": "Dev", "name": "David · Backend Dev",
        "product_line": "checkout", "avatar_emoji": "⚙️", "ranking": "Senior",
        "description": "Go/Python backend engineer, owns the order placement service",
        "specialization": "Backend services: REST API design, database query optimisation, async job processing, microservice patterns",
        "default_jira_project": "CART", "confluence_spaces": '["BACKEND","ARCH"]',
    },
    {
        "id": _uid(), "role": "Dev", "name": "Eva · Frontend Dev",
        "product_line": "platform", "avatar_emoji": "🖥️", "ranking": "Junior",
        "description": "React/TypeScript engineer, owns the buyer-facing web storefront",
        "specialization": "Frontend: component architecture, state management, accessibility, Core Web Vitals optimisation",
        "default_jira_project": "WEB", "confluence_spaces": '["FRONTEND"]',
    },
    # ── PM ───────────────────────────────────────────────────────────────────────
    {
        "id": _uid(), "role": "PM", "name": "Frank · Growth PM",
        "product_line": "promotion", "avatar_emoji": "📈", "ranking": "Senior",
        "description": "Owns the buyer acquisition and promotional feature roadmap",
        "specialization": "Product strategy: OKR alignment, PRD writing, A/B test design, user research synthesis, north-star metrics",
        "default_jira_project": "PROMO", "confluence_spaces": '["PRODUCT","GROWTH"]',
    },
    {
        "id": _uid(), "role": "PM", "name": "Grace · Checkout PM",
        "product_line": "checkout", "avatar_emoji": "🗂️", "ranking": "Intern",
        "description": "New PM focusing on checkout funnel optimisation and sprint planning",
        "specialization": "Checkout product: conversion funnel, user journey, sprint planning, stakeholder alignment",
        "default_jira_project": "CART", "confluence_spaces": '["PRODUCT"]',
    },
    # ── SRE ──────────────────────────────────────────────────────────────────────
    {
        "id": _uid(), "role": "SRE", "name": "Hank · Platform SRE",
        "product_line": "platform", "avatar_emoji": "🔧", "ranking": "Lead",
        "description": "Owns reliability targets, incident response, and capacity planning",
        "specialization": "SRE: SLO/SLI definition, incident triage playbooks, chaos engineering, database capacity, Kubernetes operations",
        "default_jira_project": "INFRA", "confluence_spaces": '["SRE","RUNBOOKS"]',
    },
    {
        "id": _uid(), "role": "SRE", "name": "Iris · Payment SRE",
        "product_line": "payment", "avatar_emoji": "🛡️", "ranking": "Junior",
        "description": "Reliability engineer for payment gateway and transaction pipeline",
        "specialization": "Payment reliability: gateway SLA monitoring, transaction retry logic, dead-letter queue management",
        "default_jira_project": "PAY", "confluence_spaces": '["SRE","PAYMENT"]',
    },
    # ── PJ ───────────────────────────────────────────────────────────────────────
    {
        "id": _uid(), "role": "PJ", "name": "Jack · Project Lead",
        "product_line": "platform", "avatar_emoji": "📋", "ranking": "Senior",
        "description": "Coordinates cross-functional delivery for platform and infrastructure projects",
        "specialization": "Project management: milestone tracking, risk management, dependency mapping, stakeholder reporting, retrospectives",
        "default_jira_project": "INFRA", "confluence_spaces": '["PROJECT","INFRA"]',
    },
]


# ── Conversations & Messages ───────────────────────────────────────────────────

CONVERSATIONS = {
    "Alice · Promo QA": [
        {
            "title": "Flash sale edge case — simultaneous redemption",
            "msgs": [
                ("user", "I need test cases for simultaneous coupon redemption during flash sale."),
                ("assistant", "**Simultaneous Coupon Redemption — Test Cases**\n\n**Scenario 1 — Race condition on last voucher**\n- Two users click 'Apply Coupon' at the same millisecond for the last available coupon.\n- Expected: Exactly one succeeds; the other receives 'Coupon already claimed'.\n\n**Scenario 2 — Network retry**\n- User applies coupon, network drops before ACK. Client retries.\n- Expected: Idempotent — coupon applied exactly once (no double deduction).\n\n**Scenario 3 — Expiry boundary**\n- Coupon expires at 23:59:59. User submits request at 23:59:58 (server time) but it processes at 00:00:01.\n- Expected: Determined by server receipt time, not processing time."),
                ("user", "Good. Can you also cover the stack-with-platform-coupon scenario?"),
                ("assistant", "**Stacking Rules — Test Cases**\n\n| # | Coupon A | Coupon B | Expected |\n|---|----------|----------|----------|\n| 1 | 10% off (seller) | $5 off (platform) | Both apply, platform coupon applied last |\n| 2 | 20% off (seller) | 15% off (seller) | Only highest seller coupon applies |\n| 3 | Free shipping | $5 off (platform) | Both apply |\n\n**Edge case:** Stacking takes final price below $0 → floor at $0.01 minimum charge."),
            ],
            "created_days_ago": 5,
        },
        {
            "title": "Regression scope for campaign service v2.4",
            "msgs": [
                ("user", "What regression tests should I prioritise for the campaign service v2.4 release?"),
                ("assistant", "Based on typical campaign service change patterns, here's a risk-ranked regression scope:\n\n**P0 — Must run before release:**\n1. Coupon creation → redemption end-to-end flow\n2. Campaign start/end time boundary (edge: DST transitions)\n3. Budget cap enforcement (campaign pauses when budget exhausted)\n\n**P1 — Run in parallel:**\n4. Multi-tier discount calculation accuracy\n5. B2B vs B2C coupon isolation\n6. Real-time inventory deduction (flash sale scenario)\n\n**P2 — Can defer to next sprint:**\n7. Historical analytics data consistency\n8. Admin dashboard display edge cases\n\nWant me to draft the test case checklist for P0?"),
            ],
            "created_days_ago": 2,
        },
    ],
    "David · Backend Dev": [
        {
            "title": "Order service — database query optimisation",
            "msgs": [
                ("user", "The order listing query is taking 2.3 seconds for merchants with >10k orders. Can you help?"),
                ("assistant", "2.3s for 10k rows strongly suggests a missing index or an N+1 pattern. Let me help you diagnose.\n\n**Step 1 — Run EXPLAIN ANALYZE:**\n```sql\nEXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)\nSELECT o.*, u.email FROM orders o\nJOIN users u ON u.id = o.user_id\nWHERE o.merchant_id = $1\nORDER BY o.created_at DESC\nLIMIT 50;\n```\n\n**What to look for:**\n- `Seq Scan` on `orders` → you need an index on `(merchant_id, created_at DESC)`\n- High `Buffers: shared hit` → data is in memory but plan is bad\n- `Nested Loop` with >1k iterations → N+1 problem\n\n**Likely fix:**\n```sql\nCREATE INDEX CONCURRENTLY idx_orders_merchant_created\nON orders(merchant_id, created_at DESC);\n```\n\nShare the EXPLAIN output and I can give a more precise recommendation."),
                ("user", "The EXPLAIN shows a Seq Scan on orders with 180,000 estimated rows. Confirmed missing index."),
                ("assistant", "Confirmed. The `CONCURRENTLY` variant is safe for production — it won't lock the table:\n\n```sql\nCREATE INDEX CONCURRENTLY idx_orders_merchant_created\nON orders (merchant_id, created_at DESC)\nINCLUDE (status, total_amount);  -- covering index for the SELECT columns\n```\n\nThe `INCLUDE` clause makes this a covering index so Postgres can return results without a heap fetch. Expected improvement: from 2.3s → under 50ms for this query pattern."),
            ],
            "created_days_ago": 3,
        },
        {
            "title": "PR review — payment webhook handler",
            "msgs": [
                ("user", "Can you review this webhook handler design? It writes to DB synchronously inside the HTTP handler."),
                ("assistant", "Synchronous DB writes inside a webhook handler are a reliability risk. Here's my review:\n\n**Issues:**\n1. **Latency SLA breach risk** — if DB is slow, the payment provider's webhook times out and retries, causing duplicate processing\n2. **Missing idempotency guard** — no check for `event_id` before processing; a retry will double-apply the payment\n3. **No dead-letter handling** — if the DB write fails, the event is silently lost\n\n**Recommended pattern:**\n```python\n@app.post('/webhook/payment')\nasync def payment_webhook(event: PaymentEvent, db: Session):\n    # 1. Acknowledge immediately (< 200ms)\n    if db.query(ProcessedEvent).filter_by(id=event.id).first():\n        return {'status': 'already_processed'}  # idempotent\n    \n    # 2. Enqueue for async processing\n    await queue.enqueue('process_payment_event', event.dict())\n    return {'status': 'accepted'}  # 200 before DB write\n```\n\nThe actual DB write happens in the queue worker, with retry logic and a dead-letter queue."),
            ],
            "created_days_ago": 1,
        },
    ],
    "Frank · Growth PM": [
        {
            "title": "Flash sale PRD — first draft review",
            "msgs": [
                ("user", "Help me structure the PRD for our flash sale feature. We need it done by Thursday."),
                ("assistant", "**Flash Sale Feature — PRD Skeleton**\n\n**1. Problem Statement**\nBuyers currently have no urgency signals at checkout. Conversion rate for time-sensitive promotions is 12% below category benchmark.\n\n**2. Goals & Success Metrics**\n- Primary: Increase conversion rate during sale windows by 20%\n- Secondary: Reduce cart abandonment within 10 minutes of sale start by 15%\n- Guardrail: No increase in order cancellation rate (oversell prevention)\n\n**3. User Stories**\n- As a bargain-seeking buyer, I want to see a countdown timer so I feel urgency to complete checkout\n- As a buyer, I want clear 'sold out' feedback so I don't waste time on unavailable items\n- As an admin, I want to set per-SKU quantity caps so I can control exposure\n\n**4. Out of Scope**\n- Personalised flash sale targeting (Phase 2)\n- Seller self-service flash sale creation (Phase 2)\n\n**5. Key Risks**\n- Inventory race conditions at sale start → need DB-level locking or reservation\n- Countdown timer accuracy across time zones → use UTC server time\n\nShall I expand any section?"),
            ],
            "created_days_ago": 4,
        },
        {
            "title": "OKR Q3 alignment — growth metrics",
            "msgs": [
                ("user", "I need to align our team's OKRs with the company north-star metric of GMV. Help me frame the KRs."),
                ("assistant", "**Growth PM OKRs — Q3 Framing**\n\n**Objective:** Accelerate buyer GMV through improved promotional effectiveness\n\n**Key Results:**\n- KR1: Increase promotional campaign conversion rate from 8.2% → 11% by end of Q3\n- KR2: Launch flash sale feature with ≥15% uplift in conversion vs. standard sale (measured via A/B)\n- KR3: Reduce voucher abandonment rate (user clicks 'Apply' but doesn't checkout) from 34% → 25%\n- KR4: Achieve ≥80% recall of promotional spend — every $1 of coupon cost generates ≥$3 incremental GMV\n\n**Notes:**\n- KR4 is a guardrail — if we hit KR1–3 by burning voucher budget indiscriminately, that's a failure\n- Each KR needs a defined measurement method before Sprint 1; instrument dashboards in Week 1"),
            ],
            "created_days_ago": 6,
        },
    ],
    "Hank · Platform SRE": [
        {
            "title": "11.11 capacity plan — order service",
            "msgs": [
                ("user", "11.11 is in 3 weeks. Last year peak was 45k RPS. Marketing expects 3x this year. What do we need?"),
                ("assistant", "**11.11 Capacity Plan — Order Service**\n\n**Baseline assessment:**\nAt 45k RPS with current 20 app servers, each handles ~2,250 RPS. At 3x (135k RPS), we need ~60 servers at the same utilisation, or efficiency gains to reduce that.\n\n**Bottleneck analysis (in priority order):**\n1. **Database** — Postgres is almost always the bottleneck before app servers. Add 2 more read replicas. Introduce PgBouncer if not already present (connection pooling for burst load)\n2. **App servers** — Pre-scale to 55 servers 2 hours before event start. Configure auto-scaling to cap at 70\n3. **Redis** — Check keyspace hit rate. If <90%, the order service is hitting DB on cache misses. Pre-warm cache for top-selling SKUs\n4. **Load balancer** — Nginx config: increase `worker_connections` to 4096, enable `keepalive 32`\n\n**Validation plan:**\n- Week 1: Load test at 90k RPS (2x) — identify real bottleneck\n- Week 2: Load test at 150k RPS (3.3x) — validate fixes\n- Week 3: Game day rehearsal + runbook review\n\n**Kill switch:** If DB CPU >85% sustained for 2 min, auto-enable 'display-only' mode (no new orders)."),
            ],
            "created_days_ago": 2,
        },
        {
            "title": "Post-mortem — payment timeout incident INC-2024-089",
            "msgs": [
                ("user", "Help me write the post-mortem for last week's payment timeout. Duration: 23 minutes, ~800 failed transactions."),
                ("assistant", "**Post-Mortem: Payment Service Timeout — INC-2024-089**\n\n**Incident Summary**\nDuration: 2024-10-14 14:37–15:00 UTC (23 minutes)\nImpact: ~800 order payment failures; estimated $12,000 GMV loss\nSeverity: SEV-2\n\n**Timeline**\n- 14:37 — PagerDuty alert: payment_gateway_p99_latency > 5s\n- 14:41 — On-call Iris acknowledges, begins triage\n- 14:45 — Root cause identified: connection pool exhausted (max 50, current 50/50)\n- 14:52 — Temporary fix: increased pool size to 100 via config hot-reload\n- 15:00 — Latency normalised, all-clear\n\n**Root Cause**\nA batch job for payment reconciliation was not rate-limited and consumed 40 of 50 connections during business hours. A traffic spike at 14:37 exhausted the remaining 10.\n\n**Action Items**\n1. [ ] Separate connection pools for batch jobs vs. live traffic (Owner: Iris, Due: Oct 21)\n2. [ ] Add connection pool saturation to PagerDuty escalation policy (Owner: Hank, Due: Oct 18)\n3. [ ] Document pool sizing formula in runbook (Owner: Hank, Due: Oct 25)"),
            ],
            "created_days_ago": 7,
        },
    ],
    "Jack · Project Lead": [
        {
            "title": "Sprint 14 planning — scope conflict resolution",
            "msgs": [
                ("user", "We have a scope conflict: payment gateway v2 needs 3 extra days but the sprint end is fixed. What do I do?"),
                ("assistant", "**Sprint Scope Conflict — Decision Framework**\n\nYou have three levers. Present all three to stakeholders with trade-offs, don't pre-decide:\n\n**Option A — Scope reduction** (recommended)\n- Ship gateway v2 core integration only; defer error-handling edge cases to Sprint 15\n- Risk: some payment failure scenarios won't be handled gracefully until next sprint\n- Trade-off: meets the regulatory deadline with acceptable scope\n\n**Option B — Resource addition**\n- Pull in the one backend engineer currently on tech-debt work to assist\n- Risk: disrupts their current task; knowledge transfer takes ~1 day\n- Trade-off: keeps full scope but burns goodwill and creates context-switching cost\n\n**Option C — Timeline slip**\n- Push release by 3 days; acceptable only if the regulatory deadline has buffer\n- Risk: if the deadline is hard, this is not an option\n\n**My recommendation:** Present Option A with a clear scope-cut definition so engineering knows exactly what moves to Sprint 15. Request a decision from the stakeholders within 24 hours — delay compounds the problem."),
                ("user", "Stakeholders chose Option A. How do I communicate this to the team?"),
                ("assistant", "**Team Communication — Scope Change**\n\nKeep it short, factual, and forward-looking:\n\n> **Sprint 14 scope update (5-min standup item)**\n>\n> After stakeholder alignment, we're shipping gateway v2 core integration in Sprint 14 and deferring error-handling edge cases (items #47, #48, #51) to Sprint 15.\n>\n> **Why:** The regulatory deadline is fixed. Delivering core functionality on time is the right trade-off.\n>\n> **What moves:** David, please update those three Jira tickets to Sprint 15 and add a 'deferred — Sprint 14 scope cut' label.\n>\n> **No other changes.** The rest of the sprint plan stands.\n\nThen follow up async with a Jira comment on each deferred ticket explaining why. This creates an audit trail and prevents the items from being forgotten."),
            ],
            "created_days_ago": 1,
        },
    ],
}


# ── Exam run data (realistic scores per role) ──────────────────────────────────

EXAM_TEMPLATES = {
    "QA": [
        ("tc_design_001.yaml",        "test_case_design", "L1", 78, 82, "qa-tc-design-cart-001"),
        ("bug_report_quality_001.yaml","bug_reporting",   "L1", 91, 88, None),
        ("flash_sale_concurrency_001.yaml","concurrency", "L2", 65, 71, None),
        ("security_boundary_001.yaml", "security",        "L2", 73, 68, None),
    ],
    "Dev": [
        ("dev_code_review_001.yaml",   "code_review",    "L2", 84, 90, "dev-code-review-001"),
        ("dev_architecture_001.yaml",  "system_design",  "L3", 62, 78, "dev-architecture-001"),
    ],
    "PM": [
        ("pm_prd_001.yaml",            "prd_writing",    "L2", 76, 85, "pm-prd-flash-sale-001"),
        ("pm_metrics_001.yaml",        "data_analysis",  "L2", 69, 74, "pm-metrics-001"),
    ],
    "SRE": [
        ("sre_incident_001.yaml",      "incident_response","L2", 88, 92, "sre-incident-001"),
        ("sre_capacity_001.yaml",      "capacity_planning","L2", 71, 80, "sre-capacity-001"),
    ],
    "PJ": [
        ("pj_sprint_planning_001.yaml","sprint_planning","L1", 80, 85, "pj-sprint-planning-001"),
    ],
}


# ── Audit log seed ─────────────────────────────────────────────────────────────

TOOL_BY_ROLE = {
    "QA":  ["search_knowledge_base", "search_jira", "get_jira_issue", "create_defect_mock", "search_confluence"],
    "Dev": ["search_knowledge_base", "get_gitlab_mr_diff", "search_confluence", "write_output_file"],
    "PM":  ["search_confluence", "search_jira", "search_knowledge_base", "write_output_file"],
    "SRE": ["search_jira", "search_confluence", "search_knowledge_base", "write_output_file"],
    "PJ":  ["search_jira", "search_confluence", "write_output_file"],
}


def _generate_audit_rows(agent, n=40):
    rows = []
    tools = TOOL_BY_ROLE.get(agent["role"], ["search_knowledge_base"])
    for i in range(n):
        days_back = random.uniform(0, 7)
        trace_id = _uid()
        # llm_call entry
        rows.append((
            _uid(), agent["id"], agent["name"], None,
            "llm_call", None, None, "Reasoning step completed.",
            random.randint(800, 3000), True, None, None,
            random.randint(400, 2000), random.randint(100, 800),
            trace_id, "agent", None,
            _ts(_ago(days=int(days_back), hours=random.randint(0,23))),
        ))
        # tool_call entries
        n_tools = random.randint(1, 3)
        for j in range(n_tools):
            tool = random.choice(tools)
            success = random.random() > 0.06
            duration = random.randint(80, 2200)
            is_l2 = tool in ("create_defect_mock",)
            extra = None
            if tool == "search_knowledge_base":
                top_score = round(random.uniform(55, 97), 1)
                extra = json.dumps({"top_score": top_score, "result_count": 3, "low_relevance": top_score < 75})
            rows.append((
                _uid(), agent["id"], agent["name"], None,
                "tool_call", tool,
                json.dumps({"query": f"sample query {i}_{j}"}),
                "Search results: relevant content found..." if success else None,
                duration, success, None if success else "Timeout", None,
                None, None, trace_id, "tools", extra,
                _ts(_ago(days=int(days_back), hours=random.randint(0,23), minutes=j*2)),
            ))
            if is_l2:
                approved = random.random() > 0.2
                rows.append((
                    _uid(), agent["id"], agent["name"], None,
                    "l2_decision", tool, None, None, None,
                    True, None, approved, None, None,
                    trace_id, "human_review", None,
                    _ts(_ago(days=int(days_back), hours=random.randint(0,23), minutes=j*2+1)),
                ))
        # quality_score entry
        score = round(random.uniform(0.60, 0.98) - (days_back / 7) * 0.05, 3)
        verdict = "good" if score > 0.75 else "needs_improvement"
        rows.append((
            _uid(), agent["id"], agent["name"], None,
            "quality_score", None, None, None, None,
            True, None, None, None, None,
            trace_id, "agent",
            json.dumps({"score": score, "verdict": verdict, "reasoning": "LLM-as-Judge evaluation"}),
            _ts(_ago(days=int(days_back), hours=random.randint(0,23), minutes=n_tools*2+2)),
        ))
    return rows


def _build_exam_run(agent_id, agent_name, role, days_back):
    templates = EXAM_TEMPLATES.get(role, EXAM_TEMPLATES["QA"])
    tmpl = random.choice(templates)
    exam_file, skill, difficulty, auto_s, mentor_s, exam_id = tmpl

    auto_score = auto_s + random.randint(-5, 5)
    mentor_score = mentor_s + random.randint(-5, 5)
    auto_w, mentor_w = 0.5, 0.5
    total = round(auto_score * auto_w + mentor_score * mentor_w, 1)
    threshold = 70
    passed = total >= threshold
    elapsed = round(random.uniform(4.5, 18.0), 1)

    judge_results = json.dumps({
        "helpfulness": {"score": random.randint(2, 3), "evidence": "Response directly addressed the task.", "reasoning": "Comprehensive coverage."},
        "boundaries":  {"score": random.randint(2, 3), "evidence": "Stayed within role.",  "reasoning": "No overreach detected."},
        "clarity":     {"score": random.randint(1, 3), "evidence": "Well-structured output.", "reasoning": "Clear sections."},
    })

    return (
        _uid(), agent_id, agent_name, exam_file, exam_id, skill, difficulty,
        "done", auto_score, auto_w, mentor_score, mentor_w,
        total, threshold, passed,
        json.dumps([]), json.dumps(["Thoroughness", "Accuracy"]),
        json.dumps({"Thoroughness": 0.85, "Accuracy": 0.90}),
        "Agent produced a detailed, well-structured response covering all required aspects.",
        elapsed, None, None, None,
        judge_results, None,
        _ts(_ago(days=days_back)),
    )


# ── Main seeding ───────────────────────────────────────────────────────────────

def seed():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Check if already seeded
    cur.execute("SELECT COUNT(*) FROM agents WHERE name LIKE '%·%'")
    if cur.fetchone()[0] >= 5:
        print("Demo data already present — skipping (run with --force to override).")
        conn.close()
        return

    print("Seeding demo agents...")
    for agent in AGENTS:
        cur.execute("""
            INSERT OR IGNORE INTO agents
              (id, name, product_line, avatar_emoji, description, specialization,
               default_jira_project, confluence_spaces, ranking, role, created_at, is_active)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,1)
        """, (
            agent["id"], agent["name"], agent["product_line"], agent["avatar_emoji"],
            agent["description"], agent["specialization"],
            agent["default_jira_project"], agent["confluence_spaces"],
            agent["ranking"], agent["role"],
            _ts(_ago(days=random.randint(14, 60))),
        ))

    conn.commit()
    print(f"  ✓ {len(AGENTS)} agents inserted")

    # Conversations & messages
    print("Seeding conversations and messages...")
    total_convs = 0
    total_msgs = 0
    agent_map = {a["name"]: a["id"] for a in AGENTS}

    for agent_name, convs in CONVERSATIONS.items():
        agent_id = agent_map.get(agent_name)
        if not agent_id:
            continue
        for conv in convs:
            conv_id = _uid()
            cur.execute(
                "INSERT INTO conversations (id, agent_id, title, created_at) VALUES (?,?,?,?)",
                (conv_id, agent_id, conv["title"], _ts(_ago(days=conv["created_days_ago"]))),
            )
            total_convs += 1
            for i, (role, content) in enumerate(conv["msgs"]):
                cur.execute(
                    "INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?,?,?,?,?)",
                    (_uid(), conv_id, role, content,
                     _ts(_ago(days=conv["created_days_ago"], minutes=i*3))),
                )
                total_msgs += 1

    conn.commit()
    print(f"  ✓ {total_convs} conversations, {total_msgs} messages inserted")

    # Exam runs
    print("Seeding exam runs...")
    exam_count = 0
    for agent in AGENTS:
        n_exams = random.randint(2, 4)
        for _ in range(n_exams):
            days_back = random.randint(1, 14)
            row = _build_exam_run(agent["id"], agent["name"], agent["role"], days_back)
            cur.execute("""
                INSERT INTO exam_runs
                  (id, agent_id, agent_name, exam_file, exam_id, skill, difficulty,
                   status, auto_score, auto_weight, mentor_score, mentor_weight,
                   total_score, threshold, passed,
                   missed_keywords_json, mentor_criteria_json, mentor_scores_json,
                   output, elapsed_sec, error_msg, prompt_version_id, prompt_version_num,
                   judge_results_json, rules_result_json, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, row)
            exam_count += 1

    conn.commit()
    print(f"  ✓ {exam_count} exam runs inserted")

    # Audit logs
    print("Seeding audit logs...")
    all_audit_rows = []
    for agent in AGENTS:
        all_audit_rows.extend(_generate_audit_rows(agent, n=35))

    insert_sql = """
        INSERT INTO audit_logs
          (id, agent_id, agent_name, conversation_id,
           event_type, tool_name, tool_args_json, result_preview,
           duration_ms, success, error_msg, l2_approved,
           input_tokens, output_tokens, trace_id, node_name, extra_data_json, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    cur.executemany(insert_sql, all_audit_rows)
    conn.commit()
    print(f"  ✓ {len(all_audit_rows)} audit log entries inserted")

    conn.close()
    print("\n✅ Demo seed complete.")
    print(f"   Agents: {len(AGENTS)} ({', '.join(sorted({a['role'] for a in AGENTS}))})")
    print(f"   Conversations: {total_convs}  Messages: {total_msgs}")
    print(f"   Exam runs: {exam_count}")
    print(f"   Audit entries: {len(all_audit_rows)}")


if __name__ == "__main__":
    import sys
    if "--force" in sys.argv:
        conn = sqlite3.connect(DB_PATH)
        agent_ids = [r[0] for r in conn.execute("SELECT id FROM agents WHERE name LIKE '%·%'").fetchall()]
        if agent_ids:
            placeholders = ",".join("?" * len(agent_ids))
            conn.execute(f"DELETE FROM audit_logs WHERE agent_id IN ({placeholders})", agent_ids)
            conn.execute(f"DELETE FROM exam_runs WHERE agent_id IN ({placeholders})", agent_ids)
            conn.execute(f"DELETE FROM conversations WHERE agent_id IN ({placeholders})", agent_ids)
            conn.execute(f"DELETE FROM agents WHERE id IN ({placeholders})", agent_ids)
            conn.commit()
        conn.close()
        print("Cleared existing demo data.")
    seed()
