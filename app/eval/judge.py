"""
LLM-as-Judge evaluator for Exam Platform.

Two responsibilities:
  1. evaluate_rules()    — pure string matching, no LLM
  2. evaluate_criteria() — LLM call that scores each rubric criterion 0–3
                           with evidence + reasoning
  3. judge_to_score()    — convert per-criterion results to weighted 0–100 score
"""
from __future__ import annotations

import json
import re
from typing import Any


# ── Layer 1: Rule Checks ──────────────────────────────────────────────────────

def evaluate_rules(output: str, rules: list[dict]) -> list[dict]:
    """
    Evaluate hard-coded rules against agent output.

    Supported rule types:
      - contains_any: pass if output contains at least one of the given values
        (case-insensitive)

    Returns list of {rule, passed, message}.
    """
    results = []
    for rule in rules:
        rule_type = rule.get("type", "")
        if rule_type == "contains_any":
            values     = [str(v) for v in rule.get("values", [])]
            lower_out  = output.lower()
            found      = [v for v in values if v.lower() in lower_out]
            passed     = len(found) > 0
            rule_label = f"contains_any:{'/'.join(values)}"
            message    = f"Found: {', '.join(repr(f) for f in found)}" if passed else rule.get("fail_message", "Not found")
            results.append({"rule": rule_label, "passed": passed, "message": message})
        # Future rule types can be added here
    return results


# ── Layer 2: LLM-as-Judge ────────────────────────────────────────────────────

_JUDGE_SYSTEM = """\
You are an expert QA examiner. Your job is to score an AI QA agent's response \
against a structured rubric. Be rigorous but fair. Evidence must be a direct \
short quote from the agent response (≤150 chars). Reasoning explains why the \
score was given (≤200 chars). Always return valid JSON only — no markdown fences, \
no extra text."""


def _build_judge_prompt(
    scenario: str,
    input_message: str,
    output: str,
    criteria: list[dict],
) -> str:
    """Build the user-turn prompt for the judge LLM call."""
    criteria_blocks = []
    for c in criteria:
        rubric_lines = "\n".join(
            f"  {score} — {desc}"
            for score, desc in sorted(c.get("rubric", {}).items(), reverse=True)
        )
        criteria_blocks.append(
            f"### {c['id']}\n"
            f"Description: {c.get('description', '')}\n"
            f"Weight: {c.get('weight', 1.0)}\n"
            f"Rubric (0–3):\n{rubric_lines}"
        )

    criteria_text = "\n\n".join(criteria_blocks)

    return f"""\
## Scenario
{scenario}

## Input Given to Agent
{input_message}

## Agent Response
{output}

## Criteria to Score

{criteria_text}

## Instructions
Score EACH criterion above. Return ONLY a JSON object with this exact structure:
{{
  "<criterion_id>": {{
    "score": <integer 0–3>,
    "evidence": "<direct quote from agent response, max 150 chars>",
    "reasoning": "<why this score, max 200 chars>"
  }}
}}
All criterion IDs must appear as keys. No extra fields. No markdown."""


def evaluate_criteria(
    output: str,
    criteria: list[dict],
    scenario: str,
    input_message: str,
) -> dict[str, Any]:
    """
    Call LLM to score each criterion in the rubric.

    Returns dict: {criterion_id: {score: int, evidence: str, reasoning: str}}
    On any error, returns an empty dict (caller falls back to pending mentor scoring).
    """
    if not criteria:
        return {}

    from config import (
        LLM_PROVIDER, MODEL_NAME,
        ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENAI_BASE_URL,
    )
    from agent.llm_client import call_llm
    from langchain_core.messages import HumanMessage

    prompt = _build_judge_prompt(scenario, input_message, output, criteria)

    try:
        response = call_llm(
            system_prompt=_JUDGE_SYSTEM,
            messages=[HumanMessage(content=prompt)],
            tool_definitions=[],
            model=MODEL_NAME,
            provider=LLM_PROVIDER,
            anthropic_api_key=ANTHROPIC_API_KEY,
            openai_api_key=OPENAI_API_KEY,
            openai_base_url=OPENAI_BASE_URL,
            max_tokens=1024,
        )
        raw = response.text.strip()
        # Strip any accidental markdown fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw)
        # Validate and normalise each entry
        result = {}
        for c in criteria:
            cid = c["id"]
            entry = parsed.get(cid, {})
            score = int(entry.get("score", 0))
            score = max(0, min(3, score))   # clamp to 0–3
            result[cid] = {
                "score":     score,
                "evidence":  str(entry.get("evidence", ""))[:300],
                "reasoning": str(entry.get("reasoning", ""))[:300],
            }
        return result
    except Exception:
        return {}


# ── Score Normalisation ───────────────────────────────────────────────────────

def judge_to_score(judge_results: dict[str, Any], criteria: list[dict]) -> float:
    """
    Convert per-criterion 0–3 scores to a weighted 0–100 score.

    Formula per criterion:  (score / 3) * 100 * weight
    Total weight should sum to 1.0; if it doesn't we normalise.
    """
    if not judge_results or not criteria:
        return 0.0

    total_weight = sum(c.get("weight", 1.0) for c in criteria)
    if total_weight == 0:
        return 0.0

    weighted_sum = 0.0
    for c in criteria:
        cid    = c["id"]
        weight = c.get("weight", 1.0) / total_weight   # normalise
        score  = judge_results.get(cid, {}).get("score", 0)
        weighted_sum += (score / 3.0) * 100.0 * weight

    return round(weighted_sum, 1)
