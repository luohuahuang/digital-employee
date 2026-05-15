"""
android/runner.py — Android test run orchestrator

Loads a test run from DB, assembles skills context, launches the app on the
Android device, executes each case via AndroidCaseExecutor, writes results
back to DB, and saves screenshots to disk.

Designed to run in a background thread (called from the API handler).
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone

from android.actions import AndroidSession
from android.executor import AndroidCaseExecutor


def _screenshot_dir(run_id: str) -> str:
    base = os.path.join(os.path.dirname(__file__), "..", "output", "test_runs", run_id)
    os.makedirs(base, exist_ok=True)
    return os.path.abspath(base)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_field(content: str, field: str) -> str:
    """
    Extract a single-line value from skill content.
    Looks for lines like:  field: value  (case-insensitive key match).
    Returns empty string if not found.
    """
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith(field.lower() + ":"):
            return stripped.split(":", 1)[1].strip().strip('"').strip("'")
    return ""


def run_test_run(run_id: str, db_url: str, api_key: str, model: str = "claude-opus-4-6") -> None:
    """
    Execute an Android test run end-to-end.
    Intended to be called in a background thread.
    """
    from sqlalchemy import create_engine, text
    # Reuse skills assembly from the browser runner
    from browser.runner import _assemble_skills_context

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

        env_skill_id = run.get("env_skill_id") or None
        extra_skill_ids = []
        try:
            extra_skill_ids = json.loads(run.get("extra_skill_ids") or "[]")
        except Exception:
            pass

        _, skills_context = _assemble_skills_context(conn, env_skill_id, extra_skill_ids)

        # Extract Android-specific fields from environment skill
        device_serial = None
        app_package = None
        app_activity = None
        if env_skill_id:
            env_row = conn.execute(
                text("SELECT content FROM browser_skills WHERE id=:id AND skill_type='environment'"),
                {"id": env_skill_id},
            ).mappings().fetchone()
            if env_row:
                content = env_row["content"]
                device_serial = _extract_field(content, "device_serial") or None
                app_package = _extract_field(content, "app_package") or None
                app_activity = _extract_field(content, "app_main_activity") or None

    if not app_package:
        _mark_run_error(engine, run_id, "No app_package found in environment skill. "
                        "Add 'app_package: com.your.app' to the skill content.")
        return

    screenshot_dir = _screenshot_dir(run_id)
    executor = AndroidCaseExecutor(
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

    # ── 3. Open ADB session and launch app ─────────────────────────────────────
    passed_count = 0
    failed_count = 0

    session = AndroidSession(device_serial=device_serial)
    launch_result = session.launch_app(app_package, app_activity)
    if not launch_result.success:
        _mark_run_error(engine, run_id,
                        f"Could not launch {app_package}: {launch_result.error}")
        return

    # Give the app a moment to fully start before the first test
    session.wait(2000)

    # ── 4. Execute each case ───────────────────────────────────────────────────
    from web.api.test_runs import _terminate_requests
    try:
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
                    "description":    (s if isinstance(s, str) else s.get("description", str(s))),
                    "expected_result": overall_expected if i == len(raw) - 1 else "",
                }
                for i, s in enumerate(raw if isinstance(raw, list) else [])
            ]
            result = executor.run(case_dict, session)

            steps_data = []
            screenshot_paths = []
            for s in result.steps:
                steps_data.append({
                    "step_index":        s.step_index,
                    "description":       s.description,
                    "expected":          s.expected_result,
                    "actions_taken":     s.actions_taken,
                    "passed":            s.passed,
                    "reason":            s.reason,
                    "error":             s.error,
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
    finally:
        pass  # AndroidSession needs no explicit close (no persistent process)

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


def _mark_run_error(engine, run_id: str, reason: str) -> None:
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE test_runs SET status='error', completed_at=:t WHERE id=:id"),
            {"t": _now(), "id": run_id},
        )
