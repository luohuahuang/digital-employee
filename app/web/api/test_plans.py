"""
Test Plan API endpoints.

Endpoints:
----------
GET    /test-plans                      — list all plans
POST   /test-plans                      — create a plan
GET    /test-plans/{plan_id}            — get plan detail
PUT    /test-plans/{plan_id}            — update plan
DELETE /test-plans/{plan_id}            — delete plan
POST   /test-plans/{plan_id}/execute    — execute plan (creates runs for each suite)
"""
import json
import threading
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from config import ANTHROPIC_API_KEY, WEB_DB_PATH
from web.db.database import engine

router = APIRouter(tags=["test_plans"])

DB_URL = f"sqlite:///{WEB_DB_PATH}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Pydantic models ────────────────────────────────────────────────────────────

class PlanCreateBody(BaseModel):
    name: str
    description: str = ""
    suite_ids: list[str] = []
    env_skill_id: str = ""
    extra_skill_ids: list[str] = []
    platform: str = "web"


class PlanUpdateBody(BaseModel):
    name: str | None = None
    description: str | None = None
    suite_ids: list[str] | None = None
    env_skill_id: str | None = None
    extra_skill_ids: list[str] | None = None
    platform: str | None = None


class ExecutePlanBody(BaseModel):
    batch_name: str
    env_skill_id: str = ""
    extra_skill_ids: list[str] = []
    platform: str | None = None   # overrides plan's platform if set


# ── Helpers ────────────────────────────────────────────────────────────────────

def _row_to_dict(row) -> dict:
    d = dict(row)
    for field in ("suite_ids", "extra_skill_ids"):
        if d.get(field):
            try:
                d[field] = json.loads(d[field])
            except Exception:
                d[field] = []
        else:
            d[field] = []
    return d


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/test-plans")
def list_plans():
    """List all test plans newest first."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM test_plans ORDER BY created_at DESC")
        ).mappings().fetchall()
    return [_row_to_dict(r) for r in rows]


@router.post("/test-plans", status_code=201)
def create_plan(body: PlanCreateBody):
    """Create a new test plan."""
    plan_id = str(uuid.uuid4())
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO test_plans
                    (id, name, description, suite_ids, env_skill_id, extra_skill_ids, platform, created_at, updated_at)
                VALUES
                    (:id, :name, :desc, :suite_ids, :env, :extra, :platform, :now, :now)
            """),
            {
                "id": plan_id,
                "name": body.name,
                "desc": body.description,
                "suite_ids": json.dumps(body.suite_ids),
                "env": body.env_skill_id,
                "extra": json.dumps(body.extra_skill_ids),
                "platform": body.platform,
                "now": now,
            },
        )
        row = conn.execute(
            text("SELECT * FROM test_plans WHERE id = :id"), {"id": plan_id}
        ).mappings().fetchone()
    return _row_to_dict(row)


@router.get("/test-plans/{plan_id}")
def get_plan(plan_id: str):
    """Get a single test plan."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM test_plans WHERE id = :id"), {"id": plan_id}
        ).mappings().fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Plan not found")
    return _row_to_dict(row)


@router.put("/test-plans/{plan_id}")
def update_plan(plan_id: str, body: PlanUpdateBody):
    """Update a test plan."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM test_plans WHERE id = :id"), {"id": plan_id}
        ).mappings().fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Plan not found")

    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
    if body.suite_ids is not None:
        updates["suite_ids"] = json.dumps(body.suite_ids)
    if body.env_skill_id is not None:
        updates["env_skill_id"] = body.env_skill_id
    if body.extra_skill_ids is not None:
        updates["extra_skill_ids"] = json.dumps(body.extra_skill_ids)
    if body.platform is not None:
        updates["platform"] = body.platform
    updates["updated_at"] = _now()

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["plan_id"] = plan_id
    with engine.begin() as conn:
        conn.execute(
            text(f"UPDATE test_plans SET {set_clause} WHERE id = :plan_id"), updates
        )
        row = conn.execute(
            text("SELECT * FROM test_plans WHERE id = :id"), {"id": plan_id}
        ).mappings().fetchone()
    return _row_to_dict(row)


@router.delete("/test-plans/{plan_id}", status_code=204)
def delete_plan(plan_id: str):
    """Delete a test plan."""
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM test_plans WHERE id = :id"), {"id": plan_id}
        )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Plan not found")


@router.post("/test-plans/{plan_id}/execute")
def execute_plan(plan_id: str, body: ExecutePlanBody):
    """
    Execute a test plan — creates one test run per suite and starts background threads.
    Returns list of {run_id, suite_id, suite_name}.
    """
    from browser.runner import create_run

    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    with engine.connect() as conn:
        plan = conn.execute(
            text("SELECT * FROM test_plans WHERE id = :id"), {"id": plan_id}
        ).mappings().fetchone()
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        plan_dict = _row_to_dict(plan)
        suite_ids = plan_dict["suite_ids"]
        if not suite_ids:
            raise HTTPException(status_code=400, detail="Plan has no suites")

        platform = body.platform or plan_dict.get("platform", "web")
        env_skill_id = body.env_skill_id or plan_dict.get("env_skill_id", "") or None
        extra_skill_ids = body.extra_skill_ids or plan_dict.get("extra_skill_ids", [])

        # Look up suite names and validate case counts
        started = []
        for suite_id in suite_ids:
            suite = conn.execute(
                text("SELECT id, name FROM test_suites WHERE id = :id"), {"id": suite_id}
            ).mappings().fetchone()
            if not suite:
                continue
            case_count = conn.execute(
                text("SELECT COUNT(*) as n FROM test_cases WHERE suite_id = :id"),
                {"id": suite_id},
            ).mappings().fetchone()["n"]
            if case_count == 0:
                continue

            run_name = f"{body.batch_name} — {suite['name']}"
            run_id = create_run(
                suite_id=suite_id,
                name=run_name,
                base_url="",
                db_url=DB_URL,
                env_skill_id=env_skill_id,
                extra_skill_ids=extra_skill_ids,
                platform=platform,
            )
            started.append({"run_id": run_id, "suite_id": suite_id, "suite_name": suite["name"]})

    if not started:
        raise HTTPException(status_code=400, detail="No runnable suites found in plan")

    # Launch background threads
    if platform == "android":
        from android.runner import run_test_run as _run
    else:
        from browser.runner import run_test_run as _run

    for item in started:
        thread = threading.Thread(
            target=_run,
            args=(item["run_id"], DB_URL, ANTHROPIC_API_KEY),
            daemon=True,
        )
        thread.start()

    return {"runs": started, "platform": platform}
