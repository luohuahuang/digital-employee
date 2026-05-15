"""
browser/executor.py — Single test case execution engine

Takes one TestCase, executes all its steps using Playwright + Claude vision,
saves a screenshot per step, and returns a CaseResult.
"""
from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from browser.actions import BrowserSession
from browser import vision


@dataclass
class StepResult:
    step_index: int          # 0-based
    description: str
    expected_result: str
    actions_taken: list[dict]
    screenshot_before: str   # file path
    screenshot_after: str    # file path
    passed: bool
    reason: str
    error: str = ""          # set if an unexpected exception occurred


@dataclass
class CaseResult:
    case_id: str
    case_title: str
    status: str              # "pass" | "fail" | "error"
    steps: list[StepResult] = field(default_factory=list)
    failure_step: int | None = None   # 1-based index of first failing step
    actual_result: str = ""           # human-readable summary
    executed_at: str = ""


class CaseExecutor:
    """
    Executes a single test case against a running browser session.

    Usage:
        executor = CaseExecutor(api_key=..., model=..., screenshot_dir=..., skills_context=...)
        result = executor.run(case_dict, session)
    """

    def __init__(
        self,
        api_key: str,
        screenshot_dir: str,
        model: str = "claude-opus-4-6",
        skills_context: str = "",
    ):
        self.api_key = api_key
        self.model = model
        self.screenshot_dir = screenshot_dir
        self.skills_context = skills_context
        os.makedirs(screenshot_dir, exist_ok=True)

    def run(self, case: dict, session: BrowserSession) -> CaseResult:
        """
        Execute all steps of one test case.

        `case` is a dict with at least:
          - id (str)
          - title (str)
          - steps_json (str | list)  — list of {"description":..., "expected_result":...}
          - preconditions (str, optional)
        """
        case_id = str(case.get("id", "unknown"))
        case_title = case.get("title", "Untitled")
        steps = self._parse_steps(case.get("steps_json", []))

        result = CaseResult(
            case_id=case_id,
            case_title=case_title,
            status="pass",
            executed_at=datetime.now(timezone.utc).isoformat(),
        )

        for i, step in enumerate(steps):
            step_num = i + 1
            description = step.get("description", "")
            expected = step.get("expected_result", "")

            # Screenshot before action
            path_before = os.path.join(
                self.screenshot_dir, f"case_{case_id}_step{step_num:02d}_before.png"
            )
            session.screenshot_save(path_before)
            b64_before = _read_b64(path_before)

            # Ask vision: what actions are needed?
            actions = vision.decide_actions(
                screenshot_b64=b64_before,
                step_description=description,
                api_key=self.api_key,
                model=self.model,
                skills_context=self.skills_context,
            )

            # Execute each action
            action_error = ""
            for action in actions:
                res = session.execute_action(action)
                if not res.success:
                    action_error = res.error
                    break
                # Small pause after click/type to let the page react
                if action.get("type") in ("click", "type", "press"):
                    session.wait(300)

            # Wait for any navigation / XHR to settle
            session.wait_for_network_idle()

            # Screenshot after actions
            path_after = os.path.join(
                self.screenshot_dir, f"case_{case_id}_step{step_num:02d}_after.png"
            )
            session.screenshot_save(path_after)
            b64_after = _read_b64(path_after)

            # Verify expected result
            if expected:
                verification = vision.verify_result(
                    screenshot_b64=b64_after,
                    expected_result=expected,
                    api_key=self.api_key,
                    model=self.model,
                    skills_context=self.skills_context,
                )
                passed = verification["pass"]
                reason = verification["reason"]
            else:
                # No expected result defined — treat action success as pass
                passed = not action_error
                reason = action_error or "No expected result defined; actions completed."

            step_result = StepResult(
                step_index=i,
                description=description,
                expected_result=expected,
                actions_taken=actions,
                screenshot_before=path_before,
                screenshot_after=path_after,
                passed=passed,
                reason=reason,
                error=action_error,
            )
            result.steps.append(step_result)

            if not passed:
                result.status = "fail"
                result.failure_step = step_num
                result.actual_result = reason
                break  # Stop on first failure

        if result.status == "pass":
            result.actual_result = "All steps passed."

        return result

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_steps(steps_json) -> list[dict]:
        if isinstance(steps_json, list):
            return steps_json
        if isinstance(steps_json, str):
            try:
                parsed = json.loads(steps_json)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
        return []


def _read_b64(path: str) -> str:
    """Read a PNG file and return as base64 string."""
    import base64
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
