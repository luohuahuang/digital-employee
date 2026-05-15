"""
android/vision.py — LLM vision calls for Android UI test automation

Two responsibilities:
  1. decide_actions()  — given a screenshot + step description + screen size,
                         return the list of ADB actions needed to perform that step.
  2. verify_result()   — given a screenshot + expected result, judge pass/fail.

Key difference from browser/vision.py:
  - Screen resolution is dynamic (varies by device).
    Width and height are queried from the device at runtime and injected
    into the system prompt so the LLM produces correct coordinates.
  - Action types reflect Android gestures: tap, swipe, long_press, key, launch.
"""
from __future__ import annotations
import json
import re


# ── Prompt templates ───────────────────────────────────────────────────────────

# {width} and {height} are filled in at call time.
_DECIDE_SYSTEM_TEMPLATE = """\
You are an Android UI test automation agent. You are given a screenshot of an
Android device screen ({width} x {height} pixels) and a natural-language test
step. Your job is to decide what ADB actions are needed to perform that step.

Return ONLY a JSON object in this exact format (no markdown, no explanation):
{{
  "reasoning": "<brief description of what you see and what you plan to do>",
  "actions": [
    {{"type": "tap",        "x": <int>, "y": <int>,          "description": "<what you are tapping>"}},
    {{"type": "long_press", "x": <int>, "y": <int>,          "duration_ms": 1000}},
    {{"type": "type",       "text": "<ASCII string>"}},
    {{"type": "key",        "keycode": "<KEYCODE_name>"}},
    {{"type": "swipe",      "x1": <int>, "y1": <int>, "x2": <int>, "y2": <int>, "duration_ms": 300}},
    {{"type": "launch",     "package": "<com.example.app>",  "activity": "<optional>"}},
    {{"type": "wait",       "ms": 1500}}
  ]
}}

Rules:
- Coordinates must be within {width} x {height}.
- Tap the CENTER of the target element.
- To scroll DOWN: swipe upward — x1 == x2, y1 > y2 (e.g. y1=1400, y2=600).
- To scroll UP:   swipe downward — x1 == x2, y1 < y2.
- Use KEYCODE_BACK to dismiss dialogs or navigate back.
- Use KEYCODE_ENTER to submit a focused form field.
- Use KEYCODE_DEL to delete characters.
- If the step is purely an assertion (nothing to interact with), return an empty actions list.
- Do not include screenshot or verify actions — those are handled externally.
- Return only valid JSON.
- If skills context is provided below, use it for credentials, package names,
  test data, and any environment-specific instructions.
"""

_VERIFY_SYSTEM = """\
You are an Android UI test result verifier. You are given a screenshot of an
Android device screen and an expected result from a test case. Judge whether
the current screen state satisfies the expected result.

Return ONLY a JSON object in this exact format (no markdown, no explanation):
{
  "pass": <true or false>,
  "reason": "<one sentence explaining why it passes or fails>"
}

Be strict but fair. Minor visual differences are acceptable if the functional
requirement is met. Return only valid JSON.
"""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _image_block(b64: str) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": b64,
        },
    }


def _parse_json(text: str) -> dict:
    """Extract and parse the first JSON object from an LLM response."""
    text = re.sub(r"```(?:json)?", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON object found in LLM response: {text[:200]}")


def _build_prompt(skills_context: str, main_text: str) -> str:
    """Prepend skills context block to a prompt if context is non-empty."""
    if skills_context:
        return "---\n" + skills_context + "\n---\n\n" + main_text
    return main_text


def _build_decide_system(width: int, height: int) -> str:
    """Render the decide system prompt with actual screen dimensions."""
    return _DECIDE_SYSTEM_TEMPLATE.format(width=width, height=height)


# ── Public API ─────────────────────────────────────────────────────────────────

def decide_actions(
    screenshot_b64: str,
    step_description: str,
    api_key: str,
    screen_size: tuple[int, int],
    model: str = "claude-opus-4-6",
    skills_context: str = "",
) -> list[dict]:
    """
    Given a screenshot, a natural-language step, and the device's screen size,
    return the list of ADB actions needed to perform that step.

    Returns a list of action dicts compatible with AndroidSession.execute_action().
    On failure, returns a single wait action so execution can continue.
    """
    import anthropic

    width, height = screen_size
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=_build_decide_system(width, height),
        messages=[{
            "role": "user",
            "content": [
                _image_block(screenshot_b64),
                {
                    "type": "text",
                    "text": _build_prompt(
                        skills_context,
                        "Test step to perform:\n" + step_description,
                    ),
                },
            ],
        }],
    )

    raw = response.content[0].text if response.content else ""
    try:
        data = _parse_json(raw)
        return data.get("actions", [])
    except Exception as e:
        return [{"type": "wait", "ms": 500, "_parse_error": str(e)}]


def verify_result(
    screenshot_b64: str,
    expected_result: str,
    api_key: str,
    model: str = "claude-opus-4-6",
    skills_context: str = "",
) -> dict:
    """
    Given a screenshot and an expected result string, return:
      {"pass": bool, "reason": str}

    On failure, returns {"pass": False, "reason": "<error>"}.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=256,
        system=_VERIFY_SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                _image_block(screenshot_b64),
                {
                    "type": "text",
                    "text": _build_prompt(
                        skills_context,
                        "Expected result:\n" + expected_result,
                    ),
                },
            ],
        }],
    )

    raw = response.content[0].text if response.content else ""
    try:
        data = _parse_json(raw)
        return {
            "pass": bool(data.get("pass", False)),
            "reason": str(data.get("reason", "")),
        }
    except Exception as e:
        return {"pass": False, "reason": f"Verification error: {e}. Raw: {raw[:100]}"}
