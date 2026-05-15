"""
Prompt Improvement Suggester.

After a failed exam run, analyzes missed keywords and LLM-as-Judge reasoning
to produce specific, actionable suggestions for improving the system prompt.
Mentor can review and apply suggestions to create a new prompt version with one click.
"""
from __future__ import annotations

import json
import re
from typing import Any


_SUGGESTER_SYSTEM = """\
You are an expert prompt engineer specializing in improving LLM agent system prompts.
Given evidence from a failed exam run (missed keywords, judge scores, agent output),
identify what the current system prompt is missing or doing wrong, and produce
concrete, copy-paste-ready improvements.

Return ONLY valid JSON with this exact structure — no markdown fences, no extra text:
{
  "diagnosis": "<1-2 sentence summary of the root failure cause>",
  "suggestions": [
    {
      "id": "S1",
      "point": "<title: specific problem or missing instruction>",
      "rationale": "<why this caused failure, 1-2 sentences, cite evidence>",
      "patch": "<exact text block to add or change in the prompt>"
    }
  ],
  "patched_prompt": "<full revised prompt with all suggestions incorporated>"
}

Rules:
- 1 to 4 suggestions maximum
- Each patch must be concrete and immediately usable without further editing
- patched_prompt must be the complete, revised prompt — not a diff
- Preserve the original prompt structure; make minimal targeted changes
"""


def build_suggester_prompt(
    current_prompt: str,
    exam_scenario: str,
    input_message: str,
    agent_output: str,
    missed_keywords: list[str],
    judge_results: dict[str, Any],
) -> str:
    """Build the analysis prompt for the suggester LLM. Pure function — no I/O."""
    judge_failures = []
    for criterion, result in judge_results.items():
        score = result.get("score", 0)
        if score < 3:
            reasoning = result.get("reasoning", "")
            evidence  = result.get("evidence", "")
            line = f"  • {criterion}: {score}/3 — {reasoning}"
            if evidence:
                line += f'\n    Evidence: "{evidence[:200]}"'
            judge_failures.append(line)

    judge_section    = "\n".join(judge_failures) if judge_failures else "  (no judge data available)"
    keywords_section = ", ".join(f'"{k}"' for k in missed_keywords) if missed_keywords else "none"

    return f"""## Current System Prompt
{current_prompt[:3000]}

## Exam Details
Scenario: {exam_scenario}
Input given to agent: {input_message[:500]}

## Agent Output (what the agent actually produced)
{agent_output[:1500]}

## Failure Evidence

### Missed Expected Keywords
{keywords_section}

### Judge Scoring (criteria scored below perfect 3/3)
{judge_section}

## Your Task
Based on the failure evidence above, analyze why the current prompt produced this output
and suggest specific improvements. Focus on what behavioral instruction is MISSING or UNCLEAR
in the prompt that caused the agent to miss these keywords or score poorly on these criteria."""


def generate_suggestions(
    current_prompt: str,
    exam_scenario: str,
    input_message: str,
    agent_output: str,
    missed_keywords: list[str],
    judge_results: dict[str, Any],
) -> dict:
    """
    Call LLM to analyze a failed exam run and produce prompt improvement suggestions.

    Returns dict with keys: diagnosis, suggestions (list), patched_prompt.
    On any error, returns a dict with an 'error' key describing what went wrong.
    """
    from config import (
        LLM_PROVIDER, MODEL_NAME,
        ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENAI_BASE_URL,
    )
    from agent.llm_client import call_llm
    from langchain_core.messages import HumanMessage

    prompt = build_suggester_prompt(
        current_prompt, exam_scenario, input_message,
        agent_output, missed_keywords, judge_results,
    )

    try:
        response = call_llm(
            system_prompt=_SUGGESTER_SYSTEM,
            messages=[HumanMessage(content=prompt)],
            tool_definitions=[],
            model=MODEL_NAME,
            provider=LLM_PROVIDER,
            anthropic_api_key=ANTHROPIC_API_KEY,
            openai_api_key=OPENAI_API_KEY,
            openai_base_url=OPENAI_BASE_URL,
            max_tokens=2048,
        )
        raw = response.text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        result = json.loads(raw)
        return {
            "diagnosis":      str(result.get("diagnosis", "")),
            "suggestions":    result.get("suggestions", []),
            "patched_prompt": str(result.get("patched_prompt", current_prompt)),
        }
    except Exception as exc:
        return {
            "error":          str(exc),
            "diagnosis":      "",
            "suggestions":    [],
            "patched_prompt": current_prompt,
        }
