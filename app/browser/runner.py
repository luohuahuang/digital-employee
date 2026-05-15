"""
browser/runner.py — Test run orchestrator

Loads a test run from DB, assembles skills context, executes each case
via CaseExecutor, writes results back to DB, saves screenshots to disk.

Designed to run in a background thread (called from the API handler).
"""
from __future__ import annotations
import json
import os
import uuid
from datetime import datetime, timezone

from browser.actions import BrowserSession
from browser.executor import CaseExecutor


def _screenshot_dir(run_id: str) -> str:
    base = os.path.join(os.path.dirname(__file__), "..", "output", "test_runs", run_id)
    os.makedirs(base, exist_ok=True)
    return os.path.abspath(base)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assemble_skills_context(conn, env_skill_id: str | None, extra_skill_ids: list[str]) -> tuple[str, str]:
    """
    Load skills from DB and assemble a context string to inject into prompts.
    Returns (base_url, context_string).
    base_url is extracted from the environment skill content if present.
    """
    from sqlalchemy import text

    sections = []
    base_url = ""

    # Environment skill (exactly one)
    if env_skill_id:
        row = conn.execute(
            text("SELECT name, content FROM browser_skills WHERE id=:id AND skill_type='environment'"),
            {"id": env_skill_id},
        ).mappings().fetchone()
        if row:
            sections.append(f"## Environment: {row['name']}\n\n{row['content']}")
            # Try to extract base_url from content (look for "base_url: ..." line)
            for line in row["content"].splitlines():
                stripped = line.strip()
                if stripped.lower().startswith("base_url:"):
                    base_url = stripped.split(":", 1)[1].strip().strip('"').strip("'")
                    break

    # Extra skills (zero or more, ordered by name)
    if extra_skill_ids:
        placeholders = ",".join(f":id{i}" for i in range(len(extra_skill_ids)))
        params = {f"id{i}": v for i, v in enumerate(extra_skill_ids)}
        params["type"] = "extra"
        rows = conn.execute(
            text(f"SELECT name, content FROM browser_skills WHERE id IN ({placeholders}) AND skill_type='extra' ORDER BY name"),
            params,
        ).mappings().fetchall()
        for row in rows:
            sections.append(f"## Skill: {row['name']}\n\n{row['content']}")

    return base_url, "\n\n".join(sections)


def run_test_run(run_id: str, db_url: str, api_key: str, model: str = "claude-opus-4-6") -> None:
    """
    Execute a test run end-to-end. Intended to be called in a background thread.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(db_url)

    # ── 1. Load run + skills ───────────────────────────────────────────────────
    with engine.connect() as conn:
        run = conn.execute(
            text("SELECT * FROM test_runs WHERE id = :id"), {"id": run_id}
        ).mappings().fetchone()
        if not run:
            return

        cases = conn.execute(
            text("""
                SELECT tc.*
                FROM test_cases tc
                JOIN test_run_cases trc ON tc.id = trc.case_id
                WHERE trc.run_id = :run_id
                ORDER BY tc.id
            """),
            {"run_id": run_id},
        ).mappings().fetchall()

        # Parse skill IDs stored on the run record
        env_skill_id = run.get("env_skill_id") or None
        extra_skill_ids = []
        raw = run.get("extra_skill_ids") or "[]"
        try:
            extra_skill_ids = json.loads(raw)
        except Exception:
            pass

        base_url_from_skill, skills_context = _assemble_skills_context(
            conn, env_skill_id, extra_skill_ids
        )

    # base_url: prefer value from environment skill, fall back to run record
    base_url = base_url_from_skill or run.get("base_url", "")

    screenshot_dir = _screenshot_dir(run_id)
    executor = CaseExecutor(
        api_key=api_key,
        screenshot_dir=screenshot_dir,
        model=model,
        skills_context=skills_context,
    )

    # ── 2. Mark as running ─────────────────────────────────────────────────────
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE test_runs SET status='running', started_at=:t WHERE id=:id"),
            {"t": _now(), "id": run_id},
        )

    # ── 3. Open browser ────────────────────────────────────────────────────────
    passed_count = 0
    failed_count = 0

    with BrowserSession(headless=True) as session:
        nav = session.navigate(base_url)
        if not nav.success:
            _mark_run_error(engine, run_id, f"Could not navigate to {base_url}: {nav.error}")
            return

        session.wait_for_network_idle()

        # ── 4. Execute each case ───────────────────────────────────────────────
        from web.api.test_runs import _terminate_requests
        for case in cases:
            if run_id in _terminate_requests:
                _terminate_requests.discard(run_id)
                break
            case_dict = dict(case)
            # Convert test_cases.steps (JSON string of plain strings) to the
            # [{description, expected_result}] format the executor expects.
            raw = case_dict.get("steps") or "[]"
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    raw = []
            overall_expected = case_dict.get("expected", "")
            case_dict["steps_json"] = [
                {
                    "description":   (s if isinstance(s, str) else s.get("description", str(s))),
                    "expected_result": overall_expected if i == len(raw) - 1 else "",
                }
                for i, s in enumerate(raw if isinstance(raw, list) else [])
            ]
            result = executor.run(case_dict, session)

            steps_data = []
            screenshot_paths = []
            for s in result.steps:
                steps_data.append({
                    "step_index":    s.step_index,
                    "description":   s.description,
                    "expected":      s.expected_result,
                    "actions_taken": s.actions_taken,
                    "passed":        s.passed,
                    "reason":        s.reason,
                    "error":         s.error,
                    "screenshot_before": s.screenshot_before,
                    "screenshot_after":  s.screenshot_after,
                })
                screenshot_paths.extend([s.screenshot_before, s.screenshot_after])

            if result.status == "pass":
                passed_count += 1
            else:
                failed_count += 1

            with engine.begin() as conn:
                conn.execute(
                    text("""
                        UPDATE test_run_cases
                        SET status=:status, failure_step=:failure_step,
                            actual_result=:actual_result, steps_json=:steps_json,
                            screenshots_json=:screenshots_json, executed_at=:executed_at
                        WHERE run_id=:run_id AND case_id=:case_id
                    """),
                    {
                        "status":           result.status,
                        "failure_step":     result.failure_step,
                        "actual_result":    result.actual_result,
                        "steps_json":       json.dumps(steps_data, ensure_ascii=False),
                        "screenshots_json": json.dumps(screenshot_paths),
                        "executed_at":      result.executed_at,
                        "run_id":           run_id,
                        "case_id":          result.case_id,
                    },
                )
                conn.execute(
                    text("UPDATE test_runs SET passed=:p, failed=:f WHERE id=:id"),
                    {"p": passed_count, "f": failed_count, "id": run_id},
                )

    # ── 5. Mark run complete (skip if already terminated) ─────────────────────
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE test_runs
                SET status='completed', completed_at=:t, passed=:p, failed=:f
                WHERE id=:id AND status != 'terminated'
            """),
            {"t": _now(), "p": passed_count, "f": failed_count, "id": run_id},
        )


def create_run(
    suite_id: str,
    name: str,
    base_url: str,
    db_url: str,
    env_skill_id: str | None = None,
    extra_skill_ids: list[str] | None = None,
    platform: str = "web",
) -> str:
    """
    Create a test_run record and corresponding test_run_cases rows.
    Returns the new run_id.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(db_url)
    run_id = str(uuid.uuid4())
    extra_skill_ids = extra_skill_ids or []

    with engine.connect() as conn:
        cases = conn.execute(
            text("SELECT id, title FROM test_cases WHERE suite_id=:sid ORDER BY id"),
            {"sid": suite_id},
        ).mappings().fetchall()

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO test_runs
                    (id, name, suite_id, base_url, env_skill_id, extra_skill_ids,
                     platform, status, total_cases, passed, failed, created_at)
                VALUES
                    (:id, :name, :suite_id, :base_url, :env_skill_id, :extra_skill_ids,
                     :platform, 'pending', :total, 0, 0, :created_at)
            """),
            {
                "id":              run_id,
                "name":            name,
                "suite_id":        suite_id,
                "base_url":        base_url,
                "env_skill_id":    env_skill_id,
                "extra_skill_ids": json.dumps(extra_skill_ids),
                "platform":        platform,
                "total":           len(cases),
                "created_at":      _now(),
            },
        )
        for case in cases:
            conn.execute(
                text("""
                    INSERT INTO test_run_cases (id, run_id, case_id, case_title, status)
                    VALUES (:id, :run_id, :case_id, :case_title, 'pending')
                """),
                {
                    "id":         str(uuid.uuid4()),
                    "run_id":     run_id,
                    "case_id":    case["id"],
                    "case_title": case["title"],
                },
            )

    return run_id


def _mark_run_error(engine, run_id: str, reason: str) -> None:
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE test_runs SET status='error', completed_at=:t WHERE id=:id"),
            {"t": _now(), "id": run_id},
        )
