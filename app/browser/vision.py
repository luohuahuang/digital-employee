"""
browser/vision.py — LLM vision calls for UI test automation

Two responsibilities:
  1. decide_actions()  — given a screenshot + step description, return the list
                         of browser actions needed to perform that step.
  2. verify_result()   — given a screenshot + expected result, judge pass/fail.

Both call the Anthropic API directly (not through agent.py / llm_client.py)
because they need to pass image content blocks which the existing call_llm
wrapper does not support.
"""
from __future__ import annotations
import json
import re


# ── Prompts ────────────────────────────────────────────────────────────────────

_DECIDE_SYSTEM = """\
You are a UI test automation agent. You are given a screenshot of a web page
and a natural-language test step. Your job is to decide what browser actions
are needed to perform that step.

Return ONLY a JSON object in this exact format (no markdown, no explanation):
{
  "reasoning": "<brief description of what you see and what you plan to do>",
  "actions": [
    {"type": "click",    "x": <int>, "y": <int>,          "description": "<what you are clicking>"},
    {"type": "type",     "text": "<string>"},
    {"type": "press",    "key": "<key name>"},
    {"type": "scroll",   "direction": "down",              "amount": 300},
    {"type": "navigate", "url": "<full url>"},
    {"type": "wait",     "ms": 1000}
  ]
}

Rules:
- x and y coordinates must be within the viewport (1280 x 800).
- Click the CENTER of the target element.
- If the step is purely an assertion (nothing to interact with), return an empty actions list.
- Do not include screenshot or verify actions — those are handled externally.
- Return only valid JSON.
- If skills context is provided below, use it for credentials, URLs, test data, and
  any environment-specific instructions.
"""

_VERIFY_SYSTEM = """\
You are a UI test result verifier. You are given a screenshot of a web page
and an expected result from a test case. Judge whether the current page state
satisfies the expected result.

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
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?", "", text).strip()
    # Find first { ... } block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON object found in LLM response: {text[:200]}")


def _build_prompt(skills_context: str, main_text: str) -> str:
    """Prepend skills context block to a prompt if context is non-empty."""
    if skills_context:
        return "---\n" + skills_context + "\n---\n\n" + main_text
    return main_text


# ── Public API ─────────────────────────────────────────────────────────────────

def decide_actions(
    screenshot_b64: str,
    step_description: str,
    api_key: str,
    model: str = "claude-opus-4-6",
    skills_context: str = "",
) -> list[dict]:
    """
    Given a screenshot and a natural-language step, return the list of
    browser actions needed to perform that step.

    Returns a list of action dicts compatible with BrowserSession.execute_action().
    On failure, returns a single wait action so execution can continue.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=_DECIDE_SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                _image_block(screenshot_b64),
                {
                    "type": "text",
                    "text": _build_prompt(skills_context, f"Test step to perform:\n{step_description}"),
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
                    "text": _build_prompt(skills_context, f"Expected result:\n{expected_result}"),
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
