"""
Seed Test Platform data: test plans + 30 historical test runs with case results.

Run from app/ directory:  python3 seed_test_platform.py
"""
import sqlite3
import json
import uuid
import random
from datetime import datetime, timedelta, timezone

DB_PATH = "web/de_team.db"
random.seed(42)

NOW = datetime.now(timezone.utc)

def ts(offset_days=0, offset_hours=0):
    return (NOW - timedelta(days=offset_days, hours=offset_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

def ts_offset(base_days, jitter_hours=0):
    h = random.uniform(-jitter_hours, jitter_hours)
    return (NOW - timedelta(days=base_days, hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")

# ── Load existing data ─────────────────────────────────────────────────────────

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT id, name, component FROM test_suites")
suites = [dict(r) for r in cur.fetchall()]

cur.execute("SELECT id, suite_id, title, priority FROM test_cases")
cases = [dict(r) for r in cur.fetchall()]

# Group cases by suite
cases_by_suite = {}
for c in cases:
    cases_by_suite.setdefault(c["suite_id"], []).append(c)

print(f"Found {len(suites)} test suites, {len(cases)} test cases")

if not suites:
    print("No test suites found — run seed_test_suites.py first!")
    conn.close()
    exit(1)

# ── Helper: find suite by name fragment ───────────────────────────────────────

def find_suite(fragment):
    fragment = fragment.lower()
    for s in suites:
        if fragment in s["name"].lower():
            return s
    return None

# ── 1. Create test_plans ───────────────────────────────────────────────────────

cur.execute("DELETE FROM test_plans")

checkout_suite  = find_suite("checkout — order")
cart_suite      = find_suite("cart management")
payment_suite   = find_suite("shopee pay wallet")
credit_suite    = find_suite("credit card")
promo_suite     = find_suite("platform voucher")
flash_suite     = find_suite("flash sale")
logistics_suite = find_suite("order tracking")
return_suite    = find_suite("return & refund")
auth_suite      = find_suite("registration")
search_suite    = find_suite("keyword search")
mall_suite      = find_suite("shopee mall")

def plan_suite_ids(*fragments):
    ids = []
    for f in fragments:
        s = find_suite(f)
        if s:
            ids.append(s["id"])
    return ids

PLANS = [
    {
        "id": str(uuid.uuid4()),
        "name": "Sprint 34 — Full Regression",
        "description": "Complete regression covering all major product lines ahead of Sprint 34 release.",
        "suite_ids": plan_suite_ids("order placement", "cart management", "shopee pay wallet", "platform voucher", "order tracking"),
        "platform": "web",
        "created_at": ts(14),
    },
    {
        "id": str(uuid.uuid4()),
        "name": "P0 Smoke Test — Pre-Release",
        "description": "Critical path smoke tests run before every production deployment.",
        "suite_ids": plan_suite_ids("order placement", "shopee pay wallet", "registration"),
        "platform": "web",
        "created_at": ts(10),
    },
    {
        "id": str(uuid.uuid4()),
        "name": "Payment Gateway Release QA",
        "description": "End-to-end tests for the payment gateway upgrade (ShopeePay + Credit Card).",
        "suite_ids": plan_suite_ids("shopee pay wallet", "credit card"),
        "platform": "web",
        "created_at": ts(7),
    },
    {
        "id": str(uuid.uuid4()),
        "name": "Promotions Sprint Verification",
        "description": "Voucher redemption, flash sale mechanics, and coins earn/redeem flows.",
        "suite_ids": plan_suite_ids("platform voucher", "flash sale", "shopee coins"),
        "platform": "web",
        "created_at": ts(5),
    },
    {
        "id": str(uuid.uuid4()),
        "name": "Android Checkout Smoke",
        "description": "Android native app checkout flow — ADB-based E2E.",
        "suite_ids": plan_suite_ids("order placement", "cart management"),
        "platform": "android",
        "created_at": ts(3),
    },
]

for p in PLANS:
    cur.execute("""
        INSERT OR REPLACE INTO test_plans
            (id, name, description, suite_ids, env_skill_id, extra_skill_ids, platform, created_at, updated_at)
        VALUES (?, ?, ?, ?, '', '[]', ?, ?, ?)
    """, (
        p["id"], p["name"], p["description"],
        json.dumps([s for s in p["suite_ids"] if s]),
        p["platform"], p["created_at"], p["created_at"],
    ))

conn.commit()
print(f"Created {len(PLANS)} test plans")

# ── 2. Create test_runs + test_run_cases ───────────────────────────────────────

cur.execute("DELETE FROM test_run_cases")
cur.execute("DELETE FROM test_runs")

# Define run scenarios: (suite_fragment, day_offset, pass_rate_pct, platform)
# Improving trend: older runs have lower pass rates
RUN_SCENARIOS = [
    # Sprint 32 (58-45 days ago) — rough start, ~72% pass rate
    ("order placement",   58, 68, "web"),
    ("shopee pay wallet", 57, 72, "web"),
    ("cart management",   56, 70, "web"),
    ("platform voucher",  55, 65, "web"),
    ("order tracking",    54, 74, "web"),
    ("registration",      53, 78, "web"),

    # Sprint 33 (42-28 days ago) — improving, ~82%
    ("order placement",   42, 83, "web"),
    ("shopee pay wallet", 41, 80, "web"),
    ("cart management",   40, 85, "web"),
    ("platform voucher",  39, 82, "web"),
    ("flash sale",        38, 76, "web"),
    ("credit card",       37, 88, "web"),
    ("order tracking",    36, 84, "web"),
    ("return & refund",   35, 79, "web"),
    ("registration",      34, 90, "web"),
    ("keyword search",    33, 82, "web"),

    # Mid-sprint hotfixes (25-18 days ago) — payment regression
    ("shopee pay wallet", 25, 60, "web"),   # regression
    ("credit card",       24, 55, "web"),   # regression
    ("shopee pay wallet", 22, 75, "web"),   # after fix
    ("credit card",       21, 88, "web"),   # after fix

    # Sprint 34 (14-4 days ago) — strong finish, ~90%
    ("order placement",   14, 92, "web"),
    ("shopee pay wallet", 13, 91, "web"),
    ("cart management",   12, 94, "web"),
    ("platform voucher",  11, 89, "web"),
    ("flash sale",        10, 86, "web"),
    ("credit card",       9,  95, "web"),
    ("order tracking",    8,  90, "web"),
    ("return & refund",   7,  88, "web"),
    ("registration",      6,  96, "web"),
    ("keyword search",    5,  93, "web"),
    ("shopee mall",       4,  91, "web"),
    ("android — order",   3,  80, "android"),

    # This week
    ("order placement",   1,  97, "web"),
    ("shopee pay wallet", 1,  94, "web"),
]

SPRINT_LABELS = {
    range(45, 65): "Sprint 32",
    range(28, 45): "Sprint 33",
    range(15, 28): "Hotfix",
    range(4, 15):  "Sprint 34",
    range(0, 4):   "Sprint 34 Final",
}

def get_sprint_label(day_offset):
    for r, label in SPRINT_LABELS.items():
        if day_offset in r:
            return label
    return "Sprint 34"

FAILURE_CASES = [
    "Payment fails when ShopeePay balance is exactly equal to order total",
    "3DS verification loop when card is issued by DBS",
    "Voucher code field clears when user changes shipping address",
    "Flash sale countdown timer out of sync on slow connections",
    "Order total recalculates incorrectly after removing voucher",
    "Cart badge count not updated after adding item from product detail page",
    "Login redirect broken after OAuth token refresh",
    "Search results page paginator skips page 3",
    "Return request form throws 500 on file upload > 2MB",
    "ShopeePay wallet balance shows stale amount after top-up",
]

STEP_TEMPLATES = [
    {"description": "Navigate to the feature page", "expected": "Page loads within 3 seconds", "actions_taken": [{"type": "navigate", "url": "https://staging.shopee.sg/checkout"}]},
    {"description": "Perform primary user action", "expected": "Action completes successfully", "actions_taken": [{"type": "click", "x": 640, "y": 400}]},
    {"description": "Enter required data fields", "expected": "Data accepted and validated", "actions_taken": [{"type": "type", "text": "test data"}]},
    {"description": "Submit the form or confirm action", "expected": "Confirmation message shown", "actions_taken": [{"type": "click", "x": 640, "y": 520}]},
    {"description": "Verify success state", "expected": "Success state displayed correctly", "actions_taken": []},
]

run_count = 0
case_count = 0

for suite_frag, day_offset, pass_rate_pct, platform in RUN_SCENARIOS:
    suite = find_suite(suite_frag)
    if not suite:
        continue

    suite_id = suite["id"]
    suite_name = suite["name"]
    sprint = get_sprint_label(day_offset)
    run_name = f"{sprint} — {suite_name}"
    run_id = str(uuid.uuid4())
    created_at = ts_offset(day_offset, jitter_hours=6)
    completed_at = ts_offset(day_offset - 0.1)

    # Get cases for this suite
    suite_cases = cases_by_suite.get(suite_id, [])
    if not suite_cases:
        continue

    total = len(suite_cases)
    passed = round(total * pass_rate_pct / 100)
    failed = total - passed

    # Shuffle to decide which cases fail
    shuffled = suite_cases[:]
    random.shuffle(shuffled)
    failing_cases = set(c["id"] for c in shuffled[:failed])

    # Insert test run
    cur.execute("""
        INSERT OR REPLACE INTO test_runs
            (id, name, suite_id, suite_name, base_url, platform, status,
             total_cases, passed, failed, created_at, started_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?)
    """, (
        run_id, run_name, suite_id, suite_name,
        "https://staging.shopee.sg", platform,
        total, passed, failed,
        created_at, created_at, completed_at,
    ))

    # Insert test_run_cases
    for tc in suite_cases:
        tc_id = tc["id"]
        is_fail = tc_id in failing_cases
        status = "fail" if is_fail else "pass"

        # Build steps
        steps = []
        num_steps = random.randint(3, 5)
        for si in range(num_steps):
            tmpl = STEP_TEMPLATES[si % len(STEP_TEMPLATES)]
            step_passed = True
            step_reason = "Verification passed as expected."
            step_error = None

            if is_fail and si == num_steps - 1:
                step_passed = False
                step_reason = None
                step_error = random.choice(FAILURE_CASES)

            steps.append({
                "step_index": si,
                "description": tmpl["description"],
                "expected": tmpl["expected"],
                "actions_taken": tmpl["actions_taken"],
                "passed": step_passed,
                "reason": step_reason,
                "error": step_error,
                "screenshot_before": None,
                "screenshot_after": None,
            })

        failure_step = (num_steps - 1) if is_fail else None
        actual_result = (
            f"All {num_steps} steps passed successfully."
            if not is_fail
            else f"Failed at step {num_steps}: {steps[-1]['error']}"
        )

        run_case_id = str(uuid.uuid4())
        cur.execute("""
            INSERT OR REPLACE INTO test_run_cases
                (id, run_id, case_id, case_title, status, failure_step,
                 actual_result, steps_json, screenshots_json, executed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, '[]', ?)
        """, (
            run_case_id, run_id, tc_id, tc["title"],
            status, failure_step,
            actual_result,
            json.dumps(steps, ensure_ascii=False),
            completed_at,
        ))
        case_count += 1

    run_count += 1

conn.commit()
print(f"Created {run_count} test runs with {case_count} case results")

# ── 3. Print summary ──────────────────────────────────────────────────────────

cur.execute("SELECT COUNT(*) FROM test_plans")
print(f"\nFinal counts:")
print(f"  test_plans:     {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM test_runs")
print(f"  test_runs:      {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM test_run_cases")
print(f"  test_run_cases: {cur.fetchone()[0]}")

conn.close()
print("\nDone! Refresh the Test Platform → Analytics tab to see the data.")
