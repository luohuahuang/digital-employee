"""
android/executor.py — Single test case execution engine for Android

Takes one TestCase dict, executes all its steps using ADB + Claude vision,
saves a screenshot per step, and returns a CaseResult.

Mirrors browser/executor.py with two key differences:
  1. Screen size is queried once per case and passed to decide_actions().
  2. Fixed post-action wait instead of wait_for_network_idle()
     (Android rendering has no network-idle equivalent).
"""
from __future__ import annotations
import base64
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from android.actions import AndroidSession
from android import vision


@dataclass
class StepResult:
    step_index: int           # 0-based
    description: str
    expected_result: str
    actions_taken: list[dict]
    screenshot_before: str    # file path
    screenshot_after: str     # file path
    passed: bool
    reason: str
    error: str = ""


@dataclass
class CaseResult:
    case_id: str
    case_title: str
    status: str               # "pass" | "fail" | "error"
    steps: list[StepResult] = field(default_factory=list)
    failure_step: int | None = None   # 1-based index of first failing step
    actual_result: str = ""
    executed_at: str = ""


class AndroidCaseExecutor:
    """
    Executes a single test case against a running AndroidSession.

    Usage:
        executor = AndroidCaseExecutor(api_key=..., model=..., screenshot_dir=...)
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

    def run(self, case: dict, session: AndroidSession) -> CaseResult:
        """
        Execute all steps of one test case.

        `case` is a dict with at least:
          - id (str)
          - title (str)
          - steps_json or steps (str | list) — list of
            {"description": ..., "expected_result": ...}
        """
        case_id = str(case.get("id", "unknown"))
        case_title = case.get("title", "Untitled")
        steps = self._parse_steps(case.get("steps_json") or case.get("steps", []))

        # Query screen size once — used for every decide_actions call this case
        screen_size = session.get_screen_size()

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
                self.screenshot_dir,
                f"case_{case_id}_step{step_num:02d}_before.png",
            )
            session.screenshot_save(path_before)
            b64_before = _read_b64(path_before)

            # Ask vision: what ADB actions are needed?
            actions = vision.decide_actions(
                screenshot_b64=b64_before,
                step_description=description,
                api_key=self.api_key,
                screen_size=screen_size,
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
                # Android UI needs more time to settle than a browser
                if action.get("type") in ("tap", "type", "key", "long_press"):
                    session.wait(500)

            # Fixed wait for Android rendering / animations to complete
            session.wait(800)

            # Screenshot after actions
            path_after = os.path.join(
                self.screenshot_dir,
                f"case_{case_id}_step{step_num:02d}_after.png",
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
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
