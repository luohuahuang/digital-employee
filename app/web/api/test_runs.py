"""
Test Run API endpoints.

Endpoints:
----------
POST   /test-runs                                  — create run + start execution (background)
GET    /test-runs                                  — list all runs (newest first)
GET    /test-runs/{run_id}                         — get run status + case results
GET    /test-runs/{run_id}/cases/{case_id}/screenshots  — list screenshot paths for a case
GET    /test-runs/screenshots/{run_id}/{filename}  — serve a screenshot file
"""
import json
import os
import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text

from config import ANTHROPIC_API_KEY, WEB_DB_PATH
from web.db.database import engine

router = APIRouter(tags=["test_runs"])

DB_URL = f"sqlite:///{WEB_DB_PATH}"
SCREENSHOTS_BASE = os.path.join(os.path.dirname(__file__), "..", "..", "output", "test_runs")

# Shared set — runner threads poll this between cases
_terminate_requests: set[str] = set()


# ── Pydantic Models ────────────────────────────────────────────────────────────

class StartRunRequest(BaseModel):
    suite_id: str
    name: str
    env_skill_id: str | None = None
    extra_skill_ids: list[str] = []
    platform: str = "web"   # "web" | "android"


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/test-runs")
def start_run(body: StartRunRequest):
    """Create a test run and start execution in the background."""
    from browser.runner import create_run

    platform = body.platform if body.platform in ("web", "android") else "web"

    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    # Validate suite exists and has cases
    with engine.connect() as conn:
        suite = conn.execute(
            text("SELECT id, title FROM test_suites WHERE id = :id"),
            {"id": body.suite_id},
        ).mappings().fetchone()
        if not suite:
            raise HTTPException(status_code=404, detail="Test suite not found")

        case_count = conn.execute(
            text("SELECT COUNT(*) as n FROM test_cases WHERE suite_id = :id"),
            {"id": body.suite_id},
        ).mappings().fetchone()["n"]
        if case_count == 0:
            raise HTTPException(status_code=400, detail="Suite has no test cases")

    run_id = create_run(
        suite_id=body.suite_id,
        name=body.name,
        base_url="",          # extracted from env skill at execution time
        db_url=DB_URL,
        env_skill_id=body.env_skill_id,
        extra_skill_ids=body.extra_skill_ids,
        platform=platform,
    )

    # Route to the appropriate runner
    if platform == "android":
        from android.runner import run_test_run as android_run
        target = android_run
    else:
        from browser.runner import run_test_run as web_run
        target = web_run

    thread = threading.Thread(
        target=target,
        args=(run_id, DB_URL, ANTHROPIC_API_KEY),
        daemon=True,
    )
    thread.start()

    return {"run_id": run_id, "status": "running", "platform": platform}


@router.get("/test-runs/analytics")
def get_analytics():
    """Return aggregate analytics for the Test Platform dashboard."""
    with engine.connect() as conn:
        summary = conn.execute(text("""
            SELECT
                COUNT(*) as total_runs,
                COALESCE(SUM(total_cases), 0) as total_cases,
                COALESCE(SUM(passed), 0) as total_passed,
                COALESCE(SUM(failed), 0) as total_failed
            FROM test_runs WHERE status = 'completed'
        """)).mappings().fetchone()

        suite_rows = conn.execute(text("""
            SELECT
                tr.suite_id,
                COALESCE(ts.name, tr.suite_name, 'Unknown') as suite_name,
                COUNT(*) as run_count,
                COALESCE(SUM(tr.total_cases), 0) as total_cases,
                COALESCE(SUM(tr.passed), 0) as passed
            FROM test_runs tr
            LEFT JOIN test_suites ts ON ts.id = tr.suite_id
            WHERE tr.status = 'completed' AND tr.total_cases > 0
            GROUP BY tr.suite_id
            ORDER BY run_count DESC
            LIMIT 12
        """)).mappings().fetchall()

        trend_rows = conn.execute(text("""
            SELECT
                substr(created_at, 1, 10) as day,
                COUNT(*) as runs,
                COALESCE(SUM(passed), 0) as passed,
                COALESCE(SUM(total_cases), 0) as total
            FROM test_runs
            WHERE status = 'completed'
                AND created_at >= datetime('now', '-60 days')
            GROUP BY day
            ORDER BY day ASC
        """)).mappings().fetchall()

        failure_rows = conn.execute(text("""
            SELECT case_title, COUNT(*) as fail_count
            FROM test_run_cases
            WHERE status IN ('fail', 'error') AND case_title IS NOT NULL AND case_title != ''
            GROUP BY case_title
            ORDER BY fail_count DESC
            LIMIT 8
        """)).mappings().fetchall()

        status_rows = conn.execute(text("""
            SELECT status, COUNT(*) as cnt FROM test_runs GROUP BY status
        """)).mappings().fetchall()

    total_cases = summary["total_cases"] or 0
    total_passed = summary["total_passed"] or 0
    overall_rate = round(total_passed / total_cases * 100, 1) if total_cases > 0 else 0

    suite_stats = []
    for r in suite_rows:
        tc = r["total_cases"] or 0
        p = r["passed"] or 0
        suite_stats.append({
            "suite_id": r["suite_id"],
            "suite_name": r["suite_name"],
            "run_count": r["run_count"],
            "total_cases": tc,
            "passed": p,
            "pass_rate": round(p / tc * 100, 1) if tc > 0 else 0,
        })

    daily_trend = []
    for r in trend_rows:
        t = r["total"] or 0
        p = r["passed"] or 0
        daily_trend.append({
            "day": r["day"],
            "runs": r["runs"],
            "pass_rate": round(p / t * 100, 1) if t > 0 else 0,
        })

    return {
        "total_runs": summary["total_runs"] or 0,
        "total_cases_executed": total_cases,
        "total_passed": total_passed,
        "total_failed": summary["total_failed"] or 0,
        "overall_pass_rate": overall_rate,
        "suite_stats": suite_stats,
        "daily_trend": daily_trend,
        "top_failures": [dict(r) for r in failure_rows],
        "status_breakdown": {r["status"]: r["cnt"] for r in status_rows},
    }


@router.get("/test-runs")
def list_runs(
    suite_id: str = None,
    status: str = None,
    platform: str = None,
    limit: int = 100,
):
    """List test runs with optional filters."""
    conditions = []
    params = {}
    if suite_id:
        conditions.append("tr.suite_id = :suite_id")
        params["suite_id"] = suite_id
    if status:
        conditions.append("tr.status = :status")
        params["status"] = status
    if platform:
        conditions.append("tr.platform = :platform")
        params["platform"] = platform

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params["limit"] = min(limit, 500)

    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT tr.*,
                       COALESCE(ts.name, tr.suite_name, '') as suite_name_resolved
                FROM test_runs tr
                LEFT JOIN test_suites ts ON ts.id = tr.suite_id
                {where}
                ORDER BY tr.created_at DESC
                LIMIT :limit
            """),
            params,
        ).mappings().fetchall()

    result = []
    for r in rows:
        d = dict(r)
        d["suite_name"] = d.pop("suite_name_resolved", d.get("suite_name", ""))
        result.append(d)
    return result


@router.post("/test-runs/{run_id}/terminate")
def terminate_run(run_id: str):
    """Signal a running test run to stop after the current case and mark it as terminated."""
    with engine.connect() as conn:
        run = conn.execute(
            text("SELECT status FROM test_runs WHERE id = :id"), {"id": run_id}
        ).mappings().fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        if run["status"] not in ("running", "pending"):
            raise HTTPException(status_code=400, detail=f"Run is not active (status: {run['status']})")

    # Mark in DB immediately so polling UI sees the change right away
    from datetime import datetime, timezone
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE test_runs SET status='terminated', completed_at=:t WHERE id=:id"),
            {"t": datetime.now(timezone.utc).isoformat(), "id": run_id},
        )

    # Signal the background thread to stop between cases
    _terminate_requests.add(run_id)
    return {"run_id": run_id, "status": "terminated"}


@router.get("/test-runs/{run_id}")
def get_run(run_id: str):
    """Get a test run with all case results."""
    with engine.connect() as conn:
        run = conn.execute(
            text("SELECT * FROM test_runs WHERE id = :id"),
            {"id": run_id},
        ).mappings().fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        cases = conn.execute(
            text("SELECT * FROM test_run_cases WHERE run_id = :id ORDER BY case_id"),
            {"id": run_id},
        ).mappings().fetchall()

    run_dict = dict(run)
    cases_list = []
    for c in cases:
        c_dict = dict(c)
        # Parse steps_json and screenshots_json for the frontend
        for field in ("steps_json", "screenshots_json"):
            if c_dict.get(field):
                try:
                    c_dict[field] = json.loads(c_dict[field])
                except Exception:
                    pass
        cases_list.append(c_dict)

    run_dict["cases"] = cases_list
    return run_dict


@router.get("/test-runs/{run_id}/cases/{case_id}/screenshots")
def get_case_screenshots(run_id: str, case_id: str):
    """Return list of screenshot URLs for a specific case."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT screenshots_json FROM test_run_cases WHERE run_id=:r AND case_id=:c"),
            {"r": run_id, "c": case_id},
        ).mappings().fetchone()

    if not row or not row["screenshots_json"]:
        return {"screenshots": []}

    try:
        paths = json.loads(row["screenshots_json"])
    except Exception:
        return {"screenshots": []}

    # Convert absolute paths to API URLs
    urls = []
    for p in paths:
        filename = os.path.basename(p)
        urls.append(f"/api/test-runs/screenshots/{run_id}/{filename}")

    return {"screenshots": urls}


@router.get("/test-runs/screenshots/{run_id}/{filename}")
def serve_screenshot(run_id: str, filename: str):
    """Serve a screenshot file."""
    # Sanitize to prevent path traversal
    filename = os.path.basename(filename)
    path = os.path.join(SCREENSHOTS_BASE, run_id, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(path, media_type="image/png")
